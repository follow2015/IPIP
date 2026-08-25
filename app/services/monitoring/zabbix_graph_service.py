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
    """把 Zabbix 返回的字符串数值转为 float/int，无法解析返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ZabbixGraphService:
    """Zabbix 端口流量图形服务（只读拉取，不落库）"""

    def __init__(self, adapter: ZabbixAdapter | None = None):
        self._adapter = adapter or ZabbixAdapter()


    def _resolve_hostid(self, api_url: str, credential: dict, device) -> str | None:
        """按设备 IP 匹配 Zabbix host，返回 hostid。"""
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
        """返回设备所有有流量 item 的端口列表。

        返回 ``[{"port": 接口名, "rx_itemid": "...", "tx_itemid": "..."}, ...]``

        ``use_cache=True`` 时按 device.id 做 60s TTL 缓存，避免同一设备短时间内
        重复调用 host.get + item.get（如 /traffic/ports 紧接 /traffic）。
        """
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
        """按端口名返回 rx/tx 流量时间序列。

        返回 ``{"port": 接口名, "time": [...], "rx_bps": [...], "tx_bps": [...]}``

        ``ports`` 可传入已拉取的端口列表（来自 ``list_ports``），避免重复调用
        ``host.get`` + ``item.get``。为 None 时内部自行调用 ``list_ports``。
        """
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
        """对齐 rx/tx 时间序列。

        Zabbix 的 net.if.in / net.if.out 是两个独立 item，首采时间相差几秒到几十秒，
        在固定采样周期下会形成永久相位差（如设备 107 实测 rx/tx 相差 21s，周期 180s，
        永不重合）。旧逻辑取 clock 并集 + 缺失填 0，会导致每个时间点只有一条线有值、
        另一条线被强制置 0，图表呈锯齿状跳变。

        改进策略：
        - 以点数较多的一方作为主时间轴（通常 rx/tx 点数相同，任选其一）
        - 另一方用最近邻插值对齐到主轴（21s 偏移在 180s 周期内误差 < 3%）
        - 主轴缺失的点（一方完全无数据）才填 0
        - 双方都无数据时返回空序列
        """
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
        """拉取单个 item 的数值历史（优先 history.get，空则 trend.get）。"""
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
        """从 item name / key 提取接口名。

        支持格式：
        - ``Interface 10GE1/0/6(): Bits received`` → ``10GE1/0/6()``
        - ``Incoming network traffic on GigabitEthernet1/0/1`` → ``GigabitEthernet1/0/1``
        - ``net.if.in[bps,ifHCInOctets,GigabitEthernet1/0/1]`` → ``GigabitEthernet1/0/1``
        """
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
