# -*- coding: utf-8 -*-
"""
华为设备适配器

实现华为 VRP 平台的命令映射和输出解析。
"""
import os
from app.utils.logging import get_logger
from typing import List, Optional
import re

from app.adapters.base_adapter import (
    BaseDeviceAdapter, BanCommands, ArpBanCommands, ParsedRoute, ParsedArpEntry, ParsedPort,
    ParsedDeviceInfo,ParsedMacEntry
)

logger = get_logger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__),  "templates")

_RE_DESCRIPTION = re.compile(r'^\s*description\s+(.+?)\s*$', re.MULTILINE)
_RE_TRAFFIC_POLICY = re.compile(r'^\s*traffic-policy\s+(\S+)\s+(inbound|outbound)', re.MULTILINE)
_RE_ETH_TRUNK = re.compile(r'^\s*eth-trunk\s+(\d+)', re.MULTILINE)
_RE_L3_PORT = re.compile(r'^\s*(?:ip\s+address|undo\s+portswitch)', re.MULTILINE)
_RE_ACCESS_VLAN = re.compile(r'^\s*port\s+default\s+vlan\s+(\d+)', re.MULTILINE)
_RE_TRUNK_PVID = re.compile(r'^\s*port\s+trunk\s+pvid\s+vlan\s+(\d+)', re.MULTILINE)
_RE_TRUNK_ALLOW = re.compile(r'^\s*port\s+trunk\s+allow-pass\s+vlan\s+(.+?)\s*$', re.MULTILINE)


class HuaweiAdapter(BaseDeviceAdapter):

    def parse_port_vlans(self, raw_output: str) -> dict:
        result = {}
        pattern = re.compile(
            r'^(\S+)\s+(?:trunk|access)\s+(\d+)',
            re.MULTILINE,
        )
        for m in pattern.finditer(raw_output):
            result[m.group(1)] = int(m.group(2))
        return result

    def get_ban_commands(self, ip_address: str, device_model: str = "") -> BanCommands:
        is_ce = self.is_ce_model(device_model)
        ip_address = self._validate_ip(ip_address)
        ban_cmds = [
            f"ip route-static {ip_address} 32 NULL0 description BANNED_BY_SYSTEM",
        ]
        unban_cmds = [
            f"undo ip route-static {ip_address} 32 NULL0",
        ]
        if is_ce:
            ban_cmds.append("commit")
            unban_cmds.append("commit")

        return BanCommands(
            ban_cmds=ban_cmds,
            unban_cmds=unban_cmds,
            save_cmd=self.get_save_command(device_model),
        )

    def get_arp_ban_commands(self, ip_address: str, mac_address: str, vlan_id: int, device_model: str = "") -> ArpBanCommands:
        BANNED_MAC = "0000-0000-0001"
        is_ce = self.is_ce_model(device_model)
        ip_address = self._validate_ip(ip_address)
        mac_address = self._validate_mac(mac_address)
        vlan_id = self._validate_vlan_id(vlan_id)
        ban_cmds = [
            f"arp static {ip_address} {BANNED_MAC} vlan-id {vlan_id} description BANNED_BY_SYSTEM",
        ]
        unban_cmds = [
            f"undo arp static {ip_address}",
        ]
        if is_ce:
            ban_cmds.append("commit")
            unban_cmds.append("commit")

        return ArpBanCommands(
            ban_cmds=ban_cmds,
            unban_cmds=unban_cmds,
            save_cmd=self.get_save_command(device_model),
        )

    def parse_routes(self, raw_output: str) -> List[ParsedRoute]:
        template_path = os.path.join(
            TEMPLATE_DIR, "huawei_vrp_display_ip_routing-table_verbose.textfsm"
        )
        return self._parse_with_textfsm(
            raw_output, template_path, self._map_route_row,
        )

    def parse_arp(self, raw_output: str) -> List[ParsedArpEntry]:
        template_path = os.path.join(
            TEMPLATE_DIR, "huawei_vrp_display_arp.textfsm"
        )
        return self._parse_with_textfsm(
            raw_output, template_path, self._map_arp_row,
        )

    def parse_ports(self, raw_output: str) -> List[ParsedPort]:
        template_path = os.path.join(
            TEMPLATE_DIR, "huawei_vrp_display_interface.textfsm"
        )
        return self._parse_with_textfsm(
            raw_output, template_path, self._map_port_row,
        )

    def get_interface_vlan_command(self, vlan_id: int) -> str:
        return f"interface vlanif {self._validate_vlan_id(vlan_id)}"

    def get_set_access_vlan_command(self, vlan_id: int) -> str:
        return f"port default vlan {self._validate_vlan_id(vlan_id)}"

    def get_portswitch_command(self) -> str:
        return "portswitch"

    def get_undo_portswitch_command(self) -> str:
        return "undo portswitch"

    def get_trunk_allow_command(self, vlans: str, device_model: str = "") -> str:
        if self.is_ce_model(device_model):
            ranges = self.parse_vlan_ranges(vlans)
            vlans = self.format_vlans_ce(ranges) if ranges else vlans
        return f"port trunk allow-pass vlan {self._sanitize_cli_value(vlans, max_len=256, field='vlans')}"

    def get_create_trunk_command(self, channel_id: int) -> str:
        return f"interface eth-trunk {channel_id}"

    def get_delete_trunk_command(self, channel_id: int) -> str:
        return f"undo interface eth-trunk {channel_id}"

    def get_add_member_command(self, channel_id: int) -> str:
        return f"eth-trunk {channel_id}"

    def get_remove_member_command(self) -> str:
        return "undo eth-trunk"

    def get_trunkport_command(self, port_expr: str) -> str:
        return f"trunkport {self._sanitize_cli_value(port_expr, max_len=256, field='port_range')}"

    def get_undo_trunkport_command(self, port_expr: str) -> str:
        return f"undo trunkport {self._sanitize_cli_value(port_expr, max_len=256, field='port_range')}"

    def get_check_trunk_command(self, channel_id: int) -> str:
        return f"display eth-trunk {channel_id}"


    def get_save_command(self, device_model: str = "") -> str:
        if self.is_ce_model(device_model):
            return "save force vrpcfg.zip"
        return "save force"

    def get_commit_command(self) -> Optional[str]:
        return "commit"

    def parse_device_info(self, version_output: str, connection=None) -> ParsedDeviceInfo:
        model = version = serial = uptime = ""
        try:
            import textfsm
            tpl_path = os.path.join(TEMPLATE_DIR, "huawei_vrp_display_ver.textfsm")
            with open(tpl_path) as f:
                fsm = textfsm.TextFSM(f)
            rows = fsm.ParseText(version_output)
            if rows:
                header = fsm.header
                row = rows[0]
                model = HuaweiAdapter._get_col(header, row, "MODEL")
                version = HuaweiAdapter._get_col(header, row, "VERSION")
                uptime = HuaweiAdapter._get_col(header, row, "UPTIME")
        except Exception:
            m = re.search(
                r'(?:HUAWEI|Huawei|Quidway)\s+(\S+)\s+(?:Router\s+)?uptime\s+is',
                version_output, re.IGNORECASE,
            )
            if m:
                model = m.group(1)
            else:
                m = re.search(r'Hardware\s+type\s*:\s*(\S+)', version_output)
                if m:
                    model = m.group(1)
            m = re.search(r'Software\s+Version\s*(\S+)', version_output)
            if m:
                version = m.group(1)
        if not version:
            m = re.search(r'Version\s+([\d.]+)', version_output)
            if m:
                version = m.group(1)
        if connection:
            try:
                esn_output = connection.send_command("display esn", delay_factor=2)
                m = re.search(r'SN\s*:\s*(\S+)', esn_output)
                if m:
                    serial = m.group(1)
            except Exception:
                pass
        return ParsedDeviceInfo(model=model, version=version, serial=serial, uptime=uptime, brand="Huawei")


    def parse_mac_table(self, raw_output: str) -> list:
        template_path = os.path.join(TEMPLATE_DIR, "huawei_vrp_display_mac-address.textfsm")
        results = self._parse_with_textfsm(raw_output, template_path, self._map_mac_row)
        return results

    @staticmethod
    def _map_mac_row(header, row) -> "ParsedMacEntry":
        h = header
        vlan_raw = HuaweiAdapter._get_col(h, row, "VLAN_ID")
        vlan = vlan_raw.split("/")[0] if vlan_raw and "/" in vlan_raw else (vlan_raw or "")
        return ParsedMacEntry(
            mac_address=HuaweiAdapter._get_col(h, row, "DESTINATION_ADDRESS"),
            vlan=vlan,
            port=HuaweiAdapter._get_col(h, row, "DESTINATION_PORT"),
            entry_type=(HuaweiAdapter._get_col(h, row, "TYPE") or "").lower(),
        )


    def parse_port_description(self, config_text: str) -> str:
        m = _RE_DESCRIPTION.search(config_text)
        return m.group(1).strip() if m else ""

    def parse_qos_policies(self, config_text: str) -> list[tuple[str, str]]:
        return [(m.group(1), m.group(2)) for m in _RE_TRAFFIC_POLICY.finditer(config_text)]

    def parse_trunk_id(self, config_text: str) -> Optional[int]:
        m = _RE_ETH_TRUNK.search(config_text)
        return int(m.group(1)) if m else None

    def parse_vlan_info(self, config_text: str) -> dict:
        if _RE_L3_PORT.search(config_text):
            return {"mode": None, "pvid": None, "allowed_vlans": None}

        mode = None
        pvid = None
        allowed_vlans = None

        m_access = _RE_ACCESS_VLAN.search(config_text)
        if m_access:
            mode = "access"
            pvid = int(m_access.group(1))

        m_trunk_pvid = _RE_TRUNK_PVID.search(config_text)
        m_trunk_allow = _RE_TRUNK_ALLOW.search(config_text)
        if m_trunk_pvid or m_trunk_allow:
            mode = "trunk"
            if m_trunk_pvid:
                pvid = int(m_trunk_pvid.group(1))
            if m_trunk_allow:
                allowed_vlans = m_trunk_allow.group(1).strip()

        return {"mode": mode, "pvid": pvid, "allowed_vlans": allowed_vlans}


    @staticmethod
    def _map_route_row(header, row) -> ParsedRoute:
        h = header
        dest = HuaweiAdapter._get_col(h, row, "DESTINATION")
        prefix = HuaweiAdapter._get_col(h, row, "PREFIX_LENGTH")
        network = f"{dest}/{prefix}" if dest and prefix else dest

        nexthop = HuaweiAdapter._get_col(h, row, "NEXT_HOP")
        if nexthop in ("127.0.0.1", "0.0.0.0"):
            relay_nh = HuaweiAdapter._get_col(h, row, "RELAY_NEXT_HOP")
            if relay_nh and relay_nh not in ("127.0.0.1", "0.0.0.0", ""):
                nexthop = relay_nh

        return ParsedRoute(
            network=network,
            nexthop=nexthop,
            interface=HuaweiAdapter._get_col(h, row, "INTERFACE"),
            flags=HuaweiAdapter._get_col(h, row, "FLAGS"),
            protocol=HuaweiAdapter._get_col(h, row, "PROTOCOL"),
        )

    @staticmethod
    def _map_arp_row(header, row) -> ParsedArpEntry:
        h = header
        type_vlan = HuaweiAdapter._get_col(h, row, "TYPE_VLAN")
        arp_type = ""
        vlan = ""
        if "/" in type_vlan:
            parts = type_vlan.split("/", 1)
            arp_type = parts[0]
            vlan = parts[1]
        else:
            arp_type = type_vlan
        return ParsedArpEntry(
            ip_address=HuaweiAdapter._get_col(h, row, "IP_ADDRESS"),
            mac_address=HuaweiAdapter._get_col(h, row, "MAC_ADDRESS"),
            vlan=vlan,
            interface=HuaweiAdapter._get_col(h, row, "INTERFACE"),
            type_vlan=arp_type,
        )

    @staticmethod
    def _map_port_row(header, row) -> ParsedPort:
        from app.adapters.base_adapter import normalize_port_status
        h = header
        raw_status = HuaweiAdapter._get_col(h, row, "LINK_STATUS")
        pvid_raw = HuaweiAdapter._get_col(h, row, "PVID")
        vlan = int(pvid_raw) if pvid_raw and pvid_raw.isdigit() else None
        ip_raw = HuaweiAdapter._get_col(h, row, "INTERNET_ADDRESS")
        if isinstance(ip_raw, list):
            ip_address = ",".join(ip_raw) if ip_raw else None
        elif ip_raw:
            ip_address = ip_raw
        else:
            ip_address = None
        return ParsedPort(
            port=HuaweiAdapter._get_col(h, row, "INTERFACE"),
            status=normalize_port_status(raw_status),
            vlan=vlan,
            mac=HuaweiAdapter._get_col(h, row, "HARDWARE_ADDRESS") or None,
            ip_address=ip_address,
            speed=HuaweiAdapter._get_col(h, row, "SPEED") or None,
            description=HuaweiAdapter._get_col(h, row, "INTERFACE_DESCRIPTION") or "",
        )
