# -*- coding: utf-8 -*-
"""
端口名解析器

将交换机端口名（如 GE1/0/1、XGigabitEthernet0/0/1）解析为结构化字段
(slot, card, port_number)，用于写入 network_ports 表。
"""
import re
from typing import Optional

_PORT_TYPE_MAP = {
    "ge": "GE", "gigabitethernet": "GE",
    "10ge": "10GE", "xge": "10GE", "xgigabitethernet": "10GE",
    "ten-gigabitethernet": "10GE",
    "25ge": "25GE",
    "40ge": "40GE", "fortygige": "40GE",
    "50ge": "50GE",
    "100ge": "100GE", "hundredgige": "100GE",
    "twohundredgige": "200GE",
    "eth": "GE",
}

_PORT_PATTERN = re.compile(
    r"^(10GE|XGE|GE|GigabitEthernet|XGigabitEthernet|Eth|"
    r"Ten-GigabitEthernet|HundredGigE|40GE|25GE|"
    r"FortyGigE|TwoHundredGigE|50GE|100GE)"
    r"(\d+)/(\d+)/(\d+)$",
    re.IGNORECASE,
)

_SIMPLE_TYPE_MAP = {
    "eth-trunk": "ETH-TRUNK",
    "bridge-aggregation": "ETH-TRUNK",
    "port-channel": "ETH-TRUNK",
    "vlanif": "VLAN",
    "vlan": "VLAN",
    "vlan-interface": "VLAN",
    "loopback": "LOOPBACK",
    "null": "NULL",
    "inloopback": "LOOPBACK",
}

_SIMPLE_PATTERN = re.compile(
    r"^(Eth-Trunk|Bridge-Aggregation|Port-channel|Vlanif|Vlan|Vlan-interface|"
    r"LoopBack|NULL|InLoopBack)(\d+)$",
    re.IGNORECASE,
)


def parse_port_name(port_name: str) -> dict:
    if not port_name:
        return {"port_name": port_name, "slot": -1, "card": -1, "port_number": -1, "port_type": None, "parsed": False}

    m = _PORT_PATTERN.match(port_name)
    if m:
        prefix = m.group(1).lower()
        port_type = _PORT_TYPE_MAP.get(prefix, "GE")
        return {
            "port_name": port_name,
            "slot": int(m.group(2)),
            "card": int(m.group(3)),
            "port_number": int(m.group(4)),
            "port_type": port_type,
            "parsed": True,
        }

    m = _SIMPLE_PATTERN.match(port_name)
    if m:
        prefix = m.group(1).lower()
        port_type = _SIMPLE_TYPE_MAP.get(prefix, None)
        return {
            "port_name": port_name,
            "slot": -1,
            "card": -1,
            "port_number": int(m.group(2)),
            "port_type": port_type,
            "parsed": True,
        }

    return {"port_name": port_name, "slot": -1, "card": -1, "port_number": -1, "port_type": None, "parsed": False}


def normalize_port_name(port_name: str) -> Optional[str]:
    if not port_name:
        return None
    return re.sub(r"\s+", "", port_name)
