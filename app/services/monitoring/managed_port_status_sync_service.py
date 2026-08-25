# -*- coding: utf-8 -*-
"""网管设备端口状态同步服务（ManagedPortStatusSyncService）

网管设备（has_ssh=True）的端口状态自动更新流程：
- 监控轮询用 SNMP/Zabbix 凭据采集端口列表
- 按 port_name 匹配 DB 端口
- 匹配命中 → 调用 PortStatusUpdateService 更新 link_status + 联动 usage_status
- 匹配不命中 → 产生 port_name_mismatch 告警
- 不增删端口（与 SSH 全量替换区分）

与 SSH 流程的关系：
- SSH 扫描（SwitchInfoService.collect_port_info → incremental_update）保留全量替换
- 本服务仅在监控轮询期间更新端口状态，不影响 SSH 扫描结果
- SSH 扫描负责端口增删和拓扑信息，本服务负责状态高频更新
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.services.monitoring.port_status_update_service import PortStatusUpdateService

logger = logging.getLogger(__name__)


class ManagedPortStatusSyncService:

    def __init__(self, status_service: PortStatusUpdateService | None = None):
        self._status_service = status_service or PortStatusUpdateService()

    def sync_device_port_status(
        self,
        device_id: int,
        port_rows: list[dict],
        now: datetime | None = None,
    ) -> dict:
        if now is None:
            now = datetime.now()

        if not port_rows:
            return {
                "success": True, "device_id": device_id,
                "collected_count": 0, "updated": 0, "unchanged": 0,
                "not_found": [], "error": None,
            }

        port_status_map: dict[str, str | None] = {}
        for row in port_rows:
            port_name = row.get("port_name")
            if not port_name:
                continue
            port_status_map[port_name] = row.get("link_status")

        result = self._status_service.batch_update_status(
            device_id, port_status_map, now=now, emit_alert=True,
        )

        not_found = result["not_found"]
        if not_found:
            self._status_service.emit_port_name_mismatch_alert(device_id, not_found)

        return {
            "success": True,
            "device_id": device_id,
            "collected_count": len(port_status_map),
            "updated": result["updated"],
            "unchanged": result["unchanged"],
            "not_found": not_found,
            "error": None,
        }
