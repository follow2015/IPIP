# -*- coding: utf-8 -*-
"""Zabbix 端口采集器（ZabbixPortCollector）

通过 Zabbix API 采集网络设备的端口列表 + 链路状态，输出与 ``SnmpPortCollector``
相同结构的 ``port_rows``，供 ``PortSyncService`` 消费。

采集流程：
1. 复用 ``ZabbixGraphService.list_ports`` 获取有流量 item 的端口名列表
   （``net.if.in[<port>]`` / ``net.if.out[<port>]`` 配对）
2. 额外查 ``net.if.status[<port>]`` item 获取端口管理状态（1=up, 0=down）
3. 端口名经 ``parse_port_name`` 解析得四元组（port_type / slot / card / port_number）
4. 跳过逻辑端口（Vlanif / Eth-Trunk / LoopBack）和无法解析的端口名

与 ``SnmpPortCollector`` 输出字段完全对齐，使 ``PortSyncService._replace_by_tuple_key``
消费方无感知。

设计要点：
- 复用 ``ZabbixGraphService`` 的主机匹配 + JSON-RPC 调用，避免重复实现
- 采集失败静默降级返回空列表，不阻断主探测流程
- ``list_ports`` 自带 60s TTL 缓存，避免短时重复调用
"""
from __future__ import annotations

import logging

from app.services.monitoring.adapters.zabbix_adapter import ZabbixAdapter
from app.services.monitoring.zabbix_graph_service import ZabbixGraphService
from app.utils.port_name_parser import parse_port_name

logger = logging.getLogger(__name__)

_STATUS_ITEM_KEY_PREFIXES = ("net.if.status", "agent.ifstatus", "zabbix.if.status")


def _status_value_to_link_status(value) -> str:
    try:
        v = int(value)
    except (ValueError, TypeError):
        return "unknown"
    if v == 1:
        return "up"
    if v == 0:
        return "down"
    return "unknown"


class ZabbixPortCollector:

    def __init__(self, graph_service: ZabbixGraphService | None = None):
        self._graph_service = graph_service or ZabbixGraphService()

    def collect(self, credential: dict, ip: str, timeout: int | None = None, device=None) -> list[dict]:
        if device is None:
            return []
        try:
            port_items = self._graph_service.list_ports(credential, device, use_cache=True)
        except Exception:
            logger.warning(
                "Zabbix 端口列表采集失败 device_id=%s",
                getattr(device, "id", None), exc_info=True,
            )
            return []

        if not port_items:
            return []

        status_map = self._collect_port_status(credential, device)

        port_rows: list[dict] = []
        for item in port_items:
            port_name = item.get("port", "")
            if not port_name:
                continue

            parsed = parse_port_name(port_name)
            port_type = parsed.get("port_type")
            if port_type in ("VLAN", "ETH-TRUNK", "LOOPBACK", "NULL"):
                continue
            if not parsed.get("parsed"):
                logger.debug(
                    "Zabbix 端口采集：端口名无法解析，跳过 port_name=%s", port_name,
                )
                continue

            link_status = status_map.get(port_name, "unknown")

            port_rows.append({
                "port_name": port_name,
                "port_type": port_type,
                "slot": parsed["slot"],
                "card": parsed["card"],
                "port_number": parsed["port_number"],
                "link_status": link_status,
                "speed": "",
                "description": None,
                "vlan": None,
                "mac": None,
                "ip_address": None,
            })

        return port_rows

    def _collect_port_status(self, credential: dict, device) -> dict[str, str]:
        api_url = credential.get("api_url")
        if not api_url:
            return {}

        adapter = self._graph_service._adapter
        hostid = self._graph_service._resolve_hostid(api_url, credential, device)
        if not hostid:
            return {}

        for key_prefix in _STATUS_ITEM_KEY_PREFIXES:
            try:
                items = adapter._zabbix_call(api_url, credential, "item.get", {
                    "hostids": hostid,
                    "output": ["itemid", "name", "key_", "value_type"],
                    "search": {"key_": key_prefix},
                    "startSearch": True,
                }) or []
            except Exception:
                logger.warning(
                    "Zabbix 端口状态 item.get 失败 key_prefix=%s hostid=%s",
                    key_prefix, hostid, exc_info=True,
                )
                continue

            if not items:
                continue

            status_map: dict[str, str] = {}
            for item in items:
                itemid = item.get("itemid")
                value_type = int(item.get("value_type", 0))
                port_name = self._extract_port_from_status_item(
                    item.get("key_", "") or item.get("name", ""),
                )
                if not port_name:
                    continue
                try:
                    points = adapter._zabbix_call(api_url, credential, "history.get", {
                        "itemids": itemid,
                        "history": value_type,
                        "sortfield": "clock",
                        "sortorder": "DESC",
                        "limit": 1,
                        "output": "extend",
                    }) or []
                except Exception:
                    logger.warning(
                        "Zabbix 端口状态 history.get 失败 itemid=%s", itemid, exc_info=True,
                    )
                    continue
                if points:
                    status_map[port_name] = _status_value_to_link_status(points[0].get("value"))
            if status_map:
                return status_map

        return {}

    @staticmethod
    def _extract_port_from_status_item(label: str) -> str:
        label = label or ""
        if "[" in label and label.endswith("]"):
            inner = label[label.index("[") + 1: -1]
            parts = [p.strip() for p in inner.split(",")]
            for p in reversed(parts):
                if p and not p.startswith(("bps", "ifHC", "ifIn", "ifOut", "ifStatus")):
                    return p
        return ""
