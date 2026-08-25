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
    """端口匹配规则引擎

    负责校验端口连接的合法性，包括：
    - 端口类型匹配（电口连电口，光口连光口）
    - 端口速率匹配（速率必须一致）
    - 端口占用检查（端口不能重复连接）
    - 设备类型限制（按 link_type 校验）
    """

    NETWORK_DEVICE_TYPES = NETWORK_DEVICE_TYPES


    @staticmethod
    def validate_connection(
        source_port: DeviceNicsPort,
        target_port: DeviceNicsPort,
    ) -> Tuple[bool, str]:
        """校验两个端口是否可以建立连接

        规则：
          1. 端口类型必须相同（电口↔电口，光口↔光口）
          2. 源端口速率不超过目标端口速率（源≤目标）
          3. 两端端口均须处于 free 状态

        Args:
            source_port: 源端口（DeviceNicsPort 实例，设备侧）
            target_port: 目标端口（DeviceNicsPort 实例，网络设备侧）

        Returns:
            (is_valid, error_message)
        """
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
        """将速率字符串解析为 Mbps 整数值

        支持格式：10G/10GE/1G/1GE/100M/100ME/1000M/10000M/10Gbps/1Gbps/10T/10TE 等

        Args:
            speed_str: 速率字符串

        Returns:
            Mbps 整数值，无法解析时返回 None
        """
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
        """检查端口是否已被某条 active 连接占用

        Args:
            port_id: device_nics_port 主键

        Returns:
            True = 已占用
        """
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
        """校验设备类型组合是否允许建立连接

        重构修复（Bug #11）：
          原版只允许 server↔switch，路由器/防火墙被错误拒绝。
          现在使用 NETWORK_DEVICE_TYPES 集合做统一判断。

        Args:
            source_device_type: 源设备类型（如 'server'）
            target_device_type: 目标设备类型（如 'switch'/'router'）
            link_type: 连接模式
                - 'device_to_network'  服务器↔网络设备（默认）
                - 'network_to_network' 网络设备间互联

        Returns:
            (is_valid, error_message)
        """
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
        """获取设备的可用端口（BUG-4 修复：消除 N+1 查询）

        Args:
            device_id:  设备 ID
            port_type:  端口类型过滤（可选）
            port_speed: 端口速率过滤（可选）

        Returns:
            DeviceNicsPort 实例列表
        """
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
        """查找两台设备间可匹配的端口对

        匹配规则：
          - 端口类型必须相同
          - 源端口速率≤目标端口速率（源=设备侧，目标=网络设备侧）
          - 两端均可用

        Args:
            source_device_id: 源设备 ID
            target_device_id: 目标设备 ID
            port_type:  可选类型过滤
            port_speed: 可选速率过滤

        Returns:
            匹配端口对列表，每项包含 source/target 端口 ID 及显示信息
        """
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
        """占用端口（事务由 API 层 @transactional 统一管理）"""
        port.occupy()

    @staticmethod
    def release_port(port: DeviceNicsPort) -> None:
        """释放端口（事务由 API 层 @transactional 统一管理）"""
        port.release()
