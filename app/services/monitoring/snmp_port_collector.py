# -*- coding: utf-8 -*-
"""SNMP 端口采集器（SnmpPortCollector）

用 IF-MIB 通过 SNMP 采集网络设备的端口列表 + 链路状态，输出与 SSH 适配器
``parse_ports`` 相同结构的 ``port_rows``，供 ``NetworkPortRepository.incremental_update``
三步事务消费。

采集的 OID（均为 IF-MIB 标准表，pysnmp 自带）：
- ifName（1.3.6.1.2.1.31.1.1.1.1）：端口名，如 "GigabitEthernet0/0/1"
- ifOperStatus（1.3.6.1.2.1.2.2.1.8）：操作状态 up(1)/down(2)/testing(3)/unknown(4)/dormant(5)
- ifAdminStatus（1.3.6.1.2.1.2.2.1.7）：管理状态 up(1)/down(2)/testing(3)
- ifSpeed（1.3.6.1.2.1.2.2.1.5）：端口速率（bps）
- ifDescr（1.3.6.1.2.1.2.2.1.2）：端口描述（ifName 缺失时兜底）

所有 OID 以 ifIndex 为尾缀索引，跨表按 ifIndex 对齐。

设计要点：
- 复用 ``snmp_adapter._snmp_walk_table_async`` / ``_snmp_collect_metrics`` 的同步边界
  + 防挂死模式，避免重复实现。
- 采集失败静默降级返回空列表，不阻断主探测流程。
- 输出 ``port_rows`` 字段与 ``SwitchInfoService.collect_port_info`` 对齐，使
  ``incremental_update`` 消费方无感知。
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.monitoring.adapters.base_adapter import (
    monitor_timeout_seconds,
    run_with_timeout,
)
from app.services.monitoring.adapters.snmp_adapter import (
    _snmp_collect_metrics,
    _snmp_walk_table_async,
)
from app.utils.port_name_parser import parse_port_name

logger = logging.getLogger(__name__)

_IF_NAME_OID = "1.3.6.1.2.1.31.1.1.1.1"
_IF_DESCR_OID = "1.3.6.1.2.1.2.2.1.2"
_IF_OPER_STATUS_OID = "1.3.6.1.2.1.2.2.1.8"
_IF_ADMIN_STATUS_OID = "1.3.6.1.2.1.2.2.1.7"
_IF_SPEED_OID = "1.3.6.1.2.1.2.2.1.5"

_OPER_STATUS_MAP = {
    "1": "up",
    "2": "down",
    "3": "testing",
    "4": "unknown",
    "5": "dormant",
    "6": "notPresent",
    "7": "lowerLayerDown",
}
_ADMIN_STATUS_MAP = {
    "1": "up",
    "2": "down",
    "3": "testing",
}

def _speed_bps_to_label(speed_bps: str) -> str:
    try:
        bps = int(speed_bps)
    except (ValueError, TypeError):
        return ""
    if bps <= 0:
        return ""
    gbps = bps / 1_000_000_000
    if gbps >= 200:
        return "200G"
    if gbps >= 100:
        return "100G"
    if gbps >= 50:
        return "50G"
    if gbps >= 40:
        return "40G"
    if gbps >= 25:
        return "25G"
    if gbps >= 10:
        return "10G"
    if gbps >= 1:
        return "1G"
    if bps >= 100_000_000:
        return "100M"
    if bps >= 10_000_000:
        return "10M"
    return ""


def _resolve_link_status(oper_status: str, admin_status: str) -> str:
    admin = _ADMIN_STATUS_MAP.get(admin_status, admin_status)
    oper = _OPER_STATUS_MAP.get(oper_status, oper_status)
    if admin == "down":
        return "admin_down"
    if admin == "up" and oper == "up":
        return "up"
    if admin == "up" and oper == "down":
        return "down"
    return oper


class SnmpPortCollector:

    def collect(self, credential: dict, ip: str, timeout: int | None = None, device=None) -> list[dict]:
        snmp_timeout = timeout if timeout is not None else monitor_timeout_seconds()

        templates = [
            {"metric_key": "ifName", "oid": _IF_NAME_OID},
            {"metric_key": "ifDescr", "oid": _IF_DESCR_OID},
            {"metric_key": "ifOperStatus", "oid": _IF_OPER_STATUS_OID},
            {"metric_key": "ifAdminStatus", "oid": _IF_ADMIN_STATUS_OID},
            {"metric_key": "ifSpeed", "oid": _IF_SPEED_OID},
        ]
        ok, raw, _elapsed = run_with_timeout(
            lambda: _snmp_collect_metrics(credential, ip, templates, snmp_timeout),
            snmp_timeout + 3,
        )
        if not ok or not isinstance(raw, dict):
            return []

        if_name_table = raw.get("ifName", {})
        if_descr_table = raw.get("ifDescr", {})
        if_oper_table = raw.get("ifOperStatus", {})
        if_admin_table = raw.get("ifAdminStatus", {})
        if_speed_table = raw.get("ifSpeed", {})

        if not if_name_table and not if_descr_table:
            return []

        name_table = dict(if_descr_table)
        name_table.update(if_name_table)

        port_rows: list[dict] = []
        for if_index, port_name in name_table.items():
            if not port_name:
                continue
            parsed = parse_port_name(port_name)
            port_type = parsed.get("port_type")
            if port_type in ("VLAN", "ETH-TRUNK", "LOOPBACK", "NULL"):
                continue
            if not parsed.get("parsed"):
                logger.debug(
                    "SNMP 端口采集：端口名无法解析，跳过 ifIndex=%s port_name=%s",
                    if_index, port_name,
                )
                continue

            oper_status = if_oper_table.get(if_index, "")
            admin_status = if_admin_table.get(if_index, "")
            link_status = _resolve_link_status(oper_status, admin_status)
            speed = _speed_bps_to_label(if_speed_table.get(if_index, ""))

            port_rows.append({
                "port_name": port_name,
                "port_type": port_type,
                "slot": parsed["slot"],
                "card": parsed["card"],
                "port_number": parsed["port_number"],
                "link_status": link_status,
                "speed": speed,
                "description": None,
                "vlan": None,
                "mac": None,
                "ip_address": None,
            })

        return port_rows
