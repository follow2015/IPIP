# -*- coding: utf-8 -*-
"""端口名称识别、格式化与归一化工具函数

集中定义端口类型判断、ID 提取、名称生成、多厂商缩写展开等功能，
消除 port_normalize.py 的重复定义，单一数据来源。
"""
import re
from typing import Optional

from app.core.enums import SwitchDeviceTypeCode


def is_trunk_interface(port: str) -> bool:
    return bool(re.match(
        r"^(?:eth-trunk|bridge-aggregation|port-channel)\d+$", port, re.IGNORECASE,
    ))


def is_aggregate_interface(port: str) -> bool:
    return is_trunk_interface(port)


def extract_trunk_id(port: str) -> Optional[int]:
    m = re.search(r"(?:eth-trunk|bridge-aggregation|port-channel)(\d+)", port, re.IGNORECASE)
    return int(m.group(1)) if m else None


def is_vlan_interface(port: str) -> bool:
    return bool(re.match(r"^(?:vlan|vlanif|vlan-interface)\d+$", port, re.IGNORECASE))


def get_trunk_name(device_type: str, channel_id: int) -> str:
    return (
        f"Bridge-Aggregation{channel_id}" if device_type == SwitchDeviceTypeCode.H3C
        else f"Eth-Trunk{channel_id}"
    )


def get_vlanif_name(device_type: str, vlan_id: int) -> str:
    return f"Vlan{vlan_id}" if device_type == SwitchDeviceTypeCode.H3C else f"Vlanif{vlan_id}"


PORT_NORMALIZE_RULES = [
    (r"^GE(\d.*)$",          r"GigabitEthernet\1"),
    (r"^XGE(\d.*)$",         r"XGigabitEthernet\1"),
    (r"^Eth-Trunk(\d+)$",    r"Eth-Trunk\1"),
    (r"^Gi(\d.*)$",          r"GigabitEthernet\1"),
    (r"^Te(\d.*)$",          r"TenGigabitEthernet\1"),
    (r"^Po(\d+)$",           r"Port-channel\1"),
    (r"^[Vv]lan[Ii]f?(\d+)$", r"Vlanif\1"),
]


def normalize_port(raw: str) -> str:
    for pattern, repl in PORT_NORMALIZE_RULES:
        if re.match(pattern, raw.strip()):
            return re.sub(pattern, repl, raw.strip())
    return raw.strip()
