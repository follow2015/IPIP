# -*- coding: utf-8 -*-
"""
Cisco 设备适配器

实现 Cisco IOS 平台的命令映射和输出解析。
"""
from app.utils.logging import get_logger
import os
import re
from typing import List, Optional

from app.adapters.base_adapter import (
    BaseDeviceAdapter, BanCommands, ArpBanCommands, ParsedRoute, ParsedArpEntry, ParsedPort,
    ParsedDeviceInfo, ParsedIP, ParsedMacEntry,
)

logger = get_logger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

_CISCO_RE_DESCRIPTION = re.compile(r'^\s*description\s+(.+?)\s*$', re.MULTILINE)
_CISCO_RE_SERVICE_POLICY = re.compile(r'^\s*service-policy\s+(input|output)\s+(\S+)', re.MULTILINE)
_CISCO_RE_CHANNEL_GROUP = re.compile(r'^\s*channel-group\s+(\d+)', re.MULTILINE)
_CISCO_RE_L3_PORT = re.compile(r'^\s*(?:no\s+switchport|ip\s+address)', re.MULTILINE)
_CISCO_RE_ACCESS_VLAN = re.compile(r'^\s*switchport\s+access\s+vlan\s+(\d+)', re.MULTILINE)
_CISCO_RE_TRUNK_NATIVE = re.compile(r'^\s*switchport\s+trunk\s+native\s+vlan\s+(\d+)', re.MULTILINE)
_CISCO_RE_TRUNK_ALLOW = re.compile(r'^\s*switchport\s+trunk\s+allowed\s+vlan\s+(.+?)\s*$', re.MULTILINE)


class CiscoAdapter(BaseDeviceAdapter):
    """Cisco IOS 平台适配器"""


    def get_route_command(self) -> str:
        return "show ip route"

    def get_arp_command(self) -> str:
        return "show ip arp"

    def get_mac_command(self) -> str:
        return "show mac address-table"

    def get_interface_command(self) -> str:
        return "show interface"

    def get_interface_status_command(self, port: str) -> str:
        """Cisco 单端口链路状态查询命令（show interface <port>）"""
        return f"show interface {self._validate_port_name(port)}"

    def get_version_command(self) -> str:
        return "show version"

    def get_sysname_command(self) -> str:
        """Cisco 使用 show hostname 获取主机名"""
        return "show hostname"

    def get_port_vlan_command(self) -> str:
        return "show interfaces switchport"

    def parse_port_vlans(self, raw_output: str) -> dict:
        """解析 Cisco show interfaces switchport 输出，返回 {端口名: pvid}"""
        result = {}
        current_port = None
        for line in raw_output.splitlines():
            m = re.match(r'^(\S+)\s+is\s+', line)
            if m:
                current_port = m.group(1)
                continue
            m = re.match(r'^\s*Access\s+VLAN\s*:\s+(\d+)', line, re.IGNORECASE)
            if m and current_port:
                result[current_port] = int(m.group(1))
                continue
            m = re.match(r'^\s*Native\s+VLAN\s*:\s+(\d+)', line, re.IGNORECASE)
            if m and current_port and current_port not in result:
                result[current_port] = int(m.group(1))
        return result


    def get_ban_commands(self, ip_address: str, device_model: str = "") -> BanCommands:
        """获取 Cisco 黑洞路由封禁/解封命令（Null0 + 255.255.255.255 掩码）

        Args:
            ip_address: 需要封禁的IP地址
            device_model: 设备型号（Cisco暂不区分型号，保留参数统一接口）

        Returns:
            BanCommands: 命令集合
        """
        ip_address = self._validate_ip(ip_address)
        return BanCommands(
            ban_cmds=[
                f"ip route {ip_address} 255.255.255.255 Null0 name BANNED_BY_SYSTEM",
            ],
            unban_cmds=[
                f"no ip route {ip_address} 255.255.255.255 Null0",
            ],
            save_cmd="write memory",
        )

    def get_arp_ban_commands(self, ip_address: str, mac_address: str, vlan_id: int, device_model: str = "") -> ArpBanCommands:
        """获取静态 ARP 封禁命令（Cisco IOS，全局 arp 命令，MAC 格式 xxxx.xxxx.xxxx）

        Args:
            ip_address: IP地址
            mac_address: 真实MAC地址
            vlan_id: VLAN ID（Cisco全局arp命令不使用此参数）
            device_model: 设备型号（Cisco暂不区分型号，保留参数统一接口）

        Returns:
            ArpBanCommands: 命令集合
        """
        BANNED_MAC = "0000.0000.0001"
        ip_address = self._validate_ip(ip_address)
        mac_address = self._validate_mac(mac_address)
        return ArpBanCommands(
            ban_cmds=[
                f"arp {ip_address} {BANNED_MAC} arpa",
            ],
            unban_cmds=[
                f"no arp {ip_address} {BANNED_MAC} arpa",
            ],
            save_cmd="write memory",
        )


    def parse_routes(self, raw_output: str) -> List[ParsedRoute]:
        """解析 Cisco show ip route 输出

        支持动态/静态路由（via 格式）和直连路由（directly connected）。
        """
        results = []
        proto_map = {"S": "Static", "C": "Direct", "O": "OSPF", "B": "BGP", "R": "RIP"}

        pattern_via = re.compile(
            r"^(\S)\s+(\S+/\d+)\s+\[\d+/\d+\]\s+via\s+(\S+),\s*(\S+)",
            re.MULTILINE,
        )
        for m in pattern_via.finditer(raw_output):
            flag = m.group(1)
            results.append(ParsedRoute(
                network=m.group(2), nexthop=m.group(3),
                interface=m.group(4), flags=flag,
                protocol=proto_map.get(flag, flag),
            ))

        pattern_direct = re.compile(
            r"^(\S)\s+(\S+/\d+)\s+is directly connected,\s*(\S+)",
            re.MULTILINE,
        )
        for m in pattern_direct.finditer(raw_output):
            flag = m.group(1)
            results.append(ParsedRoute(
                network=m.group(2), nexthop="0.0.0.0",
                interface=m.group(3), flags=flag,
                protocol=proto_map.get(flag, flag),
            ))
        return results

    def parse_arp(self, raw_output: str) -> List[ParsedArpEntry]:
        """解析 Cisco show ip arp 输出

        典型格式: Internet  10.10.1.1  5   abcd.ef01.2345  ARPA  GigabitEthernet0/0
        """
        results = []
        pattern = re.compile(
            r"Internet\s+(\d+\.\d+\.\d+\.\d+)\s+\d+\s+"
            r"([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+(\S+)\s+(\S+)",
            re.MULTILINE,
        )
        for m in pattern.finditer(raw_output):
            results.append(ParsedArpEntry(
                ip_address=m.group(1),
                mac_address=m.group(2),
                vlan="",
                interface=m.group(4),
                type_vlan=m.group(3),
            ))
        return results

    def parse_mac_table(self, raw_output: str) -> List[ParsedMacEntry]:
        """解析 Cisco show mac address-table 输出

        格式: <vlan>  <xxxx.xxxx.xxxx>  <TYPE>  <port>
        MAC 地址从 Cisco 格式（xxxx.xxxx.xxxx）转换为统一格式（xxxx-xxxx-xxxx）。
        """
        from app.utils.network_utils import normalize_mac_address
        entries = []
        pattern = re.compile(
            r'(\d+)\s+'
            r'([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+'
            r'(\S+)\s+(\S+)'
        )
        for line in raw_output.splitlines():
            m = pattern.search(line)
            if m:
                entries.append(ParsedMacEntry(
                    mac_address=normalize_mac_address(m.group(2)),
                    vlan=m.group(1),
                    port=m.group(4),
                    entry_type=m.group(3).lower(),
                ))
        return entries

    def parse_ports(self, raw_output: str) -> List[ParsedPort]:
        """解析 Cisco show interface 输出"""
        template_path = os.path.join(TEMPLATE_DIR, "cisco_ios_show_interfaces.textfsm")
        return self._parse_with_textfsm(raw_output, template_path, self._map_port_row)

    @staticmethod
    def _map_port_row(header, row) -> ParsedPort:
        """映射接口信息行（TextFSM 行 → ParsedPort）

        MAC 地址从 Cisco 格式（xxxx.xxxx.xxxx）转换为统一格式（xxxx-xxxx-xxxx）。
        """
        from app.adapters.base_adapter import normalize_port_status
        h = header
        raw_status = CiscoAdapter._get_col(h, row, "LINK_STATUS")
        mac_raw = CiscoAdapter._get_col(h, row, "ADDRESS")
        mac = None
        if mac_raw and "." in mac_raw:
            hex_str = mac_raw.replace(".", "").lower()
            mac = "-".join(hex_str[i:i + 4] for i in range(0, len(hex_str), 4))
        return ParsedPort(
            port=CiscoAdapter._get_col(h, row, "INTERFACE"),
            status=normalize_port_status(raw_status),
            mac=mac or None,
            ip_address=CiscoAdapter._get_col(h, row, "IP_ADDRESS") or None,
            speed=CiscoAdapter._get_col(h, row, "SPEED") or None,
            description=CiscoAdapter._get_col(h, row, "DESCRIPTION") or "",
        )


    def get_enter_interface_command(self, port: str) -> str:
        return f"interface {self._validate_port_name(port)}"

    def get_interface_range_command(self, port_expr: str) -> str:
        """Cisco interface range 命令，支持逗号分隔和连字符范围

        Cisco 语法：
        - 范围: interface range Gi1/0/1 - 10
        - 离散: interface range Gi1/0/1 , Gi1/0/3 , Gi1/0/5
        - 混合: interface range Gi1/0/1 - 3 , Gi1/0/5

        Args:
            port_expr: 端口范围表达式（已由 PortRangeParser 转换为 Cisco 格式）

        Returns:
            str: 完整的 interface range 命令
        """
        return f"interface range {self._sanitize_cli_value(port_expr, max_len=256, field='port_range')}"

    def get_set_ip_command(self, ip: str, mask: str) -> str:
        return f"ip address {self._validate_ip(ip)} {self._validate_ip(mask)}"

    def get_set_secondary_ip_command(self, ip: str, mask: str) -> str:
        return f"ip address {self._validate_ip(ip)} {self._validate_ip(mask)} secondary"

    def get_undo_ip_command(self, ip: str, mask: str, is_secondary: bool = False) -> str:
        """删除IP地址命令（Cisco格式）"""
        secondary = " secondary" if is_secondary else ""
        return f"no ip address {self._validate_ip(ip)} {self._validate_ip(mask)}{secondary}"

    def get_shutdown_command(self) -> str:
        return "shutdown"

    def get_undo_shutdown_command(self) -> str:
        return "no shutdown"

    def get_description_command(self, description: str) -> str:
        return f"description {self._sanitize_cli_value(description, max_len=240, field='description')}"

    def get_exit_interface_command(self) -> str:
        return "exit"


    def get_create_vlan_command(self, vlan_id: int) -> str:
        return f"vlan {self._validate_vlan_id(vlan_id)}"

    def get_interface_vlan_command(self, vlan_id: int) -> str:
        return f"interface vlan {self._validate_vlan_id(vlan_id)}"

    def get_set_access_vlan_command(self, vlan_id: int) -> str:
        return f"switchport access vlan {self._validate_vlan_id(vlan_id)}"

    def get_set_trunk_command(self) -> str:
        return "switchport mode trunk"

    def get_trunk_allow_command(self, vlans: str, device_model: str = "") -> str:
        return f"switchport trunk allowed vlan {self._sanitize_cli_value(vlans, max_len=256, field='vlans')}"

    def get_trunk_pvid_command(self, vlan_id: int) -> str:
        """Cisco: switchport trunk native vlan {vlan_id}"""
        return f"switchport trunk native vlan {self._validate_vlan_id(vlan_id)}"

    def get_check_vlan_command(self, vlan_id: int) -> str:
        return f"show vlan id {self._validate_vlan_id(vlan_id)}"

    def get_delete_vlan_command(self, vlan_id: int) -> str:
        return f"no vlan {self._validate_vlan_id(vlan_id)}"


    def get_create_trunk_command(self, channel_id: int) -> str:
        return f"interface port-channel {channel_id}"

    def get_delete_trunk_command(self, channel_id: int) -> str:
        return f"no interface port-channel {channel_id}"

    def get_add_member_command(self, channel_id: int) -> str:
        return f"channel-group {channel_id} mode active"

    def get_remove_member_command(self) -> str:
        return "no channel-group"

    def get_check_trunk_command(self, channel_id: int) -> str:
        return f"show etherchannel {channel_id}"


    def get_clear_config_command(self, port: str) -> str:
        """Cisco IOS 不支持 clear configuration interface，返回空字符串"""
        return ""


    def get_delete_route_command(self, network: str, mask: str, nexthop: str) -> str:
        return (
            f"no ip route "
            f"{self._sanitize_cli_value(network, field='network')} "
            f"{self._validate_ip(mask)} "
            f"{self._sanitize_cli_value(nexthop, field='nexthop')}"
        )


    def get_save_command(self, device_model: str = "") -> str:
        return "write memory"

    def get_commit_command(self) -> Optional[str]:
        """Cisco IOS 无 commit 概念"""
        return None

    def get_system_view_command(self) -> str:
        return "configure terminal"

    def get_return_command(self) -> str:
        return "end"


    def parse_device_info(self, version_output: str, connection=None) -> ParsedDeviceInfo:
        """解析 Cisco show version 输出"""
        model = version = serial = uptime = ""
        m = re.search(r'(\S+)\s+uptime\s+is', version_output, re.IGNORECASE)
        if m:
            model = m.group(1)
        m = re.search(r'Version\s+([\d.()\w]+)', version_output, re.IGNORECASE)
        if m:
            version = m.group(1)
        m = re.search(r'uptime\s+is\s+(.+)', version_output, re.IGNORECASE)
        if m:
            uptime = m.group(1).strip()
        m = re.search(r'Processor\s+board\s+ID\s+(\S+)', version_output, re.IGNORECASE)
        if m:
            serial = m.group(1)
        return ParsedDeviceInfo(model=model, version=version, serial=serial, uptime=uptime, brand="Cisco")

    def parse_existing_ips(self, config_text: str) -> list:
        """从配置文本解析现有 IP 地址（Cisco secondary 关键字）"""
        results = []
        pattern = r'ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s*(secondary)?'
        for m in re.finditer(pattern, config_text):
            results.append(ParsedIP(
                ip_address=m.group(1),
                subnet_mask=m.group(2),
                is_primary=not bool(m.group(3)),
            ))
        return results


    def parse_port_description(self, config_text: str) -> str:
        """从端口配置文本解析描述（Cisco IOS）

        格式: description <text>
        """
        m = _CISCO_RE_DESCRIPTION.search(config_text)
        return m.group(1).strip() if m else ""

    def parse_qos_policies(self, config_text: str) -> list[tuple[str, str]]:
        """从端口配置文本解析已应用的 QoS 策略（Cisco IOS）

        Cisco IOS 使用 service-policy input/output 格式。
        """
        results = []
        for m in _CISCO_RE_SERVICE_POLICY.finditer(config_text):
            direction = "inbound" if m.group(1) == "input" else "outbound"
            results.append((m.group(2), direction))
        return results

    def parse_trunk_id(self, config_text: str) -> Optional[int]:
        """从端口配置文本解析 Port-channel ID（Cisco IOS）

        格式: channel-group <id> mode <mode>
        """
        m = _CISCO_RE_CHANNEL_GROUP.search(config_text)
        return int(m.group(1)) if m else None

    def parse_vlan_info(self, config_text: str) -> dict:
        """从端口配置文本解析 VLAN 信息（Cisco IOS）

        格式:
        - Access: switchport access vlan <id>
        - Trunk Native: switchport trunk native vlan <id>
        - Trunk 允许: switchport trunk allowed vlan <range>
        - 三层口: no switchport / ip address
        """
        if _CISCO_RE_L3_PORT.search(config_text):
            return {"mode": None, "pvid": None, "allowed_vlans": None}

        mode = None
        pvid = None
        allowed_vlans = None

        m_access = _CISCO_RE_ACCESS_VLAN.search(config_text)
        if m_access:
            mode = "access"
            pvid = int(m_access.group(1))

        m_trunk_native = _CISCO_RE_TRUNK_NATIVE.search(config_text)
        m_trunk_allow = _CISCO_RE_TRUNK_ALLOW.search(config_text)
        if m_trunk_native or m_trunk_allow:
            mode = "trunk"
            if m_trunk_native:
                pvid = int(m_trunk_native.group(1))
            if m_trunk_allow:
                allowed_vlans = m_trunk_allow.group(1).strip()

        return {"mode": mode, "pvid": pvid, "allowed_vlans": allowed_vlans}
