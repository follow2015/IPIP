from __future__ import annotations
# -*- coding: utf-8 -*-
"""扫描上下文数据类

统一封装每台交换机的采集结果，替代原有分散处理模式。
包含路由、ARP、MAC 表条目及交换机元信息。
"""
from dataclasses import dataclass


@dataclass
class ParsedRoute:
    """路由条目

    Attributes:
        network: CIDR 格式网段，e.g. "192.168.10.0/24"
        nexthop: 下一跳 IP，"0.0.0.0" 表示直连
        flags: 路由标志，e.g. "C" / "DIRECT" / "S" / "O"
        interface: 原始接口名，e.g. "GE0/0/3"
        port: 归一化后的端口（Phase 1 写库前填充）
    """
    network:   str          # CIDR，e.g. "192.168.10.0/24"
    nexthop:   str          # "0.0.0.0" 表示直连
    flags:     str          # "C" / "DIRECT" / "S" / "O" 等
    interface: str          # 原始接口名，e.g. "GE0/0/3"
    port:      str = ""     # 归一化后的端口（Phase 1 写库前填充）


@dataclass
class ParsedArpEntry:
    """ARP 条目

    Attributes:
        ip: IP 地址，e.g. "192.168.10.100"
        mac: 归一化 MAC 地址，e.g. "aa:bb:cc:dd:ee:ff"
        interface: 接口名，e.g. "Vlanif10"
        vlan: VLAN ID，可选
    """
    ip:        str          # e.g. "192.168.10.100"
    mac:       str          # 归一化 MAC，e.g. "aa:bb:cc:dd:ee:ff"
    interface: str          # e.g. "Vlanif10"
    vlan:      int | None = None


@dataclass
class ParsedMacEntry:
    """MAC 表条目

    Attributes:
        mac: 归一化 MAC 地址
        port: 归一化端口，e.g. "GigabitEthernet0/0/5"
        vlan: VLAN ID，可选
        is_uplink: 是否为上联端口（Phase 2 build() 时由 detect_uplink_ports() 填充）
    """
    mac:       str          # 归一化 MAC
    port:      str          # 归一化端口，e.g. "GigabitEthernet0/0/5"
    vlan:      int | None = None
    is_uplink: bool = False # Phase 2 build() 时由 detect_uplink_ports() 填充


@dataclass
class SwitchContext:
    """每台交换机的采集结果上下文

    统一封装单台交换机的所有采集数据，供 6-Phase 流水线各阶段读写。

    Attributes:
        sw_id: 交换机 devices.id (via switch_credentials.device_id)
        ip: 管理IP
        has_ssh: 是否有 SSH 权限
        layer: 交换机层级（2 或 3）
        is_core: 是否核心交换机
        routes: 路由条目列表
        arps: ARP 条目列表
        macs: MAC 表条目列表
        uplink_sw_id: 上联交换机 devices.id
        uplink_port: 上游侧端口（已归一化）
        room_id: 机房ID
    """
    sw_id:        int
    ip:           str
    has_ssh:      bool
    layer:        int           # 2 or 3
    is_core:      bool          # True=核心交换机（Device.switch_role==0），False=接入层
    routes:       list[ParsedRoute]
    arps:         list[ParsedArpEntry]
    macs:         list[ParsedMacEntry]
    uplink_sw_id: int | None
    uplink_port:  str | None    # 上游侧端口（已归一化）
    room_id:      int
    scope:        str = ""      # 扫描范围标识，"r:{room_id}" 或 "vr:{virtual_room_id}"
