from __future__ import annotations

"""扫描上下文数据类

统一封装每台交换机的采集结果，替代原有分散处理模式。
包含路由、ARP、MAC 表条目及交换机元信息。
"""
from dataclasses import dataclass


@dataclass
class ParsedRoute:
    network:   str
    nexthop:   str
    flags:     str
    interface: str
    port:      str = ""


@dataclass
class ParsedArpEntry:
    ip:        str
    mac:       str
    interface: str
    vlan:      int | None = None


@dataclass
class ParsedMacEntry:
    mac:       str
    port:      str
    vlan:      int | None = None
    is_uplink: bool = False


@dataclass
class SwitchContext:
    sw_id:        int
    ip:           str
    has_ssh:      bool
    layer:        int
    is_core:      bool
    routes:       list[ParsedRoute]
    arps:         list[ParsedArpEntry]
    macs:         list[ParsedMacEntry]
    uplink_sw_id: int | None
    uplink_port:  str | None
    room_id:      int
    scope:        str = ""
