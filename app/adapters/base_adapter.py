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
    """封禁/解封命令集合（黑洞路由方式）"""
    ban_cmds: list   # 添加黑洞路由的命令序列
    unban_cmds: list  # 删除黑洞路由的命令序列
    save_cmd: str     # 保存配置命令


@dataclass
class ArpBanCommands:
    """封禁/解封命令集合（静态ARP方式，用于二层网络）"""
    ban_cmds: list   # 配置静态ARP的命令序列
    unban_cmds: list  # 恢复动态ARP的命令序列
    save_cmd: str     # 保存配置命令


@dataclass
class ParsedRoute:
    """解析后的路由条目"""
    network: str     # 目的网络(CIDR)
    nexthop: str     # 下一跳
    interface: str   # 出接口
    flags: str       # 路由标志
    protocol: str    # 路由协议


@dataclass
class ParsedArpEntry:
    """解析后的ARP条目"""
    ip_address: str
    mac_address: str
    vlan: str
    interface: str
    type_vlan: str = ""


@dataclass
class ParsedMacEntry:
    """解析后的MAC地址表条目"""
    mac_address: str
    vlan: str
    port: str
    entry_type: str = ""  # dynamic / static / security


@dataclass
class ParsedPort:
    """解析后的端口条目"""
    port: str
    status: str
    vlan: Optional[int] = None
    mac: Optional[str] = None
    ip_address: Optional[str] = None
    speed: Optional[str] = None
    description: str = ""


def normalize_port_status(raw_status: str) -> str:
    """将设备原始端口状态规范化为统一值

    规范化结果：
    - "up"        — 端口链路UP
    - "down"      — 端口链路DOWN（物理down）
    - "admin_down" — 管理关闭（administratively down / *down）

    处理的原始格式：
    - 华为: "up", "down", "*down", "UP (ifindex: 16)", "DOWN (ifindex: 18)"
    - H3C:  "UP", "DOWN", "Administratively DOWN"
    - Cisco: "up", "down", "administratively down"

    Args:
        raw_status: SSH 输出的原始状态字符串

    Returns:
        str: 规范化后的状态值
    """
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
    """解析后的设备信息"""
    model: str
    version: str
    serial: str
    uptime: str
    hostname: str = ""
    brand: str = ""
    mac_address: Optional[str] = None


@dataclass
class ParsedIP:
    """解析后的IP地址"""
    ip_address: str
    subnet_mask: str
    is_primary: bool = True


class BaseDeviceAdapter(ABC):
    """设备适配层抽象基类

    每个厂商子类只需实现命令映射和 TextFSM 解析。
    SSH 连接由 SSHManager（infra层）统一管理。
    """

    def get_route_command(self) -> str:
        """获取路由表查询命令"""
        return "display ip routing-table verbose"

    def get_arp_command(self) -> str:
        """获取ARP表查询命令

        使用 display arp 而非 display arp all，
        部分华为VRP版本不支持 all 参数会报错。
        """
        return "display arp"

    def get_mac_command(self) -> str:
        """获取MAC地址表查询命令"""
        return "display mac-address"

    def get_interface_command(self) -> str:
        """获取接口信息查询命令"""
        return "display interface"

    def get_interface_status_command(self, port: str) -> str:
        """获取单端口实际链路状态的查询命令

        用于启用/禁用单端口后从设备读取真实链路状态（替代硬编码 up/admin_down），
        输出为单端口明细，可经 parse_ports 解析出该端口实际 status。

        Args:
            port: 端口名称

        Returns:
            str: 查询命令
        """
        return f"display interface {self._validate_port_name(port)}"

    def get_version_command(self) -> str:
        """获取设备版本查询命令"""
        return "display version"

    def get_sysname_command(self) -> str:
        """获取设备主机名查询命令（华为/H3C: display sysname, Cisco: show hostname）"""
        return "display sysname"

    def parse_sysname(self, raw_output: str) -> str:
        """解析 sysname 命令输出，提取主机名

        典型输出：设备直接返回主机名字符串，可能被尖括号或方括号包裹。
        部分设备返回错误信息或特殊字符（如 ^），需过滤。
        """
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
        """获取端口VLAN查询命令（可选，默认返回空）"""
        return ""

    def parse_port_vlans(self, raw_output: str) -> dict:
        """解析端口VLAN映射，返回 {端口名: vlan_id} 字典"""
        return {}

    @abstractmethod
    def get_ban_commands(self, ip_address: str, device_model: str = "") -> BanCommands:
        """获取封禁/解封命令集（黑洞路由方式，用于三层网络）

        Args:
            ip_address: 需要封禁的IP地址
            device_model: 设备型号，部分厂商需根据型号调整命令格式

        Returns:
            BanCommands: 命令集合
        """
        ...

    @abstractmethod
    def get_arp_ban_commands(
        self, ip_address: str, mac_address: str, vlan_id: int, device_model: str = "",
    ) -> ArpBanCommands:
        """获取封禁/解封命令集（静态ARP方式，用于二层网络）

        原理：在网关交换机上配置静态ARP，将IP绑定到不存在的MAC地址，
        使该IP的流量无法正常转发，达到封禁效果。
        相比黑洞路由方式，不会增加路由表条目。

        Args:
            ip_address: 需要封禁的IP地址
            mac_address: 该IP的真实MAC地址（用于解封恢复）
            vlan_id: VLAN ID
            device_model: 设备型号，部分厂商需根据型号调整命令格式

        Returns:
            ArpBanCommands: 命令集合
        """
        ...

    @abstractmethod
    def parse_routes(self, raw_output: str) -> list[ParsedRoute]:
        """解析路由表原始输出

        Args:
            raw_output: 交换机命令原始输出

        Returns:
            list[ParsedRoute]: 解析后的路由列表
        """
        ...

    @abstractmethod
    def parse_arp(self, raw_output: str) -> list[ParsedArpEntry]:
        """解析ARP表原始输出

        Args:
            raw_output: 交换机命令原始输出

        Returns:
            list[ParsedArpEntry]: 解析后的ARP列表
        """
        ...

    @abstractmethod
    def parse_ports(self, raw_output: str) -> list[ParsedPort]:
        """解析接口信息原始输出

        Args:
            raw_output: 交换机命令原始输出

        Returns:
            list[ParsedPort]: 解析后的端口列表
        """
        ...


    @staticmethod
    def _sanitize_cli_value(value: str, *, max_len: int = 255, field: str = "value") -> str:
        """清洗自由文本型 CLI 参数，阻断注入载体。

        仅允许「无控制字符、无分号/反引号」的普通文本。用于 description、
        端口范围表达式、VLAN 范围字符串等自由或半结构化参数。命中非法字符
        或超长时抛出 ValidationError(400)。
        """
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
        """校验端口名称，返回安全端口名或抛出 ValidationError(400)。"""
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
        """校验 IPv4/IPv6 地址或子网掩码，返回原值或抛出 ValidationError(400)。"""
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
        """校验 MAC 地址格式，返回原值或抛出 ValidationError(400)。

        兼容 00:11:22:33:44:55 / 0011-2233-4455 / 0000.0000.0001 等标准表示：
        去除分隔符后必须为 12 位十六进制。
        """
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
        """校验 VLAN ID 合法范围 (1-4094)。"""
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
        """进入接口配置模式命令"""
        return f"interface {self._validate_port_name(port)}"

    def get_interface_range_command(self, port_expr: str) -> str:
        """构造 interface range 命令，批量进入多个接口视图

        Args:
            port_expr: 端口范围表达式，如 "10GE1/0/1 to 10GE1/0/10"
                       或离散列表拼接 "10GE1/0/1 10GE1/0/3 10GE1/0/5"

        Returns:
            str: 完整的 interface range 命令
        """
        return f"interface range {self._sanitize_cli_value(port_expr, max_len=256, field='port_range')}"

    def get_set_ip_command(self, ip: str, mask: str) -> str:
        """设置IP地址命令"""
        return f"ip address {self._validate_ip(ip)} {self._validate_ip(mask)}"

    def get_set_secondary_ip_command(self, ip: str, mask: str) -> str:
        """设置从IP地址命令"""
        return f"ip address {self._validate_ip(ip)} {self._validate_ip(mask)} sub"

    def get_undo_ip_command(self, ip: str, mask: str, is_secondary: bool = False) -> str:
        """删除IP地址命令

        Args:
            ip: IP地址
            mask: 子网掩码
            is_secondary: 是否为从IP，从IP需加sub关键字
        """
        sub = " sub" if is_secondary else ""
        return f"undo ip address {self._validate_ip(ip)} {self._validate_ip(mask)}{sub}"

    def get_shutdown_command(self) -> str:
        """关闭端口命令"""
        return "shutdown"

    def get_undo_shutdown_command(self) -> str:
        """开启端口命令"""
        return "undo shutdown"

    def get_description_command(self, description: str) -> str:
        """设置端口描述命令"""
        return f"description {self._sanitize_cli_value(description, max_len=240, field='description')}"

    def get_undo_description_command(self) -> str:
        """删除端口描述命令"""
        return "undo description"

    def get_exit_interface_command(self) -> str:
        """退出接口配置命令"""
        return "quit"

    def get_create_vlan_command(self, vlan_id: int) -> str:
        """创建VLAN命令"""
        return f"vlan {self._validate_vlan_id(vlan_id)}"

    @abstractmethod
    def get_interface_vlan_command(self, vlan_id: int) -> str:
        """进入VLAN接口命令"""
        ...

    @abstractmethod
    def get_set_access_vlan_command(self, vlan_id: int) -> str:
        """设置Access VLAN命令"""
        ...

    def get_portswitch_command(self) -> str:
        """切换端口为二层模式（配置VLAN前需要）"""
        return ""

    def get_undo_portswitch_command(self) -> str:
        """切换端口为三层模式（配置IP地址前需要）"""
        return ""

    def get_set_trunk_command(self) -> str:
        """设置Trunk模式命令"""
        return "port link-type trunk"

    @abstractmethod
    def get_trunk_allow_command(self, vlans: str, device_model: str = "") -> str:
        """设置Trunk允许VLAN命令

        Args:
            vlans: VLAN 范围字符串
            device_model: 设备型号（部分厂商需根据型号调整格式）
        """
        ...

    def get_trunk_pvid_command(self, vlan_id: int) -> str:
        """设置Trunk端口PVID（Native VLAN）命令

        华为/H3C: port trunk pvid vlan {vlan_id}
        Cisco 由子类覆写
        """
        return f"port trunk pvid vlan {self._validate_vlan_id(vlan_id)}"

    def get_check_vlan_command(self, vlan_id: int) -> str:
        """检查VLAN存在命令"""
        return f"display vlan {self._validate_vlan_id(vlan_id)}"

    def get_list_all_vlans_command(self) -> str:
        """列出所有VLAN及其成员端口命令"""
        return "display vlan"

    def get_list_all_trunks_command(self) -> str:
        """列出所有链路聚合及其成员端口命令"""
        return "display eth-trunk"

    def get_delete_vlan_command(self, vlan_id: int) -> str:
        """删除VLAN命令"""
        return f"undo vlan {self._validate_vlan_id(vlan_id)}"

    def get_delete_interface_command(self, port: str) -> str:
        """删除接口命令（LoopBack等虚拟接口）"""
        return f"undo interface {self._validate_port_name(port)}"

    @abstractmethod
    def get_create_trunk_command(self, channel_id: int) -> str:
        """创建链路聚合命令"""
        ...

    @abstractmethod
    def get_delete_trunk_command(self, channel_id: int) -> str:
        """删除链路聚合命令"""
        ...

    @abstractmethod
    def get_add_member_command(self, channel_id: int) -> str:
        """添加成员端口命令"""
        ...

    @abstractmethod
    def get_remove_member_command(self) -> str:
        """移除成员端口命令"""
        ...

    @abstractmethod
    def get_check_trunk_command(self, channel_id: int) -> str:
        """检查链路聚合命令"""
        ...

    def get_clear_config_command(self, port: str) -> str:
        """清除指定端口配置命令（系统视图下执行）

        华为/H3C: clear configuration interface <port>
        该命令会触发 [Y/N] 确认提示，需配合交互式命令使用。
        清除后端口会变为 shutdown 状态，需执行 undo shutdown 恢复。

        Args:
            port: 端口名称（如 10GE1/0/1）

        Returns:
            str: 清除配置命令
        """
        return f"clear configuration interface {self._validate_port_name(port)}"


    def get_port_max_speed(self, port: str) -> int:
        """根据端口名称推算最大速率（Mbps）

        从端口名称前缀识别端口类型，返回对应的速率上限。
        各厂商端口命名规则：
        - 华为: 10GE, XGE, GE, 40GE, 25GE, 100GE, FE
        - H3C:  Ten-GigabitEthernet, GigabitEthernet, HundredGigE, FortyGigE, TwentyFiveGigE
        - Cisco: GigabitEthernet, TenGigabitEthernet, TwentyFiveGigE, FortyGigE, HundredGigE

        Args:
            port: 端口名称（如 10GE1/0/1、GigabitEthernet1/0/1）

        Returns:
            int: 最大速率（Mbps），无法识别时默认 10000
        """
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
        return 10000  # 兜底

    def get_qos_policy_name(self, direction: str, speed_mbps: int) -> str:
        """生成 QoS 策略名称（按方向+限速值，不绑定端口，便于多端口复用）

        命名规则：LIMIT_{DIR}_{SPEED}M
        同一（方向, 限速值）只生成一份策略，其它同值端口直接引用，
        避免按端口生成海量重复策略（如 LIMIT_100GE1_0_1_IN_1000M）。

        Args:
            direction: 方向（inbound/outbound）
            speed_mbps: 限速值（Mbps）

        Returns:
            str: 策略名称（如 LIMIT_IN_1000M / LIMIT_OUT_1200M）
        """
        dir_short = "IN" if direction == "inbound" else "OUT"
        return f"LIMIT_{dir_short}_{speed_mbps}M"

    def get_create_qos_policy_commands(
        self, policy_name: str, cir_kbps: int,
    ) -> list:
        """创建 QoS 策略定义命令（classifier + behavior + policy）

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
            f"traffic policy {policy_name}",
            f"classifier {policy_name} behavior {policy_name}",
            "quit",
        ]

    def get_apply_qos_policy_command(
        self, policy_name: str, direction: str,
    ) -> str:
        """在接口下应用 QoS 策略命令

        Args:
            policy_name: 策略名称
            direction: 方向（inbound/outbound）

        Returns:
            str: 应用策略命令
        """
        return f"traffic-policy {policy_name} {direction}"

    def get_undo_apply_qos_policy_command(self, direction: str, policy_name: str = "") -> str:
        """取消接口下 QoS 策略引用命令

        华为CE要求 undo traffic-policy 必须指定策略名和方向，
        非CE设备支持 undo traffic-policy {direction} 简写。
        传入 policy_name 时生成完整格式，否则使用简写格式。

        Args:
            direction: 方向（inbound/outbound）
            policy_name: 策略名称（华为CE必须指定）

        Returns:
            str: 取消策略引用命令
        """
        if policy_name:
            return f"undo traffic-policy {policy_name} {direction}"
        return f"undo traffic-policy {direction}"

    def get_qos_policy_query_command(self, policy_name: str) -> str:
        """查询设备上指定 QoS 策略是否存在的命令（华为 traffic-policy）

        子类（如 H3C）应按厂商覆盖为对应查询命令。
        """
        return f"display traffic policy {policy_name}"

    @staticmethod
    def is_qos_policy_missing(output: str) -> bool:
        """根据查询回显判断策略是否不存在

        命中 "does not exist" / "不存在" 视为不存在；其余视为已存在。
        用于限速策略去重：已存在则跳过创建、仅引用。

        Args:
            output: display 命令回显

        Returns:
            bool: True 表示策略不存在
        """
        if not output:
            return False
        low = output.lower()
        return "does not exist" in low or "不存在" in low

    def get_delete_qos_policy_commands(self, policy_name: str) -> list:
        """删除 QoS 策略定义命令（policy → behavior → classifier）

        Args:
            policy_name: 策略名称

        Returns:
            list: 删除策略的命令序列
        """
        return [
            f"undo traffic policy {policy_name}",
            f"undo traffic behavior {policy_name}",
            f"undo traffic classifier {policy_name}",
        ]

    def get_delete_route_command(self, network: str, mask: str, nexthop: str) -> str:
        """删除静态路由命令"""
        return (
            f"undo ip route-static "
            f"{self._sanitize_cli_value(network, field='network')} "
            f"{self._validate_ip(mask)} "
            f"{self._sanitize_cli_value(nexthop, field='nexthop')}"
        )

    def get_save_command(self, device_model: str = "") -> str:
        """保存配置命令

        Args:
            device_model: 设备型号，子类可据此区分命令差异
        """
        return "save"

    @abstractmethod
    def get_commit_command(self) -> Optional[str]:
        """提交配置命令(CE系列)，无则返回None"""
        ...

    def get_system_view_command(self) -> str:
        """进入系统视图命令"""
        return "system-view"

    def get_return_command(self) -> str:
        """退回到用户视图命令"""
        return "return"

    @abstractmethod
    def parse_device_info(self, version_output: str, connection=None) -> 'ParsedDeviceInfo':
        """解析设备信息"""
        ...

    def is_ce_model(self, device_model: str) -> bool:
        """判断是否为华为 CloudEngine 系列（影响配置模式）

        Args:
            device_model: 设备型号字符串

        Returns:
            bool: 是CE型号返回True
        """
        return "CE" in (device_model or "").upper()


    @staticmethod
    def parse_vlan_ranges(vlans_str: str) -> list[tuple[int, int]]:
        """解析 VLAN 范围字符串为 (start, end) 元组列表

        支持格式: "1-10,20,30-40" → [(1,10), (20,20), (30,40)]
        也支持: "1 to 10 20 30 to 40" → [(1,10), (20,20), (30,40)]

        Args:
            vlans_str: VLAN 范围字符串

        Returns:
            list[tuple[int, int]]: (起始VLAN, 结束VLAN) 元组列表
        """
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
        """将 VLAN 范围列表格式化为华为 CE 系列语法

        CE 系列要求: 范围用 "to" 关键字，多个值用空格分隔
        例: [(1,10), (20,20), (30,40)] → "1 to 10 20 30 to 40"

        Args:
            ranges: (起始VLAN, 结束VLAN) 元组列表

        Returns:
            str: CE 格式的 VLAN 字符串
        """
        parts = []
        for start, end in ranges:
            if start == end:
                parts.append(str(start))
            else:
                parts.append(f"{start} to {end}")
        return " ".join(parts)

    @staticmethod
    def format_vlans_vrp(ranges: list[tuple[int, int]]) -> str:
        """将 VLAN 范围列表格式化为华为 VRP (S系列) 语法

        VRP 系列支持: 连字符范围 + 逗号分隔
        例: [(1,10), (20,20), (30,40)] → "1-10,20,30-40"

        Args:
            ranges: (起始VLAN, 结束VLAN) 元组列表

        Returns:
            str: VRP 格式的 VLAN 字符串
        """
        parts = []
        for start, end in ranges:
            if start == end:
                parts.append(str(start))
            else:
                parts.append(f"{start}-{end}")
        return ",".join(parts)


    @staticmethod
    def _parse_with_textfsm(raw_output: str, template_path: str, row_mapper) -> list:
        """使用 TextFSM 模板解析输出（每次创建新实例，确保线程安全）"""
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
        """安全获取 TextFSM 行中指定列的值（所有子类共用）"""
        try:
            return row[header.index(col_name)]
        except (ValueError, IndexError):
            return default

    def parse_mac_table(self, raw_output: str) -> list:
        """解析 MAC 地址表（华为/H3C 格式默认实现，Cisco 等子类可按需覆盖）

        支持两种 VLAN 列格式：
        - 纯数字: "3" (老格式)
        - VLAN/BD: "3/-" (新格式，华为CE系列)
        """
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
        """从配置文本解析现有IP地址（华为/H3C 格式默认实现，Cisco 子类已覆盖）"""
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
        """从端口配置文本解析 Eth-Trunk / Bridge-Aggregation / Port-channel ID

        各厂商配置格式：
        - 华为: "eth-trunk 10"
        - H3C:  "port link-aggregation group 10"
        - Cisco: "channel-group 10 mode active"

        Args:
            config_text: display current-configuration interface <port> 的输出

        Returns:
            Trunk ID（如 10），不属于任何 Trunk 时返回 None
        """
        ...

    @abstractmethod
    def parse_vlan_info(self, config_text: str) -> dict:
        """从端口配置文本解析 VLAN 信息

        各厂商配置格式：
        - 华为: port default vlan 10 / port trunk pvid vlan 10 / port trunk allow-pass vlan 10
        - H3C:  port access vlan 10 / port trunk pvid vlan 10 / port trunk permit vlan 10
        - Cisco: switchport access vlan 10 / switchport trunk native vlan 10

        三层口判断：
        - 华为: ip address / undo portswitch
        - H3C:  ip address / portlink-mode route
        - Cisco: no switchport / ip address

        Args:
            config_text: display current-configuration interface <port> 的输出

        Returns:
            dict: {
                "mode": "access" | "trunk" | None,   # None 表示三层口
                "pvid": int | None,                   # 默认 VLAN ID，三层口为 None
                "allowed_vlans": str | None,          # Trunk 允许的 VLAN 范围字符串
            }
        """
        ...

    @abstractmethod
    def parse_port_description(self, config_text: str) -> str:
        """从端口配置文本解析描述

        各厂商配置格式：
        - 华为/H3C: "description <text>"
        - Cisco:    "description <text>"

        Args:
            config_text: display current-configuration interface <port> 的输出

        Returns:
            str: 描述文本，无描述时返回空字符串
        """
        ...

    @abstractmethod
    def parse_qos_policies(self, config_text: str) -> list[tuple[str, str]]:
        """从端口配置文本解析已应用的 QoS 策略名和方向

        各厂商配置格式：
        - 华为: "traffic-policy LIMIT_XXX inbound"
        - H3C:  "qos apply policy LIMIT_XXX inbound"
        - Cisco: 暂无对应格式

        Args:
            config_text: display current-configuration interface <port> 的输出

        Returns:
            list[tuple[str, str]]: [(policy_name, direction), ...]
            direction 为 "inbound" 或 "outbound"
        """
        ...