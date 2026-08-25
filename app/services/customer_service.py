# -*- coding: utf-8 -*-
"""
客户服务模块

提供客户相关的业务逻辑。
重构后的版本使用Repository模式进行数据访问，职责更加单一。
"""
import ipaddress
from app.utils.logging import get_logger
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from app.models.customer import Customer
from app.core.enums import CustomerStatus
from app.persistence.customer_repository import CustomerRepository
from app.services.switch_events import emit_resource_change_global
from app.utils.cache import cache_manager, cached
from app.exceptions.business import BusinessLogicError
from app.exceptions.data_access import RecordNotFoundError
from app.exceptions.validation import ValidationError
from config import get_config

logger = get_logger(__name__)
config = get_config()


class CustomerService:

    def __init__(self, customer_repository: CustomerRepository):
        self.customer_repository = customer_repository
        self.cache_ttl = config.CACHE_TTL_ROOM

    def get_by_id(self, customer_id: int) -> Optional[Customer]:
        return self.customer_repository.find_by_id(customer_id)

    def get_by_name(self, customer_name: str) -> Optional[Customer]:
        return self.customer_repository.find_by_customer_name(customer_name)

    def search_customers(
        self, keyword: str = None, page: int = 1, page_size: int = 20
    ) -> Dict[str, Any]:
        result = self.customer_repository.search(
            search_fields=["customer_name", "contact_person", "contact_phone", "email"],
            keyword=keyword,
            page=page,
            page_size=page_size
        )

        result["data"] = [customer.to_dict() for customer in result["data"]]

        return result

    def name_exists(self, name: str, exclude_id: int = None) -> bool:
        return self.customer_repository.check_customer_name_exists(name, exclude_id)

    def create_customer(self, data: Dict[str, Any]) -> Customer:
        payload = self._normalize_customer_payload(data, is_update=False)
        name = payload.get("customer_name")
        if not name:
            raise ValidationError("customer_name 不能为空")
        if self.name_exists(name):
            raise ValidationError(f"客户名称 '{name}' 已存在")

        customer = self.customer_repository.create(payload)
        cache_manager.invalidate_pattern("customer:*")
        emit_resource_change_global("customer", "create", ids=[customer.id])
        return customer

    def update_customer(self, customer_id: int, data: Dict[str, Any]) -> Optional[Customer]:
        payload = self._normalize_customer_payload(data, is_update=True)
        if "customer_name" in payload:
            if self.name_exists(payload["customer_name"], exclude_id=customer_id):
                raise ValidationError(f"客户名称 '{payload['customer_name']}' 已存在")

        customer = self.customer_repository.update(customer_id, payload)
        cache_manager.invalidate_pattern("customer:*")
        emit_resource_change_global("customer", "update", ids=[customer_id])
        return customer


    def assert_allocatable(self, customer_id: int) -> None:
        customer = self.customer_repository.find_by_id(customer_id)
        if customer is None:
            raise RecordNotFoundError(f"客户不存在: {customer_id}")
        if customer.customer_status == CustomerStatus.TERMINATED.value:
            raise BusinessLogicError(
                f"客户[{customer.customer_name}]已终止，禁止分配资源",
                code="CUSTOMER_TERMINATED",
                status_code=409,
            )


    def terminate_customer(self, customer_id: int, operator_id: int, reason: Optional[str] = None) -> Customer:
        from extensions import db
        from app.utils.transactional import on_commit
        from app.services.audit_service import AuditService
        from app.persistence.ip_repositories import IPManagerRepository, IPNetworkRepository
        from app.persistence.device_repository import DeviceRepository
        from app.persistence.cabinet_repository import CabinetRepository
        from app.persistence.switch_port_repository import NetworkPortRepository
        from app.persistence.component_template_repository import ComponentTemplateRepository
        from app.persistence.customer_termination_archive_repository import CustomerTerminationArchiveRepository

        customer = (
            db.session.query(Customer)
            .filter_by(id=customer_id)
            .with_for_update()
            .first()
        )
        if customer is None:
            raise RecordNotFoundError(f"客户不存在: {customer_id}")
        if customer.customer_status == CustomerStatus.TERMINATED.value:
            return customer

        ip_repo = IPManagerRepository()
        ip_network_repo = IPNetworkRepository()
        device_repo = DeviceRepository()
        cabinet_repo = CabinetRepository()
        switch_port_repo = NetworkPortRepository()
        template_repo = ComponentTemplateRepository()
        archive_repo = CustomerTerminationArchiveRepository()
        audit_service = AuditService()

        with db.session.begin_nested():
            assets = self.get_customer_assets(customer_id)
            import json as _json
            assets = _json.loads(_json.dumps(assets, default=str))
            archive = archive_repo.create({
                "customer_id": customer_id,
                "summary_json": assets,
                "operator_id": operator_id,
                "reason": reason,
                "pdf_blob": None,
                "pdf_size": None,
            })
            db.session.flush()

            ip_repo.clear_customer(customer_id)
            ip_network_repo.clear_customer(customer_id)
            device_repo.clear_customer(customer_id)
            cabinet_repo.clear_customer(customer_id)
            switch_port_repo.release_customer_ports(customer_id)
            template_repo.delete_customer_templates(customer_id)

            customer.customer_status = CustomerStatus.TERMINATED.value
            self.customer_repository.save(customer)
            db.session.flush()

        archive_id = archive.id
        assets_summary = assets.get("summary", {})
        on_commit(lambda: self._generate_and_persist_pdf(archive_id))
        on_commit(lambda: cache_manager.invalidate_pattern("customer:*"))
        on_commit(lambda: emit_resource_change_global("customer", "terminate", ids=[customer_id]))
        on_commit(lambda: audit_service.log(
            user_id=operator_id, action="terminate", resource="customer",
            resource_id=customer_id,
            detail={"reason": reason, "archive_id": archive_id, "summary": assets_summary},
        ))
        return customer

    def _generate_and_persist_pdf(self, archive_id: int) -> None:
        from sqlalchemy.orm import Session
        from extensions import db as _db
        from app.models.customer_termination_archive import CustomerTerminationArchive

        independent_session: Session = Session(bind=_db.engine, expire_on_commit=False)
        try:
            archive = independent_session.query(CustomerTerminationArchive).filter_by(id=archive_id).first()
            if not archive:
                logger.warning("终止存档 PDF 生成失败：archive_id=%s 不存在", archive_id)
                return
            customer = self.customer_repository.find_by_id(archive.customer_id)
            if not customer:
                logger.warning("终止存档 PDF 生成失败：customer_id=%s 不存在", archive.customer_id)
                return
            pdf_buf = self.generate_customer_termination_pdf(customer, archive.summary_json)
            pdf_bytes = pdf_buf.read()
            archive.pdf_blob = pdf_bytes
            archive.pdf_size = len(pdf_bytes)
            independent_session.commit()
            logger.info("终止存档 PDF 生成成功 archive_id=%s size=%s", archive_id, len(pdf_bytes))
        except Exception:
            independent_session.rollback()
            logger.warning("终止存档 PDF 生成失败 archive_id=%s", archive_id, exc_info=True)
        finally:
            independent_session.close()

    def generate_customer_termination_pdf(self, customer, assets: dict):
        from io import BytesIO
        from datetime import datetime
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas as _canvas_mod

        class _NumberedCanvas(_canvas_mod.Canvas):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._saved_states = []

            def showPage(self):
                self._saved_states.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                total = len(self._saved_states)
                for idx, state in enumerate(self._saved_states, 1):
                    self.__dict__.update(state)
                    self.setFont(cn_font, 9)
                    self.drawCentredString(self._pagesize[0] / 2, 15 * mm, f"第 {idx} 页 / 共 {total} 页")
                    super().showPage()
                super().save()

        cn_font = "STSong-Light"
        try:
            pdfmetrics.registerFont(UnicodeCIDFont(cn_font))
        except Exception:
            cn_font = "Helvetica"

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=f"客户终止存档-{customer.customer_name}")
        styles = getSampleStyleSheet()
        for _name, _style in styles.byName.items():
            _style.fontName = cn_font
        styles.add(ParagraphStyle(name="CNTitle", parent=styles["Title"], fontName=cn_font, fontSize=18))
        styles.add(ParagraphStyle(name="CNHeading2", parent=styles["Heading2"], fontName=cn_font, fontSize=13))
        styles.add(ParagraphStyle(name="CNHeading3", parent=styles["Heading3"], fontName=cn_font, fontSize=11, spaceBefore=4, spaceAfter=2))
        styles.add(ParagraphStyle(name="CNNormal", parent=styles["Normal"], fontName=cn_font, fontSize=10))
        story = []

        _tbl_style = TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), cn_font),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])

        def _add_table(title, header, rows, col_widths):
            story.append(Paragraph(title, styles["CNHeading2"]))
            story.append(Spacer(1, 6))
            if rows:
                table_data = [header] + rows
            else:
                table_data = [header]
            story.append(Table(table_data, colWidths=col_widths, style=_tbl_style, repeatRows=1))
            story.append(Spacer(1, 12))

        story.append(Paragraph(f"客户终止存档 - {customer.customer_name}", styles["CNTitle"]))
        story.append(Spacer(1, 10))
        summary = assets.get("summary", {})
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        info_data = [
            ["客户名称", assets.get("customer_name", ""), "终止时间", now_str],
            ["客户状态", "已终止", "生成方式", "系统自动生成"],
        ]
        story.append(Table(info_data, colWidths=[80, 200, 80, 200], style=_tbl_style))
        story.append(Spacer(1, 12))

        overview_rows = [
            ["机柜总数", str(summary.get("total_cabinets", 0)), "整柜租赁", str(summary.get("full_cabinets", 0))],
            ["部分使用机柜", str(summary.get("partial_cabinets", 0)), "已用U位", str(assets.get("cabinets", {}).get("total_u_used", 0))],
            ["设备总数", str(summary.get("total_devices", 0)), "整柜设备", str(summary.get("full_cabinet_devices", 0))],
            ["部分使用设备", str(summary.get("partial_cabinet_devices", 0)), "", ""],
            ["网段数", str(summary.get("total_networks", 0)), "整网段", str(summary.get("full_networks", 0))],
            ["IP总数", str(summary.get("total_ips", 0)), "零散IP", str(summary.get("partial_ips", 0))],
        ]
        _add_table("资源概览", ["项目", "数值", "项目", "数值"], overview_rows, [120, 120, 120, 120])

        cabinet_rows = []
        for c in assets.get("cabinets", {}).get("full_cabinets", []):
            total_u = int(c.get("total_u", 0) or 1)
            used_u = int(c.get("used_u", 0) or 0)
            cabinet_rows.append([
                c.get("cabinet_number", ""), "整柜租赁", c.get("room_name", ""),
                str(total_u), str(used_u), f"{used_u / total_u * 100:.0f}%" if total_u else "0%", "",
            ])
        for c in assets.get("cabinets", {}).get("partial_cabinets", []):
            total_u = int(c.get("total_u", 0) or 1)
            used = int(c.get("u_used", 0) or c.get("used_u", 0) or 0)
            cabinet_rows.append([
                c.get("cabinet_number", ""), "部分使用", c.get("room_name", ""),
                str(total_u), str(used), f"{used / total_u * 100:.0f}%" if total_u else "0%", str(c.get("device_count", "")),
            ])
        _add_table("机柜明细", ["机柜编号", "类型", "机房", "总U位", "已用U位", "使用率", "设备数"],
                   cabinet_rows, [70, 60, 80, 50, 50, 50, 50])

        network_rows = []
        for n in assets.get("networks", {}).get("full_networks", []):
            network_rows.append([
                "整网段", n.get("ip_network", ""), str(n.get("mask", "")),
                str(n.get("ip_count", "")), n.get("room_name", ""),
            ])
        for ip in assets.get("networks", {}).get("partial_ips", []):
            network_rows.append([
                "零散IP", ip.get("ip_address", ""), "", "", ip.get("room_name", ""),
            ])
        _add_table("网段与IP", ["类型", "网段/IP地址", "掩码", "IP数量", "机房"],
                   network_rows, [60, 150, 60, 60, 100])

        port_rows = []
        for r in assets.get("ports", {}).get("rows", []):
            port_rows.append([
                r.get("switch_name", ""), r.get("port_name", ""),
                r.get("usage_status", ""), r.get("link_status", ""), str(r.get("speed", "")),
            ])
        _add_table("端口分配", ["交换机", "端口名", "使用状态", "链路状态", "速率"],
                   port_rows, [100, 80, 80, 80, 60])

        device_detail_rows = assets.get("devices", {}).get("detail_rows", [])
        base_rows = []
        for r in device_detail_rows:
            base_rows.append([
                r.get("device_name", ""), r.get("device_type", ""), r.get("device_subtype", ""),
                r.get("brand", ""), r.get("device_model", ""), r.get("serial_number", ""),
                r.get("cabinet_number", ""), str(r.get("u_position", "")),
            ])
        _add_table("设备基础信息",
                   ["设备名称", "类型", "子类型", "品牌", "型号", "序列号", "机柜", "U位"],
                   base_rows, [120, 60, 60, 70, 90, 100, 60, 40])

        config_rows = []
        for r in device_detail_rows:
            config_rows.append([
                r.get("device_name", ""),
                r.get("cpu", ""), str(r.get("cpu_way", "")), str(r.get("cpu_cores", "")),
                r.get("memory", ""), str(r.get("memory_size_gb", "")), r.get("gpu", ""),
                r.get("storage_summary", ""), r.get("os_version", ""), r.get("ip_address", ""),
            ])
        _add_table("设备配置信息",
                   ["设备名称", "CPU", "路数", "核心", "内存", "内存GB", "GPU", "存储", "OS", "管理IP"],
                   config_rows, [120, 90, 40, 45, 70, 50, 60, 90, 70, 80])

        doc.build(story, canvasmaker=_NumberedCanvas)
        buf.seek(0)
        return buf


    def delete_customer(self, customer_id: int, force: bool = False) -> bool:
        customer = self.get_by_id(customer_id)
        if not customer:
            return False

        resource_counts = self.customer_repository.check_customer_has_resources(customer_id)
        cabinet_count = resource_counts["cabinet_count"]
        device_count = resource_counts["device_count"]

        if (cabinet_count > 0 or device_count > 0) and not force:
            raise ValidationError(
                f"客户还有 {cabinet_count} 个机柜和 {device_count} 个设备，无法删除。"
                "请先删除所有关联资源或使用强制删除。"
            )

        result = self.customer_repository.delete(customer_id)

        if result:
            cache_manager.invalidate_pattern("customer:*")
            emit_resource_change_global("customer", "delete", ids=[customer_id])

        return result

    def _normalize_customer_payload(self, data: Dict[str, Any], is_update: bool) -> Dict[str, Any]:
        payload = dict(data or {})

        if "name" in payload and "customer_name" not in payload:
            payload["customer_name"] = payload.pop("name")
        if "status" in payload and "customer_status" not in payload:
            payload["customer_status"] = payload.pop("status")

        allowed_fields = {"customer_name", "customer_status", "contact_person", "contact_phone", "email", "address", "notes"}
        normalized = {k: v for k, v in payload.items() if k in allowed_fields}

        if not is_update:
            normalized.setdefault("customer_status", CustomerStatus.ACTIVE.value)

        return normalized

    def get_cabinets(self, customer_id: int) -> List:
        customer = self.customer_repository.find_with_relations(customer_id, ["cabinets"])
        if not customer:
            return []

        return customer.cabinets

    def get_devices(self, customer_id: int) -> List:
        customer = self.customer_repository.find_with_relations(customer_id, ["devices"])
        if not customer:
            return []

        return customer.devices

    @cached(key_pattern="customer:resources:{customer_id}")
    def get_customer_resources(self, customer_id: int) -> Dict[str, Any]:
        customer = self.customer_repository.find_with_relations(customer_id, ["cabinets", "devices"])
        if not customer:
            return None

        cabinets = customer.cabinets
        devices = customer.devices

        total_u = sum(cabinet.total_u for cabinet in cabinets)
        used_u = sum(cabinet.used_u for cabinet in cabinets)
        total_power = sum(cabinet.total_power or 0 for cabinet in cabinets)
        used_power = sum(cabinet.used_power or 0 for cabinet in cabinets)

        return {
            "customer_id": customer_id,
            "customer_name": customer.customer_name,
            "cabinet_count": len(cabinets),
            "device_count": len(devices),
            "total_u": total_u,
            "used_u": used_u,
            "available_u": total_u - used_u,
            "total_power": total_power,
            "used_power": used_power,
            "available_power": total_power - used_power,
            "cabinets": [cabinet.to_dict() for cabinet in cabinets],
            "devices": [device.to_dict() for device in devices],
        }


    def get_all_customers_list(self) -> List[Dict[str, Any]]:
        try:
            customers = self.customer_repository.find_all(order_by="customer_name")
            return [
                {
                    "id": c.id,
                    "customer_name": c.customer_name,
                    "customer_status": c.customer_status if c.customer_status is not None else CustomerStatus.ACTIVE.value,
                    "created_at": self._format_datetime(c.created_at),
                    "updated_at": self._format_datetime(c.updated_at),
                }
                for c in customers
            ]
        except Exception as e:
            logger.error(f"获取客户列表失败: {e}", exc_info=True)
            raise

    def customer_exists_by_id(self, customer_id: int) -> bool:
        return self.customer_repository.find_by_id(customer_id) is not None

    def get_customer_switch_ports(self, customer_id: int) -> Dict[str, Any]:
        try:
            from sqlalchemy import func as sa_func

            data = self.customer_repository.get_customer_switch_ports_data(customer_id)

            result = data["result"]
            networks = data["networks"]
            all_ip_rows = data["all_ip_rows"]
            customer_direct_ip_rows = data["customer_direct_ip_rows"]
            ip_switch_rows = data["ip_switch_rows"]
            switch_ids_with_ports = data["switch_ids_with_ports"]

            ip_assignments_by_room: Dict[int, Dict[int, List[str]]] = {}
            for ip_data in all_ip_rows:
                ip_address = ip_data.ip_address
                ip_customer_id = ip_data.customer_id
                room_id = ip_data.room_id

                if room_id not in ip_assignments_by_room:
                    ip_assignments_by_room[room_id] = {}

                if ip_customer_id not in ip_assignments_by_room[room_id]:
                    ip_assignments_by_room[room_id][ip_customer_id] = []

                ip_assignments_by_room[room_id][ip_customer_id].append(ip_address)

            processed_networks = []

            for network in networks:
                ip_network_str = str(network.get("ip_network", ""))
                network_customer_id = network.get("network_customer_id")
                room_id = network.get("room_id")
                port = network.get("port", "")

                if network_customer_id != customer_id:
                    continue

                if port is None or port == "Unknown" or str(port).strip() == "":
                    logger.debug(f"网段 {ip_network_str} 端口数据无效 ({port})，跳过处理")
                    continue

                try:
                    if ip_network_str == "0.0.0.0/0":
                        continue

                    network_obj = ipaddress.ip_network(ip_network_str, strict=False)
                    room_ip_assignments = ip_assignments_by_room.get(room_id, {})

                    occupied_ips: Set[ipaddress.IPv4Address] = set()
                    for other_customer_id, ip_list in room_ip_assignments.items():
                        if other_customer_id != customer_id:
                            for ip in ip_list:
                                try:
                                    ip_obj = ipaddress.ip_address(ip)
                                    if ip_obj in network_obj:
                                        occupied_ips.add(ip_obj)
                                except Exception:
                                    logger.debug("解析IP地址失败，跳过: ip=%s", ip, exc_info=True)
                                    continue

                    if not occupied_ips:
                        processed_networks.append(
                            {
                                "ip_network": ip_network_str,
                                "switch_name": network.get("switch_name"),
                                "switch_ip": network.get("switch_ip"),
                                "room_name": network.get("room_name"),
                                "room_id": room_id,
                                "is_split": False,
                                "switch_id": network.get("switch_id"),
                                "port": port,
                            }
                        )
                    else:
                        logger.info(
                            f"检测到网段 {ip_network_str} 有 {len(occupied_ips)} 个IP被其他客户占用"
                        )
                        available_ips = []
                        host_count = network_obj.num_addresses - 2
                        if host_count > 1024 and len(occupied_ips) < host_count // 2:
                            occupied_ints = sorted(int(ip) for ip in occupied_ips)
                            first = int(network_obj.network_address) + 1
                            last = int(network_obj.broadcast_address) - 1
                            ranges = []
                            start = first
                            for occ in occupied_ints:
                                if occ > last:
                                    break
                                if occ < first:
                                    continue
                                if occ > start:
                                    ranges.append((start, occ - 1))
                                start = occ + 1
                            if start <= last:
                                ranges.append((start, last))
                            for r_start, r_end in ranges:
                                while r_start <= r_end:
                                    max_bits = (r_start & -r_start).bit_length() - 1 if r_start else 32
                                    remaining = r_end - r_start + 1
                                    prefix_len = 32 - max_bits
                                    while (1 << (32 - prefix_len)) > remaining and prefix_len < 32:
                                        prefix_len += 1
                                    cidr = ipaddress.ip_network(f"{ipaddress.ip_address(r_start)}/{prefix_len}", strict=False)
                                    available_ips.append(cidr)
                                    r_start += cidr.num_addresses
                        else:
                            for ip in network_obj.hosts():
                                if ip not in occupied_ips:
                                    available_ips.append(ip)

                        if available_ips:
                            if host_count > 1024 and len(occupied_ips) < host_count // 2:
                                cidrs = available_ips
                            else:
                                cidrs = self._ips_to_cidrs(available_ips)
                            logger.info(f"网段 {ip_network_str} 拆分为 {len(cidrs)} 个CIDR块")
                            for cidr in cidrs:
                                processed_networks.append(
                                    {
                                        "ip_network": str(cidr),
                                        "switch_name": network.get("switch_name"),
                                        "switch_ip": network.get("switch_ip"),
                                        "room_name": network.get("room_name"),
                                        "room_id": room_id,
                                        "is_split": True,
                                        "switch_id": network.get("switch_id"),
                                        "port": port,
                                    }
                                )

                except Exception as e:
                    logger.error(f"处理网段 {ip_network_str} 失败: {e}")
                    continue

            direct_ips_by_room: Dict[int, List[str]] = {}
            for ip_data in customer_direct_ip_rows:
                room_id = ip_data.room_id
                if room_id not in direct_ips_by_room:
                    direct_ips_by_room[room_id] = []
                direct_ips_by_room[room_id].append(ip_data.ip_address)

            ip_switch_map = {}
            for row in ip_switch_rows:
                ip_switch_map[(row.ip_address, row.room_id)] = {
                    "switch_name": row.switch_name or "",
                    "switch_ip": row.switch_ip or "",
                    "room_name": row.room_name or "",
                    "switch_id": row.switch_id,
                }

            for room_id, ip_list in direct_ips_by_room.items():
                for ip_address in ip_list:
                    try:
                        ip_obj = ipaddress.ip_address(ip_address)
                        is_covered = False

                        for network_data in processed_networks:
                            if network_data.get("room_id") == room_id:
                                try:
                                    net_obj = ipaddress.ip_network(
                                        network_data["ip_network"], strict=False
                                    )
                                    if ip_obj in net_obj:
                                        is_covered = True
                                        break
                                except Exception:
                                    logger.debug("解析网段失败，跳过: network=%s", network_data.get("ip_network"), exc_info=True)
                                    continue

                        if not is_covered:
                            switch_info = ip_switch_map.get((ip_address, room_id))
                            if switch_info and switch_info["switch_id"] in switch_ids_with_ports:
                                processed_networks.append(
                                    {
                                        "ip_network": f"{ip_address}/32",
                                        "switch_name": switch_info["switch_name"],
                                        "switch_ip": switch_info["switch_ip"],
                                        "room_name": switch_info["room_name"],
                                        "room_id": room_id,
                                        "is_split": False,
                                        "switch_id": switch_info["switch_id"],
                                    }
                                )
                            else:
                                logger.debug(f"直接分配IP {ip_address} 所在交换机无端口，跳过处理")

                    except Exception as e:
                        logger.error(f"处理直接分配IP {ip_address} 失败: {e}")
                        continue

            filtered_networks = self._filter_contained_networks(processed_networks)

            status_map = {0: "online", 1: "offline", 2: "banned", 3: "unused"}

            for network_data in filtered_networks:
                ip_network = network_data["ip_network"]
                room_id = network_data["room_id"]
                room_name = network_data["room_name"]

                if room_name not in result:
                    result[room_name] = {"ports": [], "ip_networks": []}

                try:
                    network_obj = ipaddress.ip_network(ip_network, strict=False)
                    first_ip_int = int(network_obj.network_address) + 1
                    last_ip_int = int(network_obj.broadcast_address) - 1

                    from app.models.ip_model import IPManager
                    status_rows = (
                        self.customer_repository.session.query(
                            IPManager.status,
                            sa_func.count(sa_func.distinct(IPManager.ip_address)).label("count"),
                        )
                        .filter(
                            IPManager.ip_int >= first_ip_int,
                            IPManager.ip_int <= last_ip_int,
                            IPManager.customer_id == customer_id,
                            IPManager.room_id == room_id,
                        )
                        .group_by(IPManager.status)
                        .all()
                    )

                    ip_status = {"online": 0, "offline": 0, "banned": 0, "unused": 0}
                    total_counted = 0
                    for status_row in status_rows:
                        status_code = status_row.status
                        count = status_row.count or 0
                        if status_code in status_map:
                            status_name = status_map[status_code]
                            ip_status[status_name] = count
                            total_counted += count

                    total_hosts = last_ip_int - first_ip_int + 1
                    ip_status["unused"] = total_hosts - total_counted

                    result[room_name]["ip_networks"].append(
                        {
                            "ip_network": ip_network,
                            "switch_name": str(network_data.get("switch_name", "")),
                            "switch_ip": str(network_data.get("switch_ip", "")),
                            "status": ip_status,
                        }
                    )

                except Exception as e:
                    logger.error(f"统计网段 {ip_network} 状态失败: {e}")
                    continue

            rooms_to_remove = []
            for room_name, room_data in result.items():
                if not room_data["ip_networks"]:
                    rooms_to_remove.append(room_name)

            for room_name in rooms_to_remove:
                del result[room_name]

            logger.info(f"客户 {customer_id} 资源统计完成，共 {len(result)} 个机房")
            return result

        except Exception as e:
            logger.error(f"获取客户交换机端口IP地址段失败: {e}", exc_info=True)
            return {}

    def _ips_to_cidrs(self, ip_list: List[ipaddress.IPv4Address]) -> List[ipaddress.IPv4Network]:
        if not ip_list:
            return []

        sorted_ips = sorted(ip_list)

        cidrs = list(
            ipaddress.collapse_addresses([ipaddress.ip_network(f"{ip}/32") for ip in sorted_ips])
        )

        return cidrs

    def _filter_contained_networks(self, networks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not networks:
            return []

        try:
            networks_by_room: Dict[int, List[Dict[str, Any]]] = {}
            for net in networks:
                room_id = net.get("room_id")
                if room_id not in networks_by_room:
                    networks_by_room[room_id] = []
                networks_by_room[room_id].append(net)

            filtered_all = []

            for room_id, room_networks in networks_by_room.items():
                parsed_networks = []
                for network in room_networks:
                    try:
                        ip_network_str = network["ip_network"]
                        network_obj = ipaddress.ip_network(ip_network_str, strict=False)
                        parsed_networks.append(
                            {"network_obj": network_obj, "network_data": network}
                        )
                    except Exception as e:
                        logger.error(f"解析网段 {network.get('ip_network')} 失败: {e}")
                        continue

                parsed_networks.sort(key=lambda x: x["network_obj"].prefixlen)

                for i, current in enumerate(parsed_networks):
                    current_net = current["network_obj"]
                    is_contained = False

                    for j in range(i):
                        larger_net = parsed_networks[j]["network_obj"]
                        if current_net.subnet_of(larger_net):
                            is_contained = True
                            logger.debug(f"网段 {current_net} 被 {larger_net} 包含，已过滤")
                            break

                    if not is_contained:
                        filtered_all.append(current["network_data"])

            return filtered_all

        except Exception as e:
            logger.error(f"过滤网段失败: {e}")
            return networks

    def _format_datetime(self, dt: Any) -> Optional[str]:
        if dt is None:
            return None
        if isinstance(dt, (datetime,)):
            return dt.isoformat()
        if hasattr(dt, "isoformat"):
            return dt.isoformat()
        return str(dt)

    def get_paginated(self, page: int = 1, per_page: int = 20, filters: Dict = None):
        filters = dict(filters or {})
        if "status" in filters and "customer_status" not in filters:
            filters["customer_status"] = filters.pop("status")

        result = self.customer_repository.paginate(
            filters=filters,
            page=page,
            page_size=per_page,
        )
        return result.get("data", []), result.get("total_count", 0)
    def get_customer_assets(self, customer_id: int) -> Dict[str, Any]:
        customer = self.customer_repository.find_by_id(customer_id)
        if not customer:
            raise RecordNotFoundError(f"客户不存在: {customer_id}")

        assets = self.customer_repository.get_customer_asset_statistics(customer_id)
        assets["customer_name"] = customer.customer_name
        assets["customer_status"] = customer.customer_status
        assets["summary"] = {
            "total_rooms": len(assets["rooms"]),
            "total_cabinets": assets["cabinets"]["total_count"],
            "full_cabinets": len(assets["cabinets"]["full_cabinets"]),
            "partial_cabinets": len(assets["cabinets"]["partial_cabinets"]),
            "total_devices": assets["devices"]["total_count"],
            "full_cabinet_devices": assets["devices"]["full_cabinet_count"],
            "partial_cabinet_devices": assets["devices"]["partial_cabinet_count"],
            "total_networks": assets["networks"]["total_networks"],
            "total_ips": assets["networks"]["total_ips"],
            "full_networks": len(assets["networks"]["full_networks"]),
            "partial_ips": len(assets["networks"]["partial_ips"]),
        }

        from app.models.device import Device
        from app.models.network_port import NetworkPort
        device_detail_rows = []
        for d in Device.query.filter_by(customer_id=customer_id).all():
            d_dict = d.to_dict()
            device_detail_rows.append({
                "device_name": d_dict.get("device_name", ""),
                "device_type": d_dict.get("device_type", ""),
                "device_subtype": d_dict.get("device_subtype", ""),
                "brand": d_dict.get("brand", ""),
                "device_model": d_dict.get("device_model", ""),
                "serial_number": d_dict.get("serial_number", ""),
                "cabinet_number": d.cabinet.cabinet_number if d.cabinet else "",
                "u_position": d_dict.get("u_position", ""),
                "cpu": d_dict.get("cpu", ""),
                "cpu_way": d_dict.get("cpu_way", ""),
                "cpu_cores": d_dict.get("cpu_cores", ""),
                "memory": d_dict.get("memory", ""),
                "memory_size_gb": d_dict.get("memory_size_gb", ""),
                "gpu": d_dict.get("gpu", ""),
                "storage_summary": d_dict.get("storage_summary", ""),
                "os_version": d_dict.get("os_version", ""),
                "ip_address": d_dict.get("ip_address", ""),
                "status_name": d.status_name,
            })
        assets["devices"]["detail_rows"] = device_detail_rows

        port_rows = []
        for p in NetworkPort.query.filter_by(customer_id=customer_id).all():
            port_rows.append({
                "switch_name": p.device.device_name if p.device else "",
                "port_name": p.port_name or "",
                "usage_status": p.usage_status or "",
                "link_status": p.link_status or "",
                "speed": getattr(p, "speed", "") or "",
            })
        assets["ports"] = {"rows": port_rows, "total_count": len(port_rows)}

        logger.info("获取客户 %d 资产统计成功", customer_id)
        return assets

    def generate_customer_assets_excel(self, customer_id: int):
        import pandas as pd
        from io import BytesIO
        from app.models.network_port import NetworkPort
        from app.models.device import Device

        assets = self.get_customer_assets(customer_id)
        summary = assets["summary"]
        buf = BytesIO()

        CUSTOMER_STATUS_LABELS = {0: "活跃", 1: "停用", 2: "待审核"}
        overview_rows = [
            {"项目": "客户名称", "数值": assets["customer_name"]},
            {"项目": "客户状态", "数值": CUSTOMER_STATUS_LABELS.get(assets["customer_status"], "未知")},
            {"项目": "", "数值": ""},
            {"项目": "【机柜统计】", "数值": ""},
            {"项目": "机柜总数", "数值": summary["total_cabinets"]},
            {"项目": "整柜租赁", "数值": summary["full_cabinets"]},
            {"项目": "部分使用", "数值": summary["partial_cabinets"]},
            {"项目": "已用U位", "数值": assets["cabinets"]["total_u_used"]},
            {"项目": "", "数值": ""},
            {"项目": "【设备统计】", "数值": ""},
            {"项目": "设备总数", "数值": summary["total_devices"]},
            {"项目": "整柜设备", "数值": summary["full_cabinet_devices"]},
            {"项目": "部分使用设备", "数值": summary["partial_cabinet_devices"]},
            {"项目": "", "数值": ""},
            {"项目": "【网络统计】", "数值": ""},
            {"项目": "网段数", "数值": summary["total_networks"]},
            {"项目": "整网段", "数值": summary["full_networks"]},
            {"项目": "IP总数", "数值": summary["total_ips"]},
            {"项目": "零散IP", "数值": summary["partial_ips"]},
        ]
        df_overview = pd.DataFrame(overview_rows)

        cabinet_rows = []
        for c in assets["cabinets"]["full_cabinets"]:
            cabinet_rows.append({
                "机柜编号": c.get("cabinet_number", ""),
                "类型": "整柜租赁",
                "机房": c.get("room_name", ""),
                "总U位": c.get("total_u", 0),
                "已用U位": c.get("used_u", 0),
                "使用率": f"{c.get('used_u', 0) / c.get('total_u', 1) * 100:.0f}%" if c.get("total_u") else "0%",
                "设备数": "",
            })
        for c in assets["cabinets"]["partial_cabinets"]:
            used = c.get("u_used", 0) or c.get("used_u", 0)
            cabinet_rows.append({
                "机柜编号": c.get("cabinet_number", ""),
                "类型": "部分使用",
                "机房": c.get("room_name", ""),
                "总U位": c.get("total_u", 0),
                "已用U位": used,
                "使用率": f"{used / c.get('total_u', 1) * 100:.0f}%" if c.get("total_u") else "0%",
                "设备数": c.get("device_count", ""),
            })
        df_cabinets = pd.DataFrame(cabinet_rows) if cabinet_rows else pd.DataFrame(
            columns=["机柜编号", "类型", "机房", "总U位", "已用U位", "使用率", "设备数"]
        )

        device_rows = []
        devices = Device.query.filter_by(customer_id=customer_id).all()
        for d in devices:
            d_dict = d.to_dict()
            cabinet_num = d.cabinet.cabinet_number if d.cabinet else ""
            device_rows.append({
                "设备名称": d_dict.get("device_name", ""),
                "设备类型": d_dict.get("device_type", ""),
                "子类型": d_dict.get("device_subtype", ""),
                "品牌": d_dict.get("brand", ""),
                "型号": d_dict.get("device_model", ""),
                "序列号": d_dict.get("serial_number", ""),
                "机柜": cabinet_num,
                "U位": d_dict.get("u_position", ""),
                "CPU": d_dict.get("cpu", ""),
                "CPU路数": d_dict.get("cpu_way", ""),
                "核心数": d_dict.get("cpu_cores", ""),
                "内存": d_dict.get("memory", ""),
                "内存容量GB": d_dict.get("memory_size_gb", ""),
                "GPU": d_dict.get("gpu", ""),
                "存储概要": d_dict.get("storage_summary", ""),
                "操作系统": d_dict.get("os_version", ""),
                "管理IP": d_dict.get("ip_address", ""),
                "状态": d.status_name,
            })
        df_devices = pd.DataFrame(device_rows) if device_rows else pd.DataFrame(
            columns=["设备名称", "设备类型", "子类型", "品牌", "型号", "序列号", "机柜", "U位",
                     "CPU", "CPU路数", "核心数", "内存", "内存容量GB", "GPU", "存储概要",
                     "操作系统", "管理IP", "状态"]
        )

        network_rows = []
        for n in assets["networks"]["full_networks"]:
            network_rows.append({
                "类型": "整网段",
                "网段/IP地址": n.get("ip_network", ""),
                "掩码": n.get("mask", ""),
                "IP数量": n.get("ip_count", ""),
                "机房": n.get("room_name", ""),
            })
        for ip in assets["networks"]["partial_ips"]:
            network_rows.append({
                "类型": "零散IP",
                "网段/IP地址": ip.get("ip_address", ""),
                "掩码": "",
                "IP数量": "",
                "机房": ip.get("room_name", ""),
            })
        df_networks = pd.DataFrame(network_rows) if network_rows else pd.DataFrame(
            columns=["类型", "网段/IP地址", "掩码", "IP数量", "机房"]
        )

        LINK_STATUS_LABELS = {
            "up": "在线",
            "down": "离线",
            "admin_down": "管理关闭",
            "disabled": "已禁用",
        }

        def _link_status_label(raw):
            s = (raw or "").strip().lower()
            if s == "admin_down" or "administratively" in s or s == "*down":
                return LINK_STATUS_LABELS["admin_down"]
            return LINK_STATUS_LABELS.get(s, raw or "未知")

        port_rows = []
        ports = NetworkPort.query.filter_by(customer_id=customer_id).all()
        for p in ports:
            peer_device = p.connection.device if p.connection else None
            port_rows.append({
                "交换机": p.device.device_name if p.device else "",
                "端口名": p.port_name or "",
                "端口类型": p.port_type or "",
                "端口速率": p.speed or "",
                "链路状态": _link_status_label(p.link_status),
                "对端设备": peer_device.device_name if peer_device else "",
            })
        df_ports = pd.DataFrame(port_rows) if port_rows else pd.DataFrame(
            columns=["交换机", "端口名", "端口类型", "端口速率", "链路状态", "对端设备"]
        )

        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_overview.to_excel(writer, index=False, sheet_name="资源概览")
            df_cabinets.to_excel(writer, index=False, sheet_name="机柜明细")
            df_devices.to_excel(writer, index=False, sheet_name="设备明细")
            df_networks.to_excel(writer, index=False, sheet_name="网段与IP")
            df_ports.to_excel(writer, index=False, sheet_name="端口分配")

        buf.seek(0)
        return buf


customer_service = CustomerService(CustomerRepository())
