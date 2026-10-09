# -*- coding: utf-8 -*-
"""端口行 ``port_rows`` 的**唯一**组装实现。

为什么抽出来：CLI 侧（``SwitchInfoService.collect_port_info``）与多通道采集层的
``CliChannel`` 需要产出**逐字段一致**的端口行；两边各写一份循环，改动任一侧
（例如新增速率字段、调整主 IP 取第几个）必然漂移，而漂移的代价是下游
``PortSyncService._replace_by_tuple_key`` 吃到形状不一致的数据。

刻意放 ``app/services/`` 而不是 ``app/services/collector/``：CLI 采集服务
（``switch_info_service``）早于通道层存在，让它反过来依赖通道层包会造成语义
倒置（老链路依赖新抽象）。这里只放一个纯函数，谁都能用，谁都不被绑定。

``device_id`` 为什么是可选参数而不是固定字段：契约层
（``app/services/collector/facts.py`` docstring / 契约层规格 §4）规定
``CollectedFacts.ports`` 的行**不带** ``device_id`` —— 它由 ``collect(device_id)``
的入参与后续 ``facts_adapter`` 注入。CLI 侧写库则需要它。用同一个函数、同一个
键顺序，只差这一个可选键，比维护两份循环安全。
"""
from __future__ import annotations

from typing import Any, Iterable

from app.utils.port_name_parser import parse_port_name

PORT_ROW_KEYS: tuple[str, ...] = (
    "port_name",
    "slot",
    "card",
    "port_number",
    "port_type",
    "link_status",
    "vlan",
    "mac",
    "ip_address",
    "speed",
    "description",
)


def build_port_rows(
    parsed_ports: Iterable[Any],
    device_id: int | None = None,
) -> list[dict]:
    """把适配器的 ``ParsedPort`` 序列转成 ``port_rows``（``list[dict]``）。

    Args:
        parsed_ports: ``parse_ports()`` 的产物，元素需有
            ``port`` / ``status`` / ``vlan`` / ``mac`` / ``ip_address`` /
            ``speed`` / ``description`` 属性（``ParsedPort`` dataclass）。
        device_id: 需要写库时传入，行首增加 ``device_id`` 键；采集契约层传
            ``None``（默认），产出不带该键的行。

    Returns:
        list[dict]: 每行 11 个键（传 ``device_id`` 时 12 个），键顺序固定。

    字段语义（**不得**在此处新增与既有链路不同的处理，否则即破坏"零变更"）：

    - ``slot`` / ``card`` / ``port_number`` / ``port_type`` 由 ``parse_port_name``
      从 ``port`` 字符串解析；
    - ``ip_address`` 可能含逗号分隔的多个 IP，**只取主 IP**（第一个）—— 主表
      ``network_ports`` 只存主 IP，沿用既有实现。
    """
    rows: list[dict] = []
    for p in parsed_ports:
        parsed_name = parse_port_name(p.port)
        row: dict = {}
        if device_id is not None:
            row["device_id"] = device_id
        row.update({
            "port_name":   p.port,
            "slot":        parsed_name["slot"],
            "card":        parsed_name["card"],
            "port_number": parsed_name["port_number"],
            "port_type":   parsed_name["port_type"],
            "link_status": p.status,
            "vlan":        p.vlan,
            "mac":         p.mac,
            "ip_address":  p.ip_address.split(",")[0].strip() if p.ip_address else None,
            "speed":       p.speed,
            "description": p.description,
        })
        rows.append(row)
    return rows


__all__ = ["PORT_ROW_KEYS", "build_port_rows"]
