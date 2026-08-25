# -*- coding: utf-8 -*-
"""
device_repository.py — 关键修复
覆盖 BUG-2 / BUG-3 / BUG-5 / BUG-9 / BUG-12 / BUG-13
"""
from app.utils.logging import get_logger
import random
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import case, distinct, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.models.device import Device
from app.core.enums import DeviceStatus
from app.persistence.base import SQLAlchemyRepository, QueryOptimizationMixin
from app.exceptions.data_access import QueryExecutionError
from app.utils.query_optimizer import monitor_query_performance
from extensions import db

logger = get_logger(__name__)


class DeviceRepository(SQLAlchemyRepository, QueryOptimizationMixin):

    _WRITABLE_FIELDS = {
        "device_name", "device_type", "device_subtype", "device_model", "brand",
        "serial_number", "hostname", "management_ip", "mac_address",
        "metric_template_group_id",
        "cabinet_id", "u_position", "height_u", "power",
        "status", "responsible_person", "notes", "customer_id",
        "parent_device_id", "is_chassis", "node_position", "node_row", "node_col",
        "total_nodes", "node_rows", "node_cols", "node_naming_pattern",
        "switch_role", "layer",
    }

    def __init__(self, session=None):
        super().__init__(Device, session)

    def find_ids_by_responsible_person(self, user_id: int) -> List[int]:
        rows = (
            self.session.query(Device.id)
            .filter(Device.responsible_person == user_id)
            .all()
        )
        return [r.id for r in rows]

    def find_ids_by_room_ids(self, room_ids: List[int]) -> List[int]:
        if not room_ids:
            return []
        from app.models.cabinet import Cabinet
        rows = (
            self.session.query(Device.id)
            .join(Cabinet, Cabinet.id == Device.cabinet_id)
            .filter(Cabinet.room_id.in_(room_ids))
            .all()
        )
        return [r.id for r in rows]

    def find_responsible_person_by_id(self, device_id: int) -> Optional[int]:
        row = (
            self.session.query(Device.responsible_person)
            .filter(Device.id == device_id)
            .first()
        )
        return row.responsible_person if row else None


    def find_by_id(self, device_id: int) -> Optional[Device]:
        try:
            return (
                self._base_query()
                .options(joinedload(Device.cabinet), joinedload(Device.customer), joinedload(Device.switch_credential))
                .filter(Device.id == device_id)
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_by_ids(self, device_ids: list) -> dict:
        if not device_ids:
            return {}
        try:
            rows = (
                self._base_query()
                .options(joinedload(Device.cabinet), joinedload(Device.customer), joinedload(Device.switch_credential))
                .filter(Device.id.in_(device_ids))
                .all()
            )
            return {d.id: d for d in rows}
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量查找设备失败", original_error=e)

    def find_by_id_or_404(self, device_id: int) -> Device:
        device = self.find_by_id(device_id)
        if device is None:
            from flask import abort
            abort(404)
        return device

    def find_by_id_including_deleted(self, device_id: int) -> Optional[Device]:
        try:
            return (
                self.session.query(Device)
                .options(
                    joinedload(Device.hardware),
                    joinedload(Device.server_ext),
                )
                .filter(Device.id == device_id)
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败（含已删除）", original_error=e)

    def find_ids_by_type(self, device_ids: List[int], device_types: set) -> List[int]:
        if not device_ids or not device_types:
            return []
        try:
            return [
                row[0] for row in self.session.query(Device.id)
                .filter(Device.id.in_(device_ids), Device.device_type.in_(device_types))
                .order_by(Device.id)
                .all()
            ]
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量查询设备 ID 失败", original_error=e)

    def find_by_device_name(self, device_name: str) -> Optional[Device]:
        try:
            return self._base_query().filter(Device.device_name == device_name).first()
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_by_serial_number(self, serial_number: str) -> Optional[Device]:
        try:
            return (
                self._base_query()
                .filter(Device.serial_number == serial_number)
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_nodes_by_chassis(self, chassis_id: int) -> List[Device]:
        try:
            from app.models.device_server_ext import DeviceServerExt
            return (
                self._base_query()
                .join(DeviceServerExt, DeviceServerExt.device_id == Device.id)
                .filter(
                    DeviceServerExt.parent_device_id == chassis_id,
                )
                .order_by(DeviceServerExt.node_position)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找机箱子节点失败", original_error=e)

    def find_chassis_by_id(self, device_id: int) -> Optional[Device]:
        try:
            return (
                self._base_query()
                .filter(
                    Device.id == device_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .first()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找机箱失败", original_error=e)

    def find_node_by_position(
        self, chassis_id: int, position: int, exclude_id: int = None
    ) -> Optional[Device]:
        try:
            from app.models.device_server_ext import DeviceServerExt
            q = (
                self._base_query()
                .join(DeviceServerExt, DeviceServerExt.device_id == Device.id)
                .filter(
                    DeviceServerExt.parent_device_id == chassis_id,
                    DeviceServerExt.node_position == position,
                    Device.status != DeviceStatus.SCRAPPED,
                )
            )
            if exclude_id:
                q = q.filter(Device.id != exclude_id)
            return q.first()
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找节点位置失败", original_error=e)

    def find_active_devices(self) -> List[Device]:
        try:
            return (
                self._base_query()
                .filter(Device.status != DeviceStatus.SCRAPPED)
                .order_by(Device.device_name)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_by_cabinet_id(self, cabinet_id: int) -> List[Device]:
        try:
            return (
                self._base_query()
                .options(joinedload(Device.cabinet), joinedload(Device.customer))
                .filter(
                    Device.cabinet_id == cabinet_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_by_customer_id(self, customer_id: int) -> List[Device]:
        try:
            return (
                self._base_query()
                .options(joinedload(Device.cabinet), joinedload(Device.customer))
                .filter(
                    Device.customer_id == customer_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def clear_customer(self, customer_id: int) -> int:
        from extensions import db
        result = db.session.query(Device).filter(
            Device.customer_id == customer_id,
        ).update({Device.customer_id: None}, synchronize_session=False)
        return result

    def find_by_status(self, status: int) -> List[Device]:
        try:
            return self._base_query().filter(Device.status == status).all()
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_child_devices(self, parent_device_id: int) -> List[Device]:
        try:
            from app.models.device_server_ext import DeviceServerExt
            return (
                self._base_query()
                .join(DeviceServerExt, DeviceServerExt.device_id == Device.id)
                .filter(DeviceServerExt.parent_device_id == parent_device_id)
                .order_by(DeviceServerExt.node_position)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找子设备失败", original_error=e)

    def find_by_room_id(self, room_id: int) -> List[Device]:
        try:
            from app.models.cabinet import Cabinet
            return (
                self._base_query()
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .options(joinedload(Device.cabinet))
                .filter(
                    Cabinet.room_id == room_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .order_by(Device.device_name)
                .all()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("查找设备失败", original_error=e)

    def find_node_position_conflict(
        self, parent_device_id: int, node_position: int, exclude_device_id: int = None
    ) -> Optional[Device]:
        from app.models.device_server_ext import DeviceServerExt
        query = (
            self._base_query()
            .join(DeviceServerExt, DeviceServerExt.device_id == Device.id)
            .filter(
                DeviceServerExt.parent_device_id == parent_device_id,
                DeviceServerExt.node_position    == node_position,
                Device.status           != DeviceStatus.SCRAPPED,
            )
        )
        if exclude_device_id:
            query = query.filter(Device.id != exclude_device_id)
        return query.first()


    def _apply_device_filters(
        self,
        query,
        cabinet_id=None,
        customer_id=None,
        device_id=None,
        room_id=None,
        parent_device_id=None,
        is_chassis=None,
        device_type=None,
        device_subtype=None,
        include_scrapped=False,
        has_ssh=None,
    ):
        from app.models.cabinet import Cabinet

        if not include_scrapped:
            query = query.filter(Device.status != DeviceStatus.SCRAPPED)

        if cabinet_id:
            query = query.filter(Device.cabinet_id == cabinet_id)
        if customer_id:
            query = query.filter(Device.customer_id == customer_id)
        if device_id:
            query = query.filter(Device.id == device_id)
        if room_id:
            query = query.join(Cabinet, Device.cabinet_id == Cabinet.id).filter(
                Cabinet.room_id == room_id
            )
        if parent_device_id is not None:
            from app.models.device_server_ext import DeviceServerExt
            query = query.join(DeviceServerExt, DeviceServerExt.device_id == Device.id).filter(
                DeviceServerExt.parent_device_id == parent_device_id
            )
        if is_chassis is not None:
            from app.models.device_server_ext import DeviceServerExt
            if parent_device_id is None:
                query = query.join(DeviceServerExt, DeviceServerExt.device_id == Device.id)
            query = query.filter(DeviceServerExt.is_chassis == is_chassis)
        if device_type:
            query = query.filter(Device.device_type == device_type)
        if device_subtype:
            query = query.filter(Device.device_subtype == device_subtype)

        if has_ssh is not None:
            from app.models.switch_credentials import SwitchCredentials
            query = query.join(SwitchCredentials, SwitchCredentials.device_id == Device.id)
            if has_ssh:
                query = query.filter(SwitchCredentials.has_ssh == True)
            else:
                query = query.filter(SwitchCredentials.has_ssh == False)

        return query

    @monitor_query_performance
    def get_all_devices(
        self,
        cabinet_id: int = None,
        customer_id: int = None,
        device_id: int = None,
        room_id: int = None,
        parent_device_id: int = None,
        is_chassis: int = None,
        device_type: str = None,
        device_subtype: str = None,
        page: int = 1,
        page_size: int = 20,
        include_scrapped: bool = False,
        has_ssh: bool = None,
    ) -> Dict[str, Any]:
        try:
            base_query = self._base_query().options(
                joinedload(Device.switch_credential),
            )

            filtered_query = self._apply_device_filters(
                base_query,
                cabinet_id=cabinet_id,
                customer_id=customer_id,
                device_id=device_id,
                room_id=room_id,
                parent_device_id=parent_device_id,
                is_chassis=is_chassis,
                device_type=device_type,
                device_subtype=device_subtype,
                include_scrapped=include_scrapped,
                has_ssh=has_ssh,
            )

            total = (
                filtered_query
                .with_entities(func.count(distinct(Device.id)))
                .scalar()
                or 0
            )
            total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
            page = max(1, min(page, total_pages or 1))
            offset = (page - 1) * page_size

            devices = (
                filtered_query
                .order_by(Device.device_name)
                .limit(page_size)
                .offset(offset)
                .all()
            )

            return {
                "devices":     [d.to_dict() for d in devices],
                "total":       total,
                "total_pages": total_pages,
                "page":        page,
                "page_size":   page_size,
            }
        except SQLAlchemyError as e:
            raise QueryExecutionError("获取设备列表失败", original_error=e)

    @monitor_query_performance
    def search_devices(
        self,
        keyword: str = None,
        device_type: str = None,
        status: int = None,
        cabinet_id: int = None,
        customer_id: int = None,
        page: int = 1,
        page_size: int = 20,
        include_scrapped: bool = False,
    ) -> Dict[str, Any]:
        try:
            from app.models.device_hardware import DeviceHardware

            filters: Dict[str, Any] = {}
            if device_type:
                filters["device_type"] = device_type
            if cabinet_id:
                filters["cabinet_id"] = cabinet_id
            if customer_id:
                filters["customer_id"] = customer_id
            if status is not None:
                filters["status"] = status

            exclude_filters: Dict[str, Any] = {}
            if not include_scrapped and status is None:
                exclude_filters["status"] = DeviceStatus.SCRAPPED

            join_search_fields = [
                {"model": DeviceHardware, "field": "ip_address", "cast": "Text"},
                {"model": DeviceHardware, "field": "ipmi_address"},
            ]

            joins = [{"model": DeviceHardware, "type": "outerjoin"}]

            result = self.search(
                search_fields=[
                    "device_name", "serial_number", "hostname",
                    "management_ip", "mac_address",
                ],
                keyword=keyword,
                filters=filters if filters else None,
                exclude_filters=exclude_filters if exclude_filters else None,
                page=page,
                page_size=page_size,
                joins=joins,
                join_search_fields=join_search_fields,
                distinct=True,
            )

            data_ids = [d.id for d in result["data"]]
            if data_ids:
                loaded = (
                    self._base_query()
                    .filter(Device.id.in_(data_ids))
                    .options(joinedload(Device.switch_credential))
                    .order_by(Device.device_name)
                    .all()
                )
                result["data"] = loaded

            return result
        except SQLAlchemyError as e:
            raise QueryExecutionError("搜索设备失败", original_error=e)


    def check_u_position_conflict(
        self,
        cabinet_id: int,
        u_position: int,
        height_u: int,
        exclude_id: int = None,
    ) -> List[Device]:
        try:
            from app.models.device_server_ext import DeviceServerExt
            q = (
                self._base_query()
                .outerjoin(DeviceServerExt, DeviceServerExt.device_id == Device.id)
                .filter(
                    Device.cabinet_id == cabinet_id,
                    Device.u_position.isnot(None),
                    Device.height_u.isnot(None),
                    DeviceServerExt.parent_device_id.is_(None),
                    Device.status != DeviceStatus.SCRAPPED,
                    Device.u_position < u_position + height_u,
                    u_position < Device.u_position + Device.height_u,
                )
            )
            if exclude_id:
                q = q.filter(Device.id != exclude_id)
            return q.all()
        except SQLAlchemyError as e:
            raise QueryExecutionError("检查 U 位冲突失败", original_error=e)


    @monitor_query_performance
    def get_room_device_statistics(self, room_id: int) -> Dict[str, int]:
        try:
            from app.models.cabinet import Cabinet

            result = (
                self._base_query()
                .with_entities(
                    func.count(Device.id).label("device_count"),
                    func.sum(func.coalesce(Device.height_u, 0)).label("used_u"),
                )
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .filter(
                    Cabinet.room_id == room_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .first()
            )

            type_stats = (
                self._base_query()
                .with_entities(
                    Device.device_type,
                    func.count(Device.id).label("count"),
                )
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .filter(
                    Cabinet.room_id == room_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .group_by(Device.device_type)
                .all()
            )

            type_statistics = {"网络设备": 0, "服务器": 0, "其他": 0}
            for stat in type_stats:
                dt = (stat.device_type or "").lower()
                if dt == "network":
                    type_statistics["网络设备"] += stat.count
                elif dt == "server":
                    type_statistics["服务器"] += stat.count
                else:
                    type_statistics["其他"] += stat.count

            type_u_stats = (
                self._base_query()
                .with_entities(
                    Device.device_type,
                    Device.height_u,
                    func.count(Device.id).label("count"),
                )
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .filter(
                    Cabinet.room_id == room_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .group_by(Device.device_type, Device.height_u)
                .all()
            )

            type_u_statistics = {"网络设备": {}, "服务器": {}, "其他": {}}
            for stat in type_u_stats:
                dt = (stat.device_type or "").lower()
                if dt == "network":
                    cat = "网络设备"
                elif dt == "server":
                    cat = "服务器"
                else:
                    cat = "其他"
                u_key = f"{stat.height_u or 1}U"
                type_u_statistics[cat][u_key] = (
                    type_u_statistics[cat].get(u_key, 0) + stat.count
                )

            return {
                "device_count":      result.device_count or 0,
                "used_u":            int(result.used_u or 0),
                "type_statistics":   type_statistics,
                "type_u_statistics": type_u_statistics,
            }
        except SQLAlchemyError as e:
            logger.error(f"获取机房设备统计失败 (room_id={room_id}): {e}")
            raise QueryExecutionError("获取机房设备统计失败", original_error=e)


    def sync_chassis_nodes(self, chassis_id: int, changed_params: Dict[str, Any]) -> bool:
        try:
            nodes = self.find_child_devices(chassis_id)
            if not nodes:
                return True

            syncable    = {"brand", "device_model", "cabinet_id", "customer_id"}
            hw_syncable = {"cpu", "cpu_way", "memory"}
            hw_fields   = {f: changed_params[f] for f in hw_syncable if f in changed_params}

            chassis_name = changed_params.get("device_name")
            auto_name_pattern = re.compile(r"^.+-Node\d+$")

            for node in nodes:
                for field in syncable:
                    if field in changed_params:
                        setattr(node, field, changed_params[field])

                if hw_fields and node.hardware:
                    for f, v in hw_fields.items():
                        setattr(node.hardware, f, v)

                if chassis_name and auto_name_pattern.match(node.device_name or ""):
                    node.device_name = f"{chassis_name}-Node{node.node_position}"
                    node.notes = f"{chassis_name}的第{node.node_position}个节点"

            self.session.flush()
            logger.info(f"同步机箱 {chassis_id} 参数到 {len(nodes)} 个节点")
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("同步机箱节点失败", original_error=e)


    def count_active_devices(self) -> int:
        try:
            return (
                self._base_query()
                .filter(
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计设备数量失败", original_error=e)

    def count_by_cabinet(self, cabinet_id: int) -> int:
        try:
            return (
                self._base_query()
                .filter(
                    Device.cabinet_id == cabinet_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计设备数量失败", original_error=e)

    def count_by_room(self, room_id: int) -> int:
        try:
            from app.models.cabinet import Cabinet
            return (
                self._base_query()
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .filter(
                    Cabinet.room_id == room_id,
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计设备数量失败", original_error=e)

    def count_by_status(self, status) -> int:
        try:
            return (
                self._base_query()
                .filter(
                    Device.status == status,
                )
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计设备数量失败", original_error=e)

    def count_switches(self) -> int:
        try:
            return (
                self._base_query()
                .filter(
                    or_(
                        Device.device_subtype.ilike('%switch%'),
                        Device.device_type.ilike('%switch%'),
                    ),
                )
                .count()
            )
        except SQLAlchemyError as e:
            raise QueryExecutionError("统计交换机数量失败", original_error=e)

    def create(self, data: Dict[str, Any]) -> Device:
        try:
            safe_data = {k: v for k, v in data.items() if k in self._WRITABLE_FIELDS}
            device = Device(**safe_data)
            self.session.add(device)
            self.session.flush()
            return device
        except SQLAlchemyError as e:
            raise QueryExecutionError("创建设备失败", original_error=e)

    def update(self, device_id: int, data: Dict[str, Any]) -> Optional[Device]:
        try:
            device = self.find_by_id(device_id)
            if not device:
                return None
            for k, v in data.items():
                if k in self._WRITABLE_FIELDS:
                    setattr(device, k, v)
            self.session.flush()
            return device
        except SQLAlchemyError as e:
            raise QueryExecutionError("更新设备失败", original_error=e)

    def delete(self, device_id: int) -> bool:
        return super().delete(device_id)

    def batch_update_status(self, device_ids: List[int], new_status: int) -> int:
        if not device_ids:
            return 0
        try:
            count = (
                self._base_query()
                .filter(Device.id.in_(device_ids))
                .update({"status": new_status}, synchronize_session=False)
            )
            self.session.flush()
            return count
        except SQLAlchemyError as e:
            raise QueryExecutionError("批量更新状态失败", original_error=e)

    def update_location(self, device_id: int, cabinet_id: int) -> bool:
        try:
            device = self._base_query().filter(Device.id == device_id).first()
            if not device:
                return False
            device.cabinet_id = cabinet_id
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            raise QueryExecutionError("更新设备位置失败", original_error=e)

    def check_management_ip_exists(self, ip_address: str, exclude_id: int = 0) -> bool:
        if not ip_address:
            return False
        try:
            query = self._base_query().filter(Device.management_ip == ip_address)
            if exclude_id:
                query = query.filter(Device.id != exclude_id)
            return self.session.query(query.exists()).scalar()
        except SQLAlchemyError as e:
            raise QueryExecutionError("校验管理IP失败", original_error=e)

    def check_device_name_duplicate(self, device_name: str, cabinet_id: int = None, exclude_id: int = 0) -> Optional[Device]:
        if not device_name:
            return None
        try:
            query = self._base_query().filter(Device.device_name == device_name)
            from app.core.enums import DeviceStatus
            query = query.filter(Device.status != DeviceStatus.SCRAPPED)
            if cabinet_id:
                query = query.filter(Device.cabinet_id == cabinet_id)
            if exclude_id:
                query = query.filter(Device.id != exclude_id)
            return query.first()
        except SQLAlchemyError as e:
            raise QueryExecutionError("校验设备名称失败", original_error=e)

    def check_serial_number_exists(self, serial_number: str, exclude_id: int = None) -> bool:
        if not serial_number:
            return False
        try:
            q = self._base_query().filter(Device.serial_number == serial_number)
            from app.core.enums import DeviceStatus
            q = q.filter(Device.status != DeviceStatus.SCRAPPED)
            if exclude_id:
                q = q.filter(Device.id != exclude_id)
            return self.session.query(q.exists()).scalar()
        except SQLAlchemyError as e:
            raise QueryExecutionError("校验序列号失败", original_error=e)

    def generate_unique_serial_number(
        self, prefix="SN", format_type="timestamp", length=16, max_retries=10
    ) -> str:
        for _ in range(max_retries):
            if format_type == "timestamp":
                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                sn = f"{prefix}{ts}{''.join(str(random.randint(0,9)) for _ in range(4))}"
            elif format_type == "uuid":
                sn = f"{prefix}{str(uuid.uuid4()).upper()}" if prefix else str(uuid.uuid4()).upper()
            elif format_type == "random":
                sn = f"{prefix}{''.join(str(random.randint(0,9)) for _ in range(length))}"
            elif format_type == "custom":
                date = datetime.now().strftime("%Y%m%d")
                sn = f"{prefix}{date}{''.join(str(random.randint(0,9)) for _ in range(6))}"
            else:
                raise ValueError(f"不支持的 format_type: {format_type}")
            if not self.check_serial_number_exists(sn):
                return sn
        raise RuntimeError(f"无法生成唯一序列号，已重试 {max_retries} 次")

    @monitor_query_performance
    def get_device_statistics(self) -> Dict[str, Any]:
        try:
            basic = self._base_query().with_entities(
                func.count(Device.id).label("total"),
                func.sum(case((Device.status == DeviceStatus.ONLINE, 1), else_=0)).label("online"),
                func.sum(case((Device.status == DeviceStatus.AVAILABLE, 1), else_=0)).label("available"),
                func.sum(case((Device.status == DeviceStatus.OFFLINE, 1), else_=0)).label("offline"),
                func.sum(case((Device.status == DeviceStatus.MAINTENANCE, 1), else_=0)).label("maintenance"),
                func.sum(case((Device.status == DeviceStatus.RESERVED, 1), else_=0)).label("reserved"),
                func.sum(case((Device.power.isnot(None), Device.power), else_=0)).label("total_power"),
                func.avg(case((Device.power.isnot(None), Device.power), else_=None)).label("avg_power"),
            ).first()

            status_rows = (
                self._base_query().with_entities(Device.status, func.count(Device.id))
                .group_by(Device.status).all()
            )
            type_rows = (
                self._base_query().with_entities(Device.device_type, func.count(Device.id))
                .filter(Device.status != DeviceStatus.SCRAPPED)
                .group_by(Device.device_type).all()
            )

            from app.models.cabinet import Cabinet
            cabinet_rows = (
                self.session.query(Cabinet.cabinet_number, func.count(Device.id).label("cnt"))
                .join(Device, Cabinet.id == Device.cabinet_id)
                .filter(
                    Cabinet.deleted_at.is_(None),
                    Device.status != DeviceStatus.SCRAPPED,
                )
                .group_by(Cabinet.id, Cabinet.cabinet_number).all()
            )

            return {
                "total_devices":       basic.total or 0,
                "online_devices":      basic.online or 0,
                "available_devices":   basic.available or 0,
                "offline_devices":     basic.offline or 0,
                "maintenance_devices": basic.maintenance or 0,
                "reserved_devices":    basic.reserved or 0,
                "status_statistics":   {DeviceStatus.STATUS_NAMES.get(s, f"状态{s}"): c for s, c in status_rows},
                "type_statistics":     {t or "unknown": c for t, c in type_rows},
                "cabinet_statistics":  {cn: c for cn, c in cabinet_rows},
                "power_statistics": {
                    "total_power":   float(basic.total_power or 0),
                    "average_power": round(float(basic.avg_power or 0), 2),
                },
            }
        except SQLAlchemyError as e:
            raise QueryExecutionError("获取统计信息失败", original_error=e)


    @monitor_query_performance
    def get_deleted_devices(
        self,
        page: int = 1,
        page_size: int = 20,
        start_date=None,
        end_date=None,
        room_id: int = None,
        cabinet_id: int = None,
        device_type: str = None,
        ip_search: str = None,
    ) -> Dict[str, Any]:
        try:
            from app.models.device_hardware import DeviceHardware
            from app.models.cabinet import Cabinet

            query = (
                self.session.query(Device)
                .outerjoin(DeviceHardware, DeviceHardware.device_id == Device.id)
                .filter(Device.deleted_at.isnot(None))
            )

            if start_date:
                query = query.filter(Device.deleted_at >= start_date)
            if end_date:
                query = query.filter(Device.deleted_at <= end_date)

            if cabinet_id:
                query = query.filter(Device.cabinet_id == cabinet_id)
            elif room_id:
                query = query.filter(
                    func.json_extract(
                        DeviceHardware.device_config,
                        "$.deleted_location_snapshot.room_id"
                    ) == str(room_id)
                )

            if device_type:
                query = query.filter(Device.device_type == device_type)

            if ip_search:
                ip_pattern = f"%{ip_search}%"
                hw_ip_match = DeviceHardware.ip_address.cast(db.Text).ilike(ip_pattern)
                query = query.filter(
                    or_(
                        Device.management_ip.ilike(ip_pattern),
                        DeviceHardware.ipmi_address.ilike(ip_pattern),
                        hw_ip_match,
                    )
                )

            total = (
                query.with_entities(func.count(distinct(Device.id))).scalar() or 0
            )
            total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
            page = max(1, min(page, total_pages or 1))
            offset = (page - 1) * page_size

            devices = (
                query
                .options(joinedload(Device.hardware), joinedload(Device.customer))
                .order_by(Device.deleted_at.desc())
                .limit(page_size)
                .offset(offset)
                .all()
            )

            devices_data = []
            for d in devices:
                dd = d.to_dict()
                if d.hardware and d.hardware.device_config:
                    dd['deleted_location_snapshot'] = d.hardware.device_config.get('deleted_location_snapshot')
                    dd['deleted_children_snapshot'] = d.hardware.device_config.get('deleted_children_snapshot')
                devices_data.append(dd)

            return {
                "devices": devices_data,
                "total": total,
                "total_pages": total_pages,
                "page": page,
                "page_size": page_size,
            }
        except SQLAlchemyError as e:
            raise QueryExecutionError("查询已删除设备失败", original_error=e)

    def get_child_device_ids(self, parent_device_id: int) -> list[int]:
        from app.models.device_server_ext import DeviceServerExt
        rows = self.session.query(DeviceServerExt.device_id).filter_by(
            parent_device_id=parent_device_id
        ).all()
        return [r[0] for r in rows if r[0] is not None]
