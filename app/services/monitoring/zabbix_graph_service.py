# -*- coding: utf-8 -*-
"""Zabbix 端口流量图形服务（方案 B：数据自绘，零落库）

用户需求：本系统**不存储**端口流量，交换机配置了 Zabbix API 时直接通过 API 调用
图形数据。本服务：

1. ``list_ports`` — ``item.get`` 按 host 查找端口流量 item，返回端口名列表（轻量，不拉历史）；
2. ``get_port_traffic`` — 按 port 名拉 ``history.get`` / ``trend.get`` 时间序列，**不落本系统 DB**。

复用 ``ZabbixAdapter`` 的 JSON-RPC 调用（``_zabbix_call``）与主机引用解析（``_resolve_host_ref``），
保证与现有 Zabbix 凭据结构（api_url / api_token / verify_ssl / match_by）一致。
"""
from app.services.monitoring.adapters.zabbix_adapter import ZabbixAdapter
from app.utils.logging import get_logger

import bisect

logger = get_logger(__name__)

_PORTS_CACHE: dict[int, tuple[list[dict], float]] = {}
_PORTS_CACHE_TTL = 60.0


def _to_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ZabbixGraphService:

    def __init__(self, adapter: ZabbixAdapter | None = None):
        self._adapter = adapter or ZabbixAdapter()


    def _resolve_hostid(self, api_url: str, credential: dict, device) -> str | None:
        host_ref = self._adapter._resolve_host_ref(device, credential)
        if not host_ref:
            return None
        try:
            hosts = self._adapter._zabbix_call(api_url, credential, "host.get", {
                "output": ["hostid", "host"],
                "selectInterfaces": ["ip"],
            }) or []
        except Exception:
            logger.warning("zabbix_graph host.get 失败 api_url=%s", api_url, exc_info=True)
            return None
        matched = next(
            (h for h in hosts
             if any(i.get("ip") == host_ref for i in h.get("interfaces", []))),
            None,
        )
        host = matched or (hosts[0] if hosts else None)
        return host.get("hostid") if host else None


    def list_ports(self, credential: dict, device, use_cache: bool = True) -> list[dict]:
        import time as _time
        device_id = getattr(device, "id", None)
        if use_cache and device_id is not None:
            cached = _PORTS_CACHE.get(device_id)
            if cached and cached[1] > _time.time():
                return cached[0]
        api_url = credential.get("api_url")
        if not api_url:
            return []
        hostid = self._resolve_hostid(api_url, credential, device)
        if not hostid:
            return []
        try:
            items = self._adapter._zabbix_call(api_url, credential, "item.get", {
                "hostids": hostid,
                "output": ["itemid", "name", "key_", "value_type", "units"],
                "search": {"key_": ["net.if.in[", "net.if.out["]},
                "searchByAny": True,
                "startSearch": True,
            }) or []
        except Exception:
            logger.warning("zabbix_graph item.get 失败 api_url=%s hostid=%s", api_url, hostid, exc_info=True)
            return []

        rx_items = [i for i in items if i.get("key_", "").startswith("net.if.in[")
                     and i.get("units") == "bps"]
        tx_items = [i for i in items if i.get("key_", "").startswith("net.if.out[")
                     and i.get("units") == "bps"]
        if not rx_items:
            rx_items = [i for i in items if i.get("key_", "").startswith("net.if.in[")]
        if not tx_items:
            tx_items = [i for i in items if i.get("key_", "").startswith("net.if.out[")]

        ports = []
        for rx in rx_items:
            port_name = self._extract_port_name(rx.get("name") or rx.get("key_", ""))
            tx = next((t for t in tx_items
                       if self._extract_port_name(t.get("name") or t.get("key_", "")) == port_name), None)
            if not tx:
                continue
            ports.append({
                "port": port_name,
                "rx_itemid": rx["itemid"],
                "tx_itemid": tx["itemid"],
                "rx_value_type": int(rx.get("value_type", 0)),
                "tx_value_type": int(tx.get("value_type", 0)),
            })
        if use_cache and device_id is not None:
            import time as _time
            _PORTS_CACHE[device_id] = (ports, _time.time() + _PORTS_CACHE_TTL)
        return ports


    def get_port_traffic(
        self,
        credential: dict,
        device,
        port: str,
        time_from: int,
        time_till: int,
        ports: list[dict] | None = None,
    ) -> dict:
        api_url = credential.get("api_url")
        if not api_url:
            return {"port": None, "time": [], "rx_bps": [], "tx_bps": []}

        port_list = ports if ports is not None else self.list_ports(credential, device)
        matched = next((p for p in port_list if p["port"] == port), None)
        if not matched:
            return {"port": None, "time": [], "rx_bps": [], "tx_bps": []}

        rx_points = self._pull_history(api_url, credential, matched["rx_itemid"],
                                       time_from, time_till, matched["rx_value_type"])
        tx_points = self._pull_history(api_url, credential, matched["tx_itemid"],
                                       time_from, time_till, matched["tx_value_type"])

        return self._align_series(port, rx_points, tx_points)

    @staticmethod
    def _align_series(port: str, rx_points: list, tx_points: list) -> dict:
        rx_map = {int(p["clock"]): _to_number(p["value"]) for p in rx_points if p.get("clock")}
        tx_map = {int(p["clock"]): _to_number(p["value"]) for p in tx_points if p.get("clock")}
        rx_clocks = sorted(rx_map)
        tx_clocks = sorted(tx_map)

        if len(rx_clocks) >= len(tx_clocks):
            time_keys = rx_clocks
            primary_map = rx_map
            other_clocks = tx_clocks
            other_map = tx_map
            primary_is_rx = True
        else:
            time_keys = tx_clocks
            primary_map = tx_map
            other_clocks = rx_clocks
            other_map = rx_map
            primary_is_rx = False

        primary_values = [primary_map.get(t) or 0 for t in time_keys]

        other_values = []
        for t in time_keys:
            if not other_clocks:
                other_values.append(0)
                continue
            idx = bisect.bisect_left(other_clocks, t)
            if idx == 0:
                nearest = other_clocks[0]
            elif idx == len(other_clocks):
                nearest = other_clocks[-1]
            else:
                t_left, t_right = other_clocks[idx - 1], other_clocks[idx]
                nearest = t_left if (t - t_left) <= (t_right - t) else t_right
            other_values.append(other_map.get(nearest) or 0)

        if primary_is_rx:
            rx_bps, tx_bps = primary_values, other_values
        else:
            rx_bps, tx_bps = other_values, primary_values

        return {
            "port": port,
            "time": time_keys,
            "rx_bps": rx_bps,
            "tx_bps": tx_bps,
        }


    def _pull_history(self, api_url: str, credential: dict, itemid: str,
                      time_from: int, time_till: int, value_type: int = 0) -> list:
        try:
            points = self._adapter._zabbix_call(api_url, credential, "history.get", {
                "itemids": itemid,
                "history": value_type,
                "time_from": time_from,
                "time_till": time_till,
                "sortfield": "clock",
                "sortorder": "ASC",
                "output": "extend",
                "limit": 5000,
            }) or []
            if points:
                return points
            trends = self._adapter._zabbix_call(api_url, credential, "trend.get", {
                "itemids": itemid,
                "time_from": time_from,
                "time_till": time_till,
                "output": "extend",
            }) or []
            return [
                {"clock": t.get("clock"), "value": t.get("value_avg") or t.get("value_max")}
                for t in trends
            ]
        except Exception:
            logger.warning("zabbix_graph history.get 失败 itemid=%s", itemid, exc_info=True)
            return []

    @staticmethod
    def _extract_port_name(label: str) -> str:
        label = label or ""
        if label.startswith("Interface ") and ":" in label:
            return label[len("Interface "):label.index(":")].strip()
        if "[" in label and label.endswith("]"):
            inner = label[label.index("[") + 1: -1]
            parts = [p.strip() for p in inner.split(",")]
            for p in reversed(parts):
                if p and not p.startswith(("bps", "ifHC", "ifIn", "ifOut")):
                    return p
        for prefix in ("Incoming network traffic on", "Outgoing network traffic on"):
            if label.startswith(prefix):
                port = label[len(prefix):].strip()
                return port or label
        return ""
