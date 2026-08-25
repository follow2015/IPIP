# -*- coding: utf-8 -*-
"""
端口匹配引擎

提供端口连接的匹配规则校验功能，确保连接的合法性。

重构说明（原 v1 → v2）
──────────────────────────────────────────────────────────────
原版问题：
  validate_device_type_for_connection 中硬编码
    "服务器只能连接 switch"
  导致服务器连路由器/防火墙时被错误拒绝（Bug #11）。
  同时 NETWORK_DEVICE_TYPES 与 device_connection_service 中
  各自独立维护，两处不同步时会产生矛盾。

重构后：
  ① NETWORK_DEVICE_TYPES 作为唯一权威集合，两处校验共用
  ② validate_device_type_for_connection 支持 link_type 参数，
     与 DeviceConnectionService._validate_device_type_for_link 对齐
  ③ 删除 find_matching_ports 中多余的 N×M 双重循环（改为单次过滤）
"""
from typing import Dict, List, Optional, Tuple

from app.models.device_nics_port import DeviceNicsPort
from app.models.device_connection import DeviceConnection


NETWORK_DEVICE_TYPES: frozenset = frozenset({'network'})


class PortMatchingEngine:

    NETWORK_DEVICE_TYPES = NETWORK_DEVICE_TYPES


    @staticmethod
    def validate_connection(
        source_port: DeviceNicsPort,
        target_port: DeviceNicsPort,
    ) -> Tuple[bool, str]:
        if source_port.port_type != target_port.port_type:
            return (
                False,
                f"端口类型不匹配: 源={source_port.port_type}，目标={target_port.port_type}"
                f"（{source_port.port_type} 只能连接 {source_port.port_type}）",
            )

        src_mbps = PortMatchingEngine._parse_speed_to_mbps(source_port.port_speed)
        tgt_mbps = PortMatchingEngine._parse_speed_to_mbps(target_port.port_speed)
        if src_mbps is not None and tgt_mbps is not None and src_mbps > tgt_mbps:
            return (
                False,
                f"源端口速率超出限制: {source_port.port_speed} ({src_mbps}Mbps) "
                f"> 目标端口 {target_port.port_speed} ({tgt_mbps}Mbps)",
            )

        if not source_port.is_available():
            return (False, f"源端口不可用（状态: {source_port.port_status}）")

        if not target_port.is_available():
            return (False, f"目标端口不可用（状态: {target_port.port_status}）")

        return (True, "校验通过")

    @staticmethod
    def _parse_speed_to_mbps(speed_str: str) -> Optional[int]:
        if not speed_str:
            return None
        import re
        s = speed_str.strip().upper().replace(" ", "")
        m = re.match(r'(\d+)', s)
        if not m:
            return None
        value = int(m.group(1))
        if 'T' in s:
            return value * 1_000_000
        if 'G' in s:
            return value * 1_000
        return value

    @staticmethod
    def check_port_occupied(port_id: int) -> bool:
        return (
            DeviceConnection.query
            .filter(
                DeviceConnection.device_nics_port_id == port_id,
                DeviceConnection.status == "active",
            )
            .first()
        ) is not None


    @staticmethod
    def validate_device_type_for_connection(
        source_device_type: str,
        target_device_type: str,
        link_type: str = "device_to_network",
    ) -> Tuple[bool, str]:
        nd = NETWORK_DEVICE_TYPES

        if link_type == "device_to_network":
            if source_device_type == "server" and target_device_type not in nd:
                return (
                    False,
                    f"服务器只能连接网络设备（{'/'.join(sorted(nd))}），"
                    f"目标设备类型为: {target_device_type}",
                )
            if source_device_type in nd and target_device_type != "server":
                return (
                    False,
                    f"网络设备侧只能连接服务器，目标设备类型为: {target_device_type}",
                )

        elif link_type == "network_to_network":
            if source_device_type not in nd:
                return (
                    False,
                    f"network_to_network 要求源设备为网络设备，当前: {source_device_type}",
                )
            if target_device_type not in nd:
                return (
                    False,
                    f"network_to_network 要求目标设备为网络设备，当前: {target_device_type}",
                )

        return (True, "")


    @staticmethod
    def get_available_ports(
        device_id: int,
        port_type: Optional[str] = None,
        port_speed: Optional[str] = None,
    ) -> List[DeviceNicsPort]:
        query = DeviceNicsPort.query.filter(
            DeviceNicsPort.device_id == device_id,
            DeviceNicsPort.port_status == "free",
        )
        if port_type:
            query = query.filter(DeviceNicsPort.port_type == port_type)
        if port_speed:
            query = query.filter(DeviceNicsPort.port_speed == port_speed)

        candidate_ports = query.all()
        if not candidate_ports:
            return []

        candidate_ids = [p.id for p in candidate_ports]
        occupied_ids = {
            row[0]
            for row in DeviceConnection.query
            .with_entities(DeviceConnection.device_nics_port_id)
            .filter(
                DeviceConnection.device_nics_port_id.in_(candidate_ids),
                DeviceConnection.status == "active",
            )
            .all()
        }

        return [p for p in candidate_ports if p.id not in occupied_ids]

    @staticmethod
    def find_matching_ports(
        source_device_id: int,
        target_device_id: int,
        port_type: Optional[str] = None,
        port_speed: Optional[str] = None,
    ) -> List[Dict]:
        source_ports = PortMatchingEngine.get_available_ports(
            source_device_id, port_type, port_speed
        )
        target_ports = PortMatchingEngine.get_available_ports(
            target_device_id, port_type, port_speed
        )

        target_by_type: Dict[str, List[DeviceNicsPort]] = {}
        for p in target_ports:
            target_by_type.setdefault(p.port_type, []).append(p)

        pairs: List[Dict] = []
        for sp in source_ports:
            candidates = target_by_type.get(sp.port_type, [])
            for tp in candidates:
                src_mbps = PortMatchingEngine._parse_speed_to_mbps(sp.port_speed)
                tgt_mbps = PortMatchingEngine._parse_speed_to_mbps(tp.port_speed)
                if src_mbps is not None and tgt_mbps is not None and src_mbps > tgt_mbps:
                    continue
                pairs.append({
                    "source_port_id":      sp.id,
                    "source_port_display": sp.full_info,
                    "target_port_id":      tp.id,
                    "target_port_display": tp.full_info,
                    "port_type":           sp.port_type,
                    "speed":               sp.port_speed,
                })

        return pairs


    @staticmethod
    def occupy_port(port: DeviceNicsPort) -> None:
        port.occupy()

    @staticmethod
    def release_port(port: DeviceNicsPort) -> None:
        port.release()
