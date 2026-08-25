# -*- coding: utf-8 -*-
"""
H3C 设备适配器

实现 H3C Comware 平台的命令映射和输出解析。
"""
import os
from app.utils.logging import get_logger
from typing import List, Optional
import re

from app.adapters.base_adapter import (
    BaseDeviceAdapter, BanCommands, ArpBanCommands, ParsedRoute, ParsedArpEntry, ParsedPort,
    ParsedDeviceInfo,
)

logger = get_logger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__),  "templates")

_H3C_RE_DESCRIPTION = re.compile(r'^\s*description\s+(.+?)\s*$', re.MULTILINE)
_H3C_RE_QOS_POLICY = re.compile(r'^\s*qos\s+apply\s+policy\s+(\S+)\s+(inbound|outbound)', re.MULTILINE)
_H3C_RE_LINK_AGG = re.compile(r'^\s*port\s+link-aggregation\s+group\s+(\d+)', re.MULTILINE)
_H3C_RE_L3_PORT = re.compile(r'^\s*(?:ip\s+address|port\s+link-mode\s+route)', re.MULTILINE)
_H3C_RE_ACCESS_VLAN = re.compile(r'^\s*port\s+access\s+vlan\s+(\d+)', re.MULTILINE)
_H3C_RE_TRUNK_PVID = re.compile(r'^\s*port\s+trunk\s+pvid\s+vlan\s+(\d+)', re.MULTILINE)
_H3C_RE_TRUNK_PERMIT = re.compile(r'^\s*port\s+trunk\s+permit\s+vlan\s+(.+?)\s*$', re.MULTILINE)


class H3CAdapter(BaseDeviceAdapter):
    """H3C Comware 平台适配器"""

    def parse_port_vlans(self, raw_output: str) -> dict:
        """解析H3C display port vlan 输出，返回 {端口名: pvid}"""
        result = {}
        pattern = re.compile(
            r'^(\S+)\s+(?:T|A|Hybrid)\s+(\d+)',
            re.MULTILINE | re.IGNORECASE,
        )
        for m in pattern.finditer(raw_output):
            result[m.group(1)] = int(m.group(2))
        return result

    def get_ban_commands(self, ip_address: str, device_model: str = "") -> BanCommands:
        """获取 H3C 黑洞路由封禁/解封命令

        H3C 使用 255.255.255.255 掩码格式。

        Args:
            ip_address: 需要封禁的IP地址
            device_model: 设备型号（H3C暂不区分型号，保留参数统一接口）

        Returns:
            BanCommands: 命令集合
        """
        ip_address = self._validate_ip(ip_address)
        return BanCommands(
            ban_cmds=[
                f"ip route-static {ip_address} 255.255.255.255 NULL0 "
                f"description BANNED_BY_SYSTEM",
            ],
            unban_cmds=[
                f"undo ip route-static {ip_address} 255.255.255.255 NULL0",
            ],
            save_cmd="save force",
        )

    def get_arp_ban_commands(self, ip_address: str, mac_address: str, vlan_id: int, device_model: str = "") -> ArpBanCommands:
        """获取静态ARP封禁命令（H3C Comware）

        封禁：配置静态ARP绑定到无效MAC(0000-0000-0001)
        解封：删除静态ARP，恢复动态学习

        Args:
            ip_address: IP地址
            mac_address: 真实MAC地址
            vlan_id: VLAN ID
            device_model: 设备型号（H3C暂不区分型号，保留参数统一接口）

        Returns:
            ArpBanCommands: 命令集合
        """
        BANNED_MAC = "0000-0000-0001"
        ip_address = self._validate_ip(ip_address)
        mac_address = self._validate_mac(mac_address)
        vlan_id = self._validate_vlan_id(vlan_id)
        return ArpBanCommands(
            ban_cmds=[
                f"arp static {ip_address} {BANNED_MAC} vlan {vlan_id} description BANNED_BY_SYSTEM",
            ],
            unban_cmds=[
                f"undo arp static {ip_address}",
            ],
            save_cmd="save force",
        )

    def parse_routes(self, raw_output: str) -> List[ParsedRoute]:
        """解析H3C路由表输出"""
        template_path = os.path.join(TEMPLATE_DIR, "h3c_display_ip_routing-table_verbose.textfsm")
        return self._parse_with_textfsm(
            raw_output, template_path, self._map_route_row,
        )

    def parse_arp(self, raw_output: str) -> List[ParsedArpEntry]:
        """解析H3C ARP表输出"""
        template_path = os.path.join(TEMPLATE_DIR, "h3c_display_arp.textfsm")
        return self._parse_with_textfsm(
            raw_output, template_path, self._map_arp_row,
        )

    def parse_ports(self, raw_output: str) -> List[ParsedPort]:
        """解析H3C接口信息输出"""
        template_path = os.path.join(TEMPLATE_DIR, "h3c_display_interface.textfsm")
        return self._parse_with_textfsm(
            raw_output, template_path, self._map_port_row,
        )


    @staticmethod
    def _map_route_row(header, row) -> ParsedRoute:
        """映射路由表行

        TextFSM模板列名: DESTINATION, PREFIX_LENGTH, PROTOCOL, NEXT_HOP, INTERFACE, FLAGS
        """
        h = header
        dest = H3CAdapter._get_col(h, row, "DESTINATION")
        prefix = H3CAdapter._get_col(h, row, "PREFIX_LENGTH")
        network = f"{dest}/{prefix}" if dest and prefix else dest
        return ParsedRoute(
            network=network,
            nexthop=H3CAdapter._get_col(h, row, "NEXT_HOP"),
            interface=H3CAdapter._get_col(h, row, "INTERFACE"),
            flags=H3CAdapter._get_col(h, row, "FLAGS"),
            protocol=H3CAdapter._get_col(h, row, "PROTOCOL"),
        )

    @staticmethod
    def _map_arp_row(header, row) -> ParsedArpEntry:
        """映射ARP表行

        TextFSM模板列名: IP_ADDRESS, MAC_ADDRESS, VLAN, INTERFACE, TYPE
        """
        h = header
        return ParsedArpEntry(
            ip_address=H3CAdapter._get_col(h, row, "IP_ADDRESS"),
            mac_address=H3CAdapter._get_col(h, row, "MAC_ADDRESS"),
            vlan=H3CAdapter._get_col(h, row, "VLAN"),
            interface=H3CAdapter._get_col(h, row, "INTERFACE"),
            type_vlan=H3CAdapter._get_col(h, row, "TYPE"),
        )

    @staticmethod
    def _map_port_row(header, row) -> ParsedPort:
        """映射接口信息行"""
        from app.adapters.base_adapter import normalize_port_status
        h = header
        raw_status = H3CAdapter._get_col(h, row, "LINE_STATUS")
        ip_raw = H3CAdapter._get_col(h, row, "IP_ADDRESS")
        if isinstance(ip_raw, list):
            ip_address = ",".join(ip_raw) if ip_raw else None
        elif ip_raw:
            ip_address = ip_raw
        else:
            ip_address = None
        mac_raw = H3CAdapter._get_col(h, row, "HW_ADDRESS")
        mac = mac_raw[0] if isinstance(mac_raw, list) and mac_raw else (mac_raw.split(",")[0].strip() if mac_raw else None)
        vlan_raw = H3CAdapter._get_col(h, row, "VLAN_NATIVE")
        vlan = int(vlan_raw) if vlan_raw and vlan_raw.isdigit() else None
        return ParsedPort(
            port=H3CAdapter._get_col(h, row, "INTERFACE"),
            status=normalize_port_status(raw_status),
            vlan=vlan,
            mac=mac or None,
            ip_address=ip_address,
            speed=H3CAdapter._get_col(h, row, "SPEED") or None,
            description=H3CAdapter._get_col(h, row, "DESCRIPTION") or "",
        )


    def get_interface_vlan_command(self, vlan_id: int) -> str:
        """进入VLAN接口命令"""
        return f"interface vlan {self._validate_vlan_id(vlan_id)}"

    def get_set_access_vlan_command(self, vlan_id: int) -> str:
        """设置Access VLAN命令"""
        return f"port access vlan {self._validate_vlan_id(vlan_id)}"

    def get_portswitch_command(self) -> str:
        """切换端口为二层模式"""
        return "portlink-mode bridge"

    def get_undo_portswitch_command(self) -> str:
        """切换端口为三层模式"""
        return "portlink-mode route"

    def get_trunk_allow_command(self, vlans: str, device_model: str = "") -> str:
        """设置Trunk允许VLAN命令"""
        return f"port trunk permit vlan {self._sanitize_cli_value(vlans, max_len=256, field='vlans')}"

    def get_create_trunk_command(self, channel_id: int) -> str:
        """创建链路聚合命令"""
        return f"interface bridge-aggregation {channel_id}"

    def get_delete_trunk_command(self, channel_id: int) -> str:
        """删除链路聚合命令"""
        return f"undo interface bridge-aggregation {channel_id}"

    def get_add_member_command(self, channel_id: int) -> str:
        """添加成员端口命令"""
        return f"port link-aggregation group {channel_id}"

    def get_remove_member_command(self) -> str:
        """移除成员端口命令"""
        return "undo port link-aggregation group"

    def get_check_trunk_command(self, channel_id: int) -> str:
        """检查链路聚合命令"""
        return f"display link-aggregation verbose {channel_id}"


    def get_create_qos_policy_commands(
        self, policy_name: str, cir_kbps: int,
    ) -> list:
        """创建 H3C QoS 策略定义命令（classifier + behavior + qos policy）

        H3C Comware 使用 qos policy 而非 traffic-policy。

        Args:
            policy_name: 策略名称
            cir_kbps: 承诺信息速率（kbps）

        Returns:
            list: 创建策略的命令序列
        """
        return [
            f"traffic classifier {policy_name}",
            "if-match any",
            "quit",
            f"traffic behavior {policy_name}",
            f"car cir {cir_kbps}",
            "quit",
            f"qos policy {policy_name}",
            f"classifier {policy_name} behavior {policy_name}",
            "quit",
        ]

    def get_apply_qos_policy_command(
        self, policy_name: str, direction: str,
    ) -> str:
        """在接口下应用 H3C QoS 策略命令

        Args:
            policy_name: 策略名称
            direction: 方向（inbound/outbound）

        Returns:
            str: 应用策略命令
        """
        return f"qos apply policy {policy_name} {direction}"

    def get_undo_apply_qos_policy_command(self, direction: str, policy_name: str = "") -> str:
        """取消接口下 H3C QoS 策略引用命令

        Args:
            direction: 方向（inbound/outbound）
            policy_name: 策略名称（H3C不要求指定，保留参数兼容基类）

        Returns:
            str: 取消策略引用命令
        """
        return f"undo qos apply policy {direction}"

    def get_qos_policy_query_command(self, policy_name: str) -> str:
        """查询 H3C QoS 策略是否存在的命令（H3C 使用 qos policy）"""
        return f"display qos policy {policy_name}"

    def get_delete_qos_policy_commands(self, policy_name: str) -> list:
        """删除 H3C QoS 策略定义命令（qos policy → behavior → classifier）

        Args:
            policy_name: 策略名称

        Returns:
            list: 删除策略的命令序列
        """
        return [
            f"undo qos policy {policy_name}",
            f"undo traffic behavior {policy_name}",
            f"undo traffic classifier {policy_name}",
        ]


    def get_save_command(self, device_model: str = "") -> str:
        """保存配置命令（force 跳过交互确认）"""
        return "save force"

    def get_commit_command(self) -> Optional[str]:
        """提交配置命令(H3C无commit)"""
        return None

    def parse_device_info(self, version_output: str, connection=None) -> ParsedDeviceInfo:
        """解析H3C设备信息(Comware版本)"""
        model = version = serial = uptime = ""
        m = re.search(r'(\S+)\s+uptime', version_output, re.IGNORECASE)
        if m:
            model = m.group(1)
        m = re.search(r'Comware\s+Version\s+(\S+)', version_output, re.IGNORECASE)
        if m:
            version = m.group(1)
        m = re.search(r'uptime.*?is\s+(.+)', version_output, re.IGNORECASE)
        if m:
            uptime = m.group(1).strip()
        if connection:
            try:
                sn_output = connection.send_command("display device manuinfo", delay_factor=2)
                m = re.search(r'SN\s*[:\s]+(\S+)', sn_output)
                if m:
                    serial = m.group(1)
            except Exception:
                pass
        return ParsedDeviceInfo(model=model, version=version, serial=serial, uptime=uptime, brand="H3C")


    def parse_mac_table(self, raw_output: str) -> list:
        """解析H3C MAC地址表输出

        使用 TextFSM 模板解析 display mac-address 输出。
        """
        from app.adapters.base_adapter import ParsedMacEntry
        template_path = os.path.join(TEMPLATE_DIR, "h3c_display_mac-address.textfsm")
        return self._parse_with_textfsm(raw_output, template_path, self._map_mac_row)

    @staticmethod
    def _map_mac_row(header, row) -> "ParsedMacEntry":
        """映射MAC地址表行

        TextFSM模板列名: MAC_ADDRESS, VLAN, PORT, TYPE
        """
        from app.adapters.base_adapter import ParsedMacEntry
        h = header
        return ParsedMacEntry(
            mac_address=H3CAdapter._get_col(h, row, "MAC_ADDRESS"),
            vlan=H3CAdapter._get_col(h, row, "VLAN") or "",
            port=H3CAdapter._get_col(h, row, "PORT"),
            entry_type=(H3CAdapter._get_col(h, row, "TYPE") or "").lower(),
        )


    def parse_port_description(self, config_text: str) -> str:
        """从端口配置文本解析描述（H3C Comware）

        格式: description <text>
        """
        m = _H3C_RE_DESCRIPTION.search(config_text)
        return m.group(1).strip() if m else ""

    def parse_qos_policies(self, config_text: str) -> list[tuple[str, str]]:
        """从端口配置文本解析已应用的 QoS 策略（H3C Comware）

        格式: qos apply policy <name> inbound/outbound
        """
        return [(m.group(1), m.group(2)) for m in _H3C_RE_QOS_POLICY.finditer(config_text)]

    def parse_trunk_id(self, config_text: str) -> Optional[int]:
        """从端口配置文本解析 Bridge-Aggregation ID（H3C Comware）

        格式: port link-aggregation group <id>
        """
        m = _H3C_RE_LINK_AGG.search(config_text)
        return int(m.group(1)) if m else None

    def parse_vlan_info(self, config_text: str) -> dict:
        """从端口配置文本解析 VLAN 信息（H3C Comware）

        格式:
        - Access: port access vlan <id>
        - Trunk PVID: port trunk pvid vlan <id>
        - Trunk 允许: port trunk permit vlan <range>
        - 三层口: ip address / port link-mode route
        """
        if _H3C_RE_L3_PORT.search(config_text):
            return {"mode": None, "pvid": None, "allowed_vlans": None}

        mode = None
        pvid = None
        allowed_vlans = None

        m_access = _H3C_RE_ACCESS_VLAN.search(config_text)
        if m_access:
            mode = "access"
            pvid = int(m_access.group(1))

        m_trunk_pvid = _H3C_RE_TRUNK_PVID.search(config_text)
        m_trunk_permit = _H3C_RE_TRUNK_PERMIT.search(config_text)
        if m_trunk_pvid or m_trunk_permit:
            mode = "trunk"
            if m_trunk_pvid:
                pvid = int(m_trunk_pvid.group(1))
            if m_trunk_permit:
                allowed_vlans = m_trunk_permit.group(1).strip()

        return {"mode": mode, "pvid": pvid, "allowed_vlans": allowed_vlans}
