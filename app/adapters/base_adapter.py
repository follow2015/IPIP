# -*- coding: utf-8 -*-
"""
设备适配层抽象基类

定义交换机命令映射和输出解析的抽象接口，
每个厂商子类只需实现命令映射和 TextFSM 解析。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import os
import re
import ipaddress
from app.utils.logging import get_logger
from app.exceptions.validation import ValidationError

logger = get_logger(__name__)

_DANGEROUS_CLI_PATTERN = re.compile(r'[\n\r\x00-\x1f;`]')
_PORT_NAME_PATTERN = re.compile(r'^[A-Za-z0-9/_.\-]+$')


@dataclass
class BanCommands:
    ban_cmds: list
    unban_cmds: list
    save_cmd: str


@dataclass
class ArpBanCommands:
    ban_cmds: list
    unban_cmds: list
    save_cmd: str


@dataclass
class ParsedRoute:
    network: str
    nexthop: str
    interface: str
    flags: str
    protocol: str


@dataclass
class ParsedArpEntry:
    ip_address: str
    mac_address: str
    vlan: str
    interface: str
    type_vlan: str = ""


@dataclass
class ParsedMacEntry:
    mac_address: str
    vlan: str
    port: str
    entry_type: str = ""


@dataclass
class ParsedPort:
    port: str
    status: str
    vlan: Optional[int] = None
    mac: Optional[str] = None
    ip_address: Optional[str] = None
    speed: Optional[str] = None
    description: str = ""


def normalize_port_status(raw_status: str) -> str:
    if not raw_status:
        return "down"
    s = raw_status.strip().lower()
    if s in ("up", "down", "admin_down"):
        return s
    if "(ifindex:" in s:
        s = s.split("(ifindex:")[0].strip()
    if "administratively" in s or s == "*down":
        return "admin_down"
    if s in ("up", "*up"):
        return "up"
    if s in ("down",):
        return "down"
    return "down"


@dataclass
class ParsedDeviceInfo:
    model: str
    version: str
    serial: str
    uptime: str
    hostname: str = ""
    brand: str = ""
    mac_address: Optional[str] = None


@dataclass
class ParsedIP:
    ip_address: str
    subnet_mask: str
    is_primary: bool = True


class BaseDeviceAdapter(ABC):

    def get_route_command(self) -> str:
        return "display ip routing-table verbose"

    def get_arp_command(self) -> str:
        return "display arp"

    def get_mac_command(self) -> str:
        return "display mac-address"

    def get_interface_command(self) -> str:
        return "display interface"

    def get_interface_status_command(self, port: str) -> str:
        return f"display interface {self._validate_port_name(port)}"

    def get_version_command(self) -> str:
        return "display version"

    def get_sysname_command(self) -> str:
        return "display sysname"

    def parse_sysname(self, raw_output: str) -> str:
        if not raw_output:
            return ""
        name = raw_output.strip()
        if (name.startswith("<") and name.endswith(">")) or \
           (name.startswith("[") and name.endswith("]")):
            name = name[1:-1]
        name = name.splitlines()[0].strip()
        if not name or len(name) < 2:
            return ""
        _INVALID_PREFIXES = ("error", "info:", "warning:", "unknown", "incomplete", "unrecognized")
        if name.lower().startswith(_INVALID_PREFIXES):
            return ""
        if not re.match(r'^[a-zA-Z0-9]', name):
            return ""
        return name

    def get_port_vlan_command(self) -> str:
        return ""

    def parse_port_vlans(self, raw_output: str) -> dict:
        return {}

    @abstractmethod
    def get_ban_commands(self, ip_address: str, device_model: str = "") -> BanCommands:
        ...

    @abstractmethod
    def get_arp_ban_commands(
        self, ip_address: str, mac_address: str, vlan_id: int, device_model: str = "",
    ) -> ArpBanCommands:
        ...

    @abstractmethod
    def parse_routes(self, raw_output: str) -> list[ParsedRoute]:
        ...

    @abstractmethod
    def parse_arp(self, raw_output: str) -> list[ParsedArpEntry]:
        ...

    @abstractmethod
    def parse_ports(self, raw_output: str) -> list[ParsedPort]:
        ...


    @staticmethod
    def _sanitize_cli_value(value: str, *, max_len: int = 255, field: str = "value") -> str:
        if value is None or not isinstance(value, str):
            raise ValidationError(
                message=f"{field} 必须为非空字符串",
                field=field,
                details={"value": repr(value)},
            )
        if _DANGEROUS_CLI_PATTERN.search(value):
            raise ValidationError(
                message=f"{field} 包含非法字符（控制字符、分号或反引号）",
                field=field,
                details={"value": value},
            )
        if len(value) > max_len:
            raise ValidationError(
                message=f"{field} 长度超过上限 {max_len}",
                field=field,
                details={"length": len(value)},
            )
        return value

    def _validate_port_name(self, port: str) -> str:
        port = self._sanitize_cli_value(port, max_len=64, field="port")
        if not _PORT_NAME_PATTERN.match(port):
            raise ValidationError(
                message=f"端口名称格式非法: {port!r}",
                field="port",
                details={"value": port},
            )
        return port

    @staticmethod
    def _validate_ip(value: str, *, field: str = "ip") -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(message=f"{field} 不能为空", field=field)
        try:
            ipaddress.ip_address(value.strip())
        except ValueError:
            raise ValidationError(
                message=f"{field} 不是合法的 IP 地址: {value!r}",
                field=field,
                details={"value": value},
            )
        return value.strip()

    @staticmethod
    def _validate_mac(mac: str, *, field: str = "mac") -> str:
        if not isinstance(mac, str) or not mac.strip():
            raise ValidationError(message=f"{field} 不能为空", field=field)
        m = mac.strip()
        stripped = re.sub(r"[:.-]", "", m)
        if len(stripped) != 12 or not re.fullmatch(r"[0-9A-Fa-f]{12}", stripped):
            raise ValidationError(
                message=f"{field} 不是合法的 MAC 地址: {mac!r}",
                field=field,
                details={"value": mac},
            )
        return m

    @staticmethod
    def _validate_vlan_id(vlan_id: int, *, field: str = "vlan_id") -> int:
        try:
            vid = int(vlan_id)
        except (TypeError, ValueError):
            raise ValidationError(message=f"{field} 必须为整数", field=field)
        if vid < 1 or vid > 4094:
            raise ValidationError(
                message=f"{field} 超出合法范围 1-4094: {vlan_id!r}",
                field=field,
                details={"value": vlan_id},
            )
        return vid

    def get_enter_interface_command(self, port: str) -> str:
        return f"interface {self._validate_port_name(port)}"

    def get_interface_range_command(self, port_expr: str) -> str:
        return f"interface range {self._sanitize_cli_value(port_expr, max_len=256, field='port_range')}"

    def get_set_ip_command(self, ip: str, mask: str) -> str:
        return f"ip address {self._validate_ip(ip)} {self._validate_ip(mask)}"

    def get_set_secondary_ip_command(self, ip: str, mask: str) -> str:
        return f"ip address {self._validate_ip(ip)} {self._validate_ip(mask)} sub"

    def get_undo_ip_command(self, ip: str, mask: str, is_secondary: bool = False) -> str:
        sub = " sub" if is_secondary else ""
        return f"undo ip address {self._validate_ip(ip)} {self._validate_ip(mask)}{sub}"

    def get_shutdown_command(self) -> str:
        return "shutdown"

    def get_undo_shutdown_command(self) -> str:
        return "undo shutdown"

    def get_description_command(self, description: str) -> str:
        return f"description {self._sanitize_cli_value(description, max_len=240, field='description')}"

    def get_undo_description_command(self) -> str:
        return "undo description"

    def get_exit_interface_command(self) -> str:
        return "quit"

    def get_create_vlan_command(self, vlan_id: int) -> str:
        return f"vlan {self._validate_vlan_id(vlan_id)}"

    @abstractmethod
    def get_interface_vlan_command(self, vlan_id: int) -> str:
        ...

    @abstractmethod
    def get_set_access_vlan_command(self, vlan_id: int) -> str:
        ...

    def get_portswitch_command(self) -> str:
        return ""

    def get_undo_portswitch_command(self) -> str:
        return ""

    def get_set_trunk_command(self) -> str:
        return "port link-type trunk"

    @abstractmethod
    def get_trunk_allow_command(self, vlans: str, device_model: str = "") -> str:
        ...

    def get_trunk_pvid_command(self, vlan_id: int) -> str:
        return f"port trunk pvid vlan {self._validate_vlan_id(vlan_id)}"

    def get_check_vlan_command(self, vlan_id: int) -> str:
        return f"display vlan {self._validate_vlan_id(vlan_id)}"

    def get_list_all_vlans_command(self) -> str:
        return "display vlan"

    def get_list_all_trunks_command(self) -> str:
        return "display eth-trunk"

    def get_delete_vlan_command(self, vlan_id: int) -> str:
        return f"undo vlan {self._validate_vlan_id(vlan_id)}"

    def get_delete_interface_command(self, port: str) -> str:
        return f"undo interface {self._validate_port_name(port)}"

    @abstractmethod
    def get_create_trunk_command(self, channel_id: int) -> str:
        ...

    @abstractmethod
    def get_delete_trunk_command(self, channel_id: int) -> str:
        ...

    @abstractmethod
    def get_add_member_command(self, channel_id: int) -> str:
        ...

    @abstractmethod
    def get_remove_member_command(self) -> str:
        ...

    @abstractmethod
    def get_check_trunk_command(self, channel_id: int) -> str:
        ...

    def get_clear_config_command(self, port: str) -> str:
        return f"clear configuration interface {self._validate_port_name(port)}"


    def get_port_max_speed(self, port: str) -> int:
        p = port.upper()
        if "100GE" in p or "HUNDREDGIG" in p:
            return 100000
        if "40GE" in p or "FORTYGIG" in p:
            return 40000
        if "25GE" in p or "TWENTYFIVEGIG" in p:
            return 25000
        if "10GE" in p or "XGE" in p or "TENGIG" in p or "TEN-GIG" in p:
            return 10000
        if "GE" in p or "GIGABIT" in p:
            return 1000
        if "FE" in p or "FAST" in p or "100M" in p:
            return 100
        return 10000

    def get_qos_policy_name(self, direction: str, speed_mbps: int) -> str:
        dir_short = "IN" if direction == "inbound" else "OUT"
        return f"LIMIT_{dir_short}_{speed_mbps}M"

    def get_create_qos_policy_commands(
        self, policy_name: str, cir_kbps: int,
    ) -> list:
        return [
            f"traffic classifier {policy_name}",
            "if-match any",
            "quit",
            f"traffic behavior {policy_name}",
            f"car cir {cir_kbps}",
            "quit",
            f"traffic policy {policy_name}",
            f"classifier {policy_name} behavior {policy_name}",
            "quit",
        ]

    def get_apply_qos_policy_command(
        self, policy_name: str, direction: str,
    ) -> str:
        return f"traffic-policy {policy_name} {direction}"

    def get_undo_apply_qos_policy_command(self, direction: str, policy_name: str = "") -> str:
        if policy_name:
            return f"undo traffic-policy {policy_name} {direction}"
        return f"undo traffic-policy {direction}"

    def get_qos_policy_query_command(self, policy_name: str) -> str:
        return f"display traffic policy {policy_name}"

    @staticmethod
    def is_qos_policy_missing(output: str) -> bool:
        if not output:
            return False
        low = output.lower()
        return "does not exist" in low or "不存在" in low

    def get_delete_qos_policy_commands(self, policy_name: str) -> list:
        return [
            f"undo traffic policy {policy_name}",
            f"undo traffic behavior {policy_name}",
            f"undo traffic classifier {policy_name}",
        ]

    def get_delete_route_command(self, network: str, mask: str, nexthop: str) -> str:
        return (
            f"undo ip route-static "
            f"{self._sanitize_cli_value(network, field='network')} "
            f"{self._validate_ip(mask)} "
            f"{self._sanitize_cli_value(nexthop, field='nexthop')}"
        )

    def get_save_command(self, device_model: str = "") -> str:
        return "save"

    @abstractmethod
    def get_commit_command(self) -> Optional[str]:
        ...

    def get_system_view_command(self) -> str:
        return "system-view"

    def get_return_command(self) -> str:
        return "return"

    @abstractmethod
    def parse_device_info(self, version_output: str, connection=None) -> 'ParsedDeviceInfo':
        ...

    def is_ce_model(self, device_model: str) -> bool:
        return "CE" in (device_model or "").upper()


    @staticmethod
    def parse_vlan_ranges(vlans_str: str) -> list[tuple[int, int]]:
        if not vlans_str or not vlans_str.strip():
            return []
        s = vlans_str.strip()
        s = re.sub(r'\s+to\s+', '-', s)
        ranges = []
        for part in re.split(r'[,\s]+', s):
            part = part.strip()
            if not part:
                continue
            if '-' in part:
                bounds = part.split('-', 1)
                try:
                    start, end = int(bounds[0]), int(bounds[1])
                    ranges.append((start, end))
                except ValueError:
                    continue
            else:
                try:
                    vid = int(part)
                    ranges.append((vid, vid))
                except ValueError:
                    continue
        return ranges

    @staticmethod
    def format_vlans_ce(ranges: list[tuple[int, int]]) -> str:
        parts = []
        for start, end in ranges:
            if start == end:
                parts.append(str(start))
            else:
                parts.append(f"{start} to {end}")
        return " ".join(parts)

    @staticmethod
    def format_vlans_vrp(ranges: list[tuple[int, int]]) -> str:
        parts = []
        for start, end in ranges:
            if start == end:
                parts.append(str(start))
            else:
                parts.append(f"{start}-{end}")
        return ",".join(parts)


    @staticmethod
    def _parse_with_textfsm(raw_output: str, template_path: str, row_mapper) -> list:
        import textfsm

        if not os.path.exists(template_path):
            logger.warning("TextFSM 模板不存在: %s", template_path)
            return []

        with open(template_path) as f:
            fsm = textfsm.TextFSM(f)
        rows = fsm.ParseText(raw_output)
        return [row_mapper(fsm.header, row) for row in rows]

    @staticmethod
    def _get_col(header, row, col_name: str, default: str = "") -> str:
        try:
            return row[header.index(col_name)]
        except (ValueError, IndexError):
            return default

    def parse_mac_table(self, raw_output: str) -> list:
        pattern = re.compile(
            r'([0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4})\s+'
            r'(\S+)\s+(\S+)\s+(\S+)'
        )
        results = []
        for line in raw_output.splitlines():
            m = pattern.search(line)
            if m:
                vlan_raw = m.group(2)
                vlan = vlan_raw.split("/")[0] if "/" in vlan_raw else vlan_raw
                results.append(ParsedMacEntry(
                    mac_address=m.group(1), vlan=vlan,
                    port=m.group(3), entry_type=m.group(4).lower(),
                ))
        return results

    def parse_existing_ips(self, config_text: str) -> list:
        pattern = r'ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s*(sub)?'
        return [
            ParsedIP(
                ip_address=m.group(1),
                subnet_mask=m.group(2),
                is_primary=not bool(m.group(3)),
            )
            for m in re.finditer(pattern, config_text)
        ]


    @abstractmethod
    def parse_trunk_id(self, config_text: str) -> Optional[int]:
        ...

    @abstractmethod
    def parse_vlan_info(self, config_text: str) -> dict:
        ...

    @abstractmethod
    def parse_port_description(self, config_text: str) -> str:
        ...

    @abstractmethod
    def parse_qos_policies(self, config_text: str) -> list[tuple[str, str]]:
        ...
