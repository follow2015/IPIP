# -*- coding: utf-8 -*-
"""CLI 采集产物 → ``CollectedFacts`` 字段的转换（T0.5 包壳的共用层）。

存在理由：``ScanOrchestrator._collect_single`` 里内联了「适配器 dataclass → 扫描
消费结构」的转换（含 ``Incomplete`` ARP 过滤、MAC/端口归一化、``nexthop`` 兜底）。
通道层产出必须是 ``list[dict]``（契约层规格 §3.3），如果抄一份循环进 ``CliChannel``，
两侧治理规则就会漂移 —— 典型的"同一语义两个真相源"。

因此把**转换规则**收到这里，统一产出 dict；既有链路改为消费 dict 再构造
dataclass（``ParsedRoute(**row)``），逐字段等价，两侧从此共用一份规则。

约束：本模块不碰 ORM、不碰 SSH，纯转换 + 归一化，便于单测钉住每条治理规则。
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from app.utils.network_utils import normalize_mac_address
from app.utils.port_name_utils import normalize_port


def translate_routes(parsed_routes: Iterable[Any]) -> list[dict]:
    """``adapter.parse_routes()`` 产物 → 路由行 dict 列表。

    字段与 ``services/scan_context.ParsedRoute`` 一一对应（``network`` /
    ``nexthop`` / ``flags`` / ``interface`` / ``port``），便于既有链路 ``(**row)``
    直接构造 dataclass。

    三个复刻自现状的语义（缺一即改变行为）：

    - ``nexthop`` 空值兜底 ``"0.0.0.0"``（直连路由在华为 VRP 上没有下一跳字段）；
    - ``flags`` 取 ``protocol``，空值兜底 ``"C"``；
    - ``interface`` 空值兜底 ``""``，``port`` 由 ``normalize_port`` 归一化。
    """
    rows: list[dict] = []
    for r in parsed_routes:
        interface = r.interface or ""
        rows.append({
            "network":   r.network,
            "nexthop":   r.nexthop or "0.0.0.0",  # noqa: S104 -- nexthop 缺省字符串，非 socket bind
            "flags":     r.protocol or "C",
            "interface": interface,
            "port":      normalize_port(interface),
        })
    return rows


def translate_arps(parsed_arps: Iterable[Any]) -> list[dict]:
    """``adapter.parse_arp()`` 产物 → ARP 行 dict 列表（含 Incomplete 过滤）。

    过滤条件**逐字**复刻 ``ScanOrchestrator._collect_single`` 的现状：MAC 为空
    **或** ``INCOMPLETE``（大小写不敏感）的条目直接丢弃 —— 它们表示 IP 尚未实际
    通信，参与 IP 定位会产生假结果。

    注意边界保留：MAC 只有空白字符（``"   "``）时**照旧放行**。这看起来是个缺陷
    （空白串不是合法 MAC），但本模块的存在意义是"让两侧共用同一份规则"，而不是
    顺手改造治理规则 —— 收紧它属于行为变更，应在专门议题里连带下游归一化一起定。
    该分支由 tests/services/collector/test_cli_translate.py 钉住。
    """
    rows: list[dict] = []
    for a in parsed_arps:
        mac_raw = a.mac_address
        if not mac_raw or mac_raw.strip().upper() == "INCOMPLETE":
            continue
        rows.append({
            "ip":        a.ip_address,
            "mac":       normalize_mac_address(mac_raw),
            "interface": a.interface or "",
            "vlan":      a.vlan if hasattr(a, "vlan") else None,
        })
    return rows


def translate_macs(parsed_macs: Iterable[Any]) -> list[dict]:
    """``adapter.parse_mac_table()`` 产物 → MAC 表行 dict 列表。

    ``is_uplink`` 不在此产出：它由下游 Phase 2 的 ``detect_uplink_ports()`` 填充，
    通道层不知道拓扑，也不该知道。
    """
    rows: list[dict] = []
    for m in parsed_macs:
        rows.append({
            "mac":  normalize_mac_address(m.mac_address),
            "port": normalize_port(m.port),
            "vlan": m.vlan if hasattr(m, "vlan") else None,
        })
    return rows


def translate_device_info(info: Any) -> dict:
    """``ParsedDeviceInfo`` → dict（``CollectedFacts.device`` 的形状）。

    用 ``dataclasses.asdict`` 而不是手写键：字段增减自动跟随，不会出现"契约层
    多了一个字段而这里忘了抄"的静默缺口。``mac_address`` 允许为 ``None``，原样
    透传（既有链路也没做归一化）。
    """
    return asdict(info)


__all__ = [
    "translate_arps",
    "translate_device_info",
    "translate_macs",
    "translate_routes",
]
