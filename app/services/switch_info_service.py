# -*- coding: utf-8 -*-
"""
交换机信息采集服务

从交换机采集版本、端口等信息并更新数据库。
采集端口信息写入 network_ports（统一端口表）。
"""
from app.utils.logging import get_logger
import re
from app.adapters.adapter_factory import get_adapter
from app.adapters.base_adapter import ParsedDeviceInfo
from app.core.enums import SwitchDeviceTypeCode
from app.infra import SSHManager
from app.persistence.switch_repo import SwitchRepository
from app.persistence.switch_port_repository import NetworkPortRepository
from app.utils.port_name_parser import parse_port_name

logger = get_logger(__name__)

class SwitchInfoService:
    """交换机信息采集服务"""

    def __init__(self, ssh_manager: SSHManager = None):
        self.ssh_mgr = ssh_manager or SSHManager()
        self.sw_repo = SwitchRepository()
        self.port_repo = NetworkPortRepository()

    def collect_device_info(self, device_id: int) -> dict:
        """采集交换机设备信息并更新数据库

        采集步骤：
        1. 执行 display version，由适配器解析 model / version / uptime
        2. 若适配器未能解析出序列号，则发送设备特定命令补充采集（支持多槽位框架交换机）
        3. 执行 display sysname / show hostname，解析主机名
        4. 将采集结果写回：model/serial/hostname → Device，version/uptime → SwitchCredentials

        Args:
            device_id: 交换机 device_id（devices.id，统一交换机标识）

        Returns:
            dict: {success, switch_id, info} 或 {success, switch_id, error}
        """
        switch = self.sw_repo.find_by_device_id(device_id)
        if not switch:
            raise ValueError(f"交换机 device_id={device_id} 不存在")

        adapter = get_adapter(switch.device_type)

        try:
            version_output = self.ssh_mgr.send_show_command(
                switch, adapter.get_version_command(),
            )
            info = adapter.parse_device_info(version_output)

            if not info.serial:
                info = self._collect_serial(switch, info)

            if not info.hostname:
                info = self._collect_hostname(switch, adapter, info)

            if info.model:
                switch.device.device_model = info.model
            if info.serial:
                switch.device.serial_number = info.serial
            if info.hostname:
                switch.device.hostname = info.hostname
            if info.brand:
                switch.device.brand = info.brand

            from app.models.switch_credentials import SwitchStatusCache
            cache = SwitchStatusCache.query.filter_by(device_id=device_id).first()
            if not cache:
                cache = SwitchStatusCache(device_id=device_id)
                self.sw_repo.session.add(cache)
            if info.version:
                cache.device_version = info.version
            if info.uptime:
                cache.device_uptime = info.uptime

            self.sw_repo.session.flush()
            return {"success": True, "switch_id": device_id, "info": info}

        except Exception as e:
            logger.error("采集交换机 device_id=%d 设备信息失败: %s", device_id, e)
            return {"success": False, "switch_id": device_id, "error": str(e)}

    def _collect_serial(
        self, switch, info: ParsedDeviceInfo,
    ) -> ParsedDeviceInfo:
        """补充采集序列号（当适配器版本解析未能获取 serial 时调用）

        华为设备：display esn（收集所有槽位 ESN）
        H3C 设备：display device manuinfo

        多槽位框架交换机的序列号以逗号拼接存储。

        Args:
            switch: 交换机对象
            info: 已解析的设备信息（serial 为空）

        Returns:
            ParsedDeviceInfo: 填充了 serial 字段的新实例（其余字段不变）
        """
        dt = (switch.device_type or "").lower()
        try:
            if SwitchDeviceTypeCode.HUAWEI in dt:
                esn_output = self.ssh_mgr.send_show_command(switch, "display esn")
                sns = re.findall(r'(?:ESN|SN)\s*(?:of\s+slot\s+\d+\s*)?:\s*(\S+)', esn_output)
            elif SwitchDeviceTypeCode.H3C in dt or "comware" in dt:
                esn_output = self.ssh_mgr.send_show_command(switch, "display device manuinfo")
                sns = re.findall(r'SN\s*[:\s]+(\S+)', esn_output)
            else:
                return info

            if sns:
                return ParsedDeviceInfo(
                    model=info.model,
                    version=info.version,
                    serial=",".join(sns),
                    uptime=info.uptime,
                    hostname=info.hostname,
                    brand=info.brand,
                )
        except Exception as e:
            logger.warning("补充采集序列号失败（非致命）device_id=%d: %s", switch.device_id, e)

        return info

    def _collect_hostname(
        self, switch, adapter, info: ParsedDeviceInfo,
    ) -> ParsedDeviceInfo:
        """采集交换机主机名

        通过 display sysname（华为/H3C）或 show hostname（Cisco）获取主机名。
        部分设备可能不支持该命令，此时静默跳过。

        Args:
            switch: 交换机对象（SwitchCredentials）
            adapter: 设备适配器实例
            info: 已解析的设备信息

        Returns:
            ParsedDeviceInfo: 填充了 hostname 字段的新实例
        """
        try:
            sysname_output = self.ssh_mgr.send_show_command(
                switch, adapter.get_sysname_command(),
            )
            hostname = adapter.parse_sysname(sysname_output)
            if hostname:
                return ParsedDeviceInfo(
                    model=info.model,
                    version=info.version,
                    serial=info.serial,
                    uptime=info.uptime,
                    hostname=hostname,
                    brand=info.brand,
                )
        except Exception as e:
            logger.warning("采集主机名失败（非致命）device_id=%d: %s", switch.device_id, e)

        return info

    def collect_port_info(self, device_id: int) -> dict:
        """采集交换机端口信息并增量更新

        Args:
            device_id: 交换机 device_id（devices.id，统一交换机标识）

        Returns:
            dict: {success, switch_id, port_count} 或 {success, switch_id, error}
        """
        switch = self.sw_repo.find_by_device_id(device_id)
        if not switch:
            raise ValueError(f"交换机 device_id={device_id} 不存在")

        adapter = get_adapter(switch.device_type)

        try:
            interface_output = self.ssh_mgr.send_show_command(
                switch, adapter.get_interface_command(),
            )
            parsed_ports = adapter.parse_ports(interface_output)

            port_rows = []
            for p in parsed_ports:
                parsed_name = parse_port_name(p.port)
                port_rows.append({
                    "device_id":   switch.device_id,
                    "port_name":   p.port,
                    "slot":        parsed_name["slot"],
                    "card":        parsed_name["card"],
                    "port_number": parsed_name["port_number"],
                    "port_type":   parsed_name["port_type"],   # "GE"/"10GE" 接口类型字符串
                    "link_status": p.status,                    # "up"/"down" 链路状态
                    "vlan":        p.vlan,
                    "mac":         p.mac,
                    "ip_address":  p.ip_address.split(",")[0].strip() if p.ip_address else None,
                    "speed":       p.speed,
                    "description": p.description,
                })
            self.port_repo.incremental_update(switch.device_id, port_rows)
            self._sync_port_ips(switch.device_id, parsed_ports)
            self._sync_vlan_trunk_bases(switch.device_id, parsed_ports, room_id=switch.device.cabinet.room_id if switch.device and switch.device.cabinet else None)
            self.sw_repo.session.flush()

            return {
                "success": True,
                "switch_id": device_id,
                "port_count": len(parsed_ports),
            }

        except Exception as e:
            logger.error("采集交换机 device_id=%d 端口信息失败: %s", device_id, e)
            return {"success": False, "switch_id": device_id, "error": str(e)}

    def _sync_port_ips(self, switch_id: int, parsed_ports) -> None:
        """将解析到的端口 IP 同步到 sw_info_ip 表（CIDR 或点分十进制均支持）

        修复：IP 为空的端口也调用 sync_port_ips（传空列表），利用其全量替换语义
        清理 sw_info_ip 中残留的旧 IP 记录，避免交换机删除端口 IP 后前端仍显示。
        """
        import ipaddress
        for p in parsed_ports:
            ip_list = []
            if p.ip_address:
                for ip_str in p.ip_address.split(","):
                    ip_str = ip_str.strip()
                    if not ip_str:
                        continue
                    try:
                        if "/" in ip_str:
                            iface = ipaddress.ip_interface(ip_str)
                            ip_addr = str(iface.ip)
                            mask = str(iface.network.netmask)
                            prefix = iface.network.prefixlen  # CR-PREFIX-UNIFY: 同步计算prefix
                        else:
                            ip_addr = ip_str
                            mask = "255.255.255.0"
                            prefix = 24  # CR-PREFIX-UNIFY: 默认/24
                        ip_list.append({
                            "ip_address": ip_addr,
                            "subnet_mask": mask,
                            "prefix": prefix,  # CR-PREFIX-UNIFY
                            "is_primary": len(ip_list) == 0,
                        })
                    except (ValueError, TypeError):
                        continue
            self.sw_repo.sync_port_ips(switch_id, p.port, ip_list)

    def _sync_vlan_trunk_bases(self, device_id: int, parsed_ports,
                               room_id: int = None) -> None:
        """扫描时将 Vlanif/Eth-Trunk 端口同步写入 vlans/link_aggregation_groups 基础记录

        仅写入 device_id + vlan_id/lag_name 等基础字段，不获取成员列表（避免额外SSH开销）。
        成员列表在用户点击端口详情时按需 SSH 获取并缓存。
        若记录已存在则跳过，保留已有的 member_ports 缓存。
        同时清理设备上已不存在的 Vlanif/Eth-Trunk 对应的残留记录。
        """
        from app.models.vlan import VLAN
        from app.models.link_aggregation import LinkAggregationGroup
        from sqlalchemy import delete as sa_delete

        session = self.sw_repo.session
        scanned_vlan_ids = set()
        scanned_lag_names = set()

        for p in parsed_ports:
            port_name = p.port
            if not port_name:
                continue

            if re.match(r"^(?:vlan|vlanif|vlan-interface)\d+$", port_name, re.IGNORECASE):
                vlan_id = int(re.search(r"\d+", port_name).group())
                scanned_vlan_ids.add(vlan_id)
                from app.services.vlan_service import VLANService
                from app.persistence.vlan_repository import VLANRepository
                VLANService(VLANRepository()).ensure_vlan(device_id, vlan_id, name=port_name, room_id=room_id)

            elif re.match(r"^(?:eth-trunk|bridge-aggregation|port-channel)\d+$", port_name, re.IGNORECASE):
                scanned_lag_names.add(port_name)
                existing = session.query(LinkAggregationGroup).filter(
                    LinkAggregationGroup.device_id == device_id,
                    LinkAggregationGroup.lag_name == port_name,
                ).first()
                if not existing:
                    session.add(LinkAggregationGroup(
                        device_id=device_id,
                        lag_name=port_name,
                        status=1,
                        purpose='',
                    ))
                    logger.debug("扫描同步: 新增 LAG 基础记录 device_id=%d lag_name=%s", device_id, port_name)

        if scanned_vlan_ids:
            from app.models.vlan_port_member import VLANPortMember
            stale_vlans = session.query(VLAN).filter(
                VLAN.device_id == device_id,
                VLAN.vlan_id.notin_(scanned_vlan_ids),
            ).all()

            for vlan in stale_vlans:
                logger.debug(
                    "扫描同步: VLAN %d 已从设备消失，清理记录 device_id=%d",
                    vlan.vlan_id, device_id,
                )
                session.delete(vlan)

            del_count = len(stale_vlans)
            if del_count:
                logger.debug("扫描同步: 清理残留 VLAN 记录 device_id=%d count=%d", device_id, del_count)
        if scanned_lag_names:
            del_count = session.execute(
                sa_delete(LinkAggregationGroup).where(
                    LinkAggregationGroup.device_id == device_id,
                    LinkAggregationGroup.lag_name.notin_(scanned_lag_names),
                )
            ).rowcount
            if del_count:
                logger.debug("扫描同步: 清理残留 LAG 记录 device_id=%d count=%d", device_id, del_count)

        session.flush()
