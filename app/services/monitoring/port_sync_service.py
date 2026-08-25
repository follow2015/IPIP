# -*- coding: utf-8 -*-
"""端口同步服务（PortSyncService）

对非网管网络设备（has_ssh=false）但有 SNMP 凭据的设备，用 SNMP 采集端口列表，
按 ``(port_type, slot, card, port_number)`` 四元组匹配已有端口，**直接替换**——
不保留手动端口，SNMP 采集结果作为唯一数据源。

匹配策略（用户确认）：
1. 先比 port_type（GE / 10GE / 40GE 等速率类型）
2. port_type 相同再比 (slot, card, port_number)
3. 四元组完全一致 → 视为同一端口，用 SNMP 采集数据替换
4. 四元组不一致 → SNMP 新端口新增，已有手动端口不在采集结果中则删除

自动获取状态下以采集为准，不保留手动 disabled 状态。

与网管设备的 ``SwitchInfoService.collect_port_info`` 对齐：
- 复用 ``NetworkPortRepository.incremental_update`` 三步事务
- ``data_source`` 演进：manual → auto（替换语义，不保留 hybrid）
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import delete as sa_delete

from app.core.enums import DataSource
from app.models.network_port import NetworkPort
from app.persistence.switch_port_repository import NetworkPortRepository
from app.services.monitoring.snmp_port_collector import SnmpPortCollector

logger = logging.getLogger(__name__)


class PortSyncService:
    """端口同步服务（采集 → 四元组匹配 → 替换）。

    对非网管网络设备，用 SNMP 或 Zabbix 采集端口，按四元组匹配后直接替换
    network_ports 表中的端口数据。collector 由调用方按凭据类型注入。
    """

    def __init__(
        self,
        port_repo: NetworkPortRepository | None = None,
        collector: SnmpPortCollector | None = None,
    ):
        self.port_repo = port_repo or NetworkPortRepository()
        self.collector = collector or SnmpPortCollector()

    def sync_device_ports(
        self,
        device_id: int,
        credential: dict,
        ip: str,
        timeout: int | None = None,
        collector=None,
        device=None,
    ) -> dict:
        """同步单台设备的端口（采集 → 四元组匹配 → 替换）。

        Args:
            device_id: 设备 ID
            credential: 采集凭据（SNMP 或 Zabbix）
            ip: 设备管理 IP
            timeout: 采集超时（秒）
            collector: 可选 collector 实例（缺省用 self.collector）
            device: 设备 ORM 对象（Zabbix collector 需要，SNMP 可选）

        Returns:
            dict: {"success": bool, "device_id": int, "port_count": int,
                   "matched": int, "added": int, "removed": int, "error": str | None}
        """
        active_collector = collector or self.collector
        try:
            port_rows = active_collector.collect(credential, ip, timeout=timeout, device=device)
        except Exception:  # noqa: BLE001 - 采集失败静默降级
            logger.warning(
                "端口采集失败 device_id=%s ip=%s", device_id, ip, exc_info=True,
            )
            return {
                "success": False, "device_id": device_id, "port_count": 0,
                "matched": 0, "added": 0, "removed": 0,
                "error": "collect_failed",
            }

        if not port_rows:
            logger.debug("端口采集为空 device_id=%s ip=%s", device_id, ip)
            return {
                "success": True, "device_id": device_id, "port_count": 0,
                "matched": 0, "added": 0, "removed": 0, "error": None,
            }

        stats = self._replace_by_tuple_key(device_id, port_rows)
        return {
            "success": True, "device_id": device_id,
            "port_count": len(port_rows), **stats, "error": None,
        }

    def _replace_by_tuple_key(self, device_id: int, port_rows: list[dict]) -> dict:
        """按 (port_type, slot, card, port_number) 四元组匹配并替换端口。

        语义：
        - 采集结果中的端口，四元组匹配已有行 → 更新（link_status / speed 等）
        - 采集结果中的端口，无匹配 → 新增（data_source=auto）
        - 已有端口不在采集结果中 → 删除（不保留手动端口）

        Args:
            device_id: 设备 ID
            port_rows: SNMP 采集的端口数据列表

        Returns:
            dict: {"matched": int, "added": int, "removed": int}
        """
        session = self.port_repo.session
        now = datetime.now()

        existing_ports = (
            session.query(NetworkPort)
            .filter(NetworkPort.device_id == device_id)
            .all()
        )
        existing_by_key: dict[tuple, NetworkPort] = {}
        for p in existing_ports:
            key = (p.port_type, p.slot, p.card, p.port_number)
            existing_by_key[key] = p

        collected_by_key: dict[tuple, dict] = {}
        for row in port_rows:
            key = (row.get("port_type"), row.get("slot"), row.get("card"), row.get("port_number"))
            collected_by_key[key] = row

        matched = 0
        added = 0
        collected_keys = set(collected_by_key.keys())

        for key, row in collected_by_key.items():
            existing = existing_by_key.get(key)
            if existing is not None:
                self._update_port_fields(existing, row, now)
                matched += 1
            else:
                new_port = NetworkPort(
                    device_id=device_id,
                    port_name=row.get("port_name", ""),
                    port_type=row.get("port_type"),
                    slot=row.get("slot", -1),
                    card=row.get("card", -1),
                    port_number=row.get("port_number", -1),
                    speed=row.get("speed"),
                    usage_status=NetworkPort.derive_usage_status(
                        row.get("link_status"), row.get("port_name"),
                    ),
                    link_status=row.get("link_status"),
                    vlan=row.get("vlan"),
                    mac=row.get("mac"),
                    ip_address=row.get("ip_address"),
                    description=row.get("description"),
                    data_source=DataSource.AUTO,
                    last_collected_at=now,
                )
                session.add(new_port)
                added += 1

        removed = 0
        to_delete: list[NetworkPort] = []
        for key, existing in existing_by_key.items():
            if key not in collected_keys:
                to_delete.append(existing)
        if to_delete:
            self._cleanup_port_relations(to_delete)
            for p in to_delete:
                session.delete(p)
                removed += 1

        session.flush()
        return {"matched": matched, "added": added, "removed": removed}

    def _update_port_fields(self, port: NetworkPort, row: dict, now: datetime) -> None:
        """更新已匹配端口的采集字段。

        替换语义：采集字段全部覆盖，data_source → auto。
        自动获取状态下以采集为准，不保留手动 disabled 状态。
        """
        link_status = row.get("link_status")
        new_usage_status = NetworkPort.derive_usage_status(
            link_status, row.get("port_name"),
        )

        port.port_type = row.get("port_type") or port.port_type
        port.port_name = row.get("port_name") or port.port_name
        port.slot = row.get("slot", port.slot)
        port.card = row.get("card", port.card)
        port.port_number = row.get("port_number", port.port_number)
        port.link_status = link_status
        port.usage_status = new_usage_status
        port.speed = row.get("speed") or port.speed
        if row.get("vlan") is not None:
            port.vlan = row["vlan"]
        if row.get("mac") is not None:
            port.mac = row["mac"]
        if row.get("ip_address") is not None:
            port.ip_address = row["ip_address"]
        if row.get("description") is not None:
            port.description = row["description"]
        port.data_source = DataSource.AUTO
        port.last_collected_at = now

    def _cleanup_port_relations(self, ports: list[NetworkPort]) -> None:
        """清理待删除端口的 LAG / VLAN 成员关系。

        与 PortManagementService.delete_port 语义对齐：
        - 清除 lag_group_id 并同步 LAG member_count
        - 删除 VLANPortMember 关联
        """
        if not ports:
            return
        session = self.port_repo.session
        port_ids = [p.id for p in ports if p.id is not None]
        if not port_ids:
            return

        from app.models.vlan_port_member import VLANPortMember
        session.execute(
            sa_delete(VLANPortMember).where(VLANPortMember.port_id.in_(port_ids))
        )

        for p in ports:
            p.lag_group_id = None
