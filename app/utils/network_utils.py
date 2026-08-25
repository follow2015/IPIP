# -*- coding: utf-8 -*-
"""
网络工具模块

提供网络相关的工具函数，包括IP地址处理、MAC地址处理、网络计算等。
"""
import ipaddress
from app.utils.logging import get_logger
import re
from typing import Any, Dict, List, Optional, Tuple

logger = get_logger(__name__)


def validate_ip_address(ip: str) -> bool:
    """验证IP地址格式

    Args:
        ip: IP地址字符串

    Returns:
        bool: 格式正确返回True
    """
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


_PORT_NAME_PATTERN = re.compile(r'^[A-Za-z0-9/:\-._]+$')


def validate_ip_network(network: str) -> bool:
    """验证IP网段格式

    Args:
        network: IP网段字符串（CIDR格式）

    Returns:
        bool: 格式正确返回True
    """
    try:
        ipaddress.ip_network(network, strict=False)
        return True
    except ValueError:
        return False


def normalize_mac_address(mac: str) -> str:
    """标准化MAC地址格式

    将MAC地址统一格式化为 xxxx-xxxx-xxxx 格式。

    Args:
        mac: MAC地址字符串

    Returns:
        str: 标准化后的MAC地址
    """
    if not mac or mac.upper() == "INCOMPLETE":
        return "N/A"

    mac_clean = re.sub(r"[.:\-]", "", mac.lower())

    if len(mac_clean) != 12:
        return mac

    return f"{mac_clean[:4]}-{mac_clean[4:8]}-{mac_clean[8:]}"


def get_status_text(status: int) -> str:
    """获取IP状态文本

    Args:
        status: 状态码（0-活跃, 1-非活跃, 2-封禁, 3-未使用）

    Returns:
        str: 状态文本
    """
    status_map = {0: "活跃", 1: "非活跃", 2: "封禁", 3: "未使用"}
    return status_map.get(status, "未知")


def get_status_color(status: int) -> str:
    """获取IP状态对应的颜色

    Args:
        status: 状态码

    Returns:
        str: Bootstrap颜色类名
    """
    color_map = {
        0: "success",  # 绿色
        1: "warning",  # 黄色
        2: "danger",  # 红色
        3: "secondary",  # 灰色
    }
    return color_map.get(status, "secondary")


def parse_interface_name(interface: str) -> Dict[str, str]:
    """解析接口名称

    提取接口类型和编号。

    Args:
        interface: 接口名称（如 GigabitEthernet0/0/1）

    Returns:
        Dict: 包含 type, number, full_name 的字典
    """
    match = re.match(r"([A-Za-z-]+)(\d+(?:/\d+)*)", interface)
    if match:
        return {"type": match.group(1), "number": match.group(2), "full_name": interface}
    return {"type": "Unknown", "number": "", "full_name": interface}


def calculate_network_usage(network: str, used_ips: List[str]) -> Dict[str, Any]:
    """计算网段使用率

    Args:
        network: 网段（CIDR格式）
        used_ips: 已使用的IP地址列表

    Returns:
        Dict: 包含 total_hosts, used_hosts, available_hosts, usage_rate 的字典
    """
    try:
        net = ipaddress.ip_network(network, strict=False)
        total_hosts = net.num_addresses - 2  # 减去网络地址和广播地址

        if total_hosts <= 0:
            total_hosts = 1

        used_count = len(used_ips)
        usage_rate = (used_count / total_hosts) * 100

        return {
            "total_hosts": total_hosts,
            "used_hosts": used_count,
            "available_hosts": total_hosts - used_count,
            "usage_rate": round(usage_rate, 2),
        }
    except Exception as e:
        logger.error(f"计算网段使用率失败: {e}")
        return {"total_hosts": 0, "used_hosts": 0, "available_hosts": 0, "usage_rate": 0}


def format_timestamp(timestamp) -> str:
    """格式化时间戳

    Args:
        timestamp: 时间戳对象

    Returns:
        str: 格式化后的时间字符串
    """
    if not timestamp:
        return "N/A"

    try:
        if hasattr(timestamp, "strftime"):
            return timestamp.strftime("%Y-%m-%d %H:%M:%S")
        return str(timestamp)
    except Exception:
        return "N/A"


def generate_ip_range(start_ip: str, end_ip: str) -> List[str]:
    """生成IP地址范围

    Args:
        start_ip: 起始IP地址
        end_ip: 结束IP地址

    Returns:
        List[str]: IP地址列表（最多1000个）
    """
    try:
        start = ipaddress.ip_address(start_ip)
        end = ipaddress.ip_address(end_ip)

        if start > end:
            start, end = end, start

        ip_list = []
        current = start
        while current <= end:
            ip_list.append(str(current))
            current += 1

            if len(ip_list) > 1000:
                break

        return ip_list
    except Exception as e:
        logger.error(f"生成IP范围失败: {e}")
        return []


def is_ip_in_network(ip_str: str, network_str: str) -> bool:
    """检查IP是否在网络范围内

    Args:
        ip_str: IP地址（可以带掩码）
        network_str: 网段（CIDR格式）

    Returns:
        bool: 在范围内返回True
    """
    try:
        if "/" in ip_str:
            ip = ipaddress.ip_address(ip_str.split("/")[0])
        else:
            ip = ipaddress.ip_address(ip_str)
        network = ipaddress.ip_network(network_str, strict=False)
        return ip in network
    except ValueError as e:
        logger.error(f"IP或网络格式错误: {e}")
        return False


def is_gateway(ip_with_prefix: str, network_str: Optional[str] = None) -> bool:
    """判断IP是否为网关地址

    网关通常是网络中的第一个可用IP地址。

    Args:
        ip_with_prefix: IP地址（可以带掩码）
        network_str: 网段（CIDR格式，可选）

    Returns:
        bool: 是网关返回True
    """
    try:
        if "/" in ip_with_prefix:
            ip_str = ip_with_prefix.split("/")[0]
            prefix_len = int(ip_with_prefix.split("/")[1])
        else:
            ip_str = ip_with_prefix
            prefix_len = 32  # 纯IP默认为32位掩码

        ip = ipaddress.ip_address(ip_str)

        if network_str:
            target_network = ipaddress.ip_network(network_str, strict=False)
            if ip not in target_network:
                return False
            prefix_len = target_network.prefixlen

        if prefix_len == 32:
            return False

        if prefix_len <= 29:
            network_address = ipaddress.ip_network(
                f"{ip}/{prefix_len}", strict=False
            ).network_address
            gateway_ip = ipaddress.ip_address(int(network_address) + 1)
            return ip == gateway_ip

        elif prefix_len == 30:
            network_address = ipaddress.ip_network(
                f"{ip}/{prefix_len}", strict=False
            ).network_address
            gateway_ip = ipaddress.ip_address(int(network_address) + 1)
            return ip == gateway_ip

        elif prefix_len == 31:
            return False

    except (ValueError, IndexError) as e:
        logger.error(f"IP或网络格式错误: {e}")
        return False

    return False


def cidr_to_subnet(cidr: str) -> Tuple[str, str]:
    """将CIDR格式转换为网络地址和子网掩码

    Args:
        cidr: CIDR格式的网段（如 192.168.1.0/24）

    Returns:
        Tuple[str, str]: (网络地址, 子网掩码)
    """
    network = ipaddress.IPv4Network(cidr, strict=False)
    return str(network.network_address), str(network.netmask)


def clean_netmiko_output(output: str) -> str:
    """清理Netmiko命令输出

    移除命令输出中的提示符、分页符等干扰内容。

    Args:
        output: 原始命令输出

    Returns:
        str: 清理后的输出
    """
    if not output:
        return output

    cleaned_output = re.sub(r"^(\[.*?\]\s*|<\w+>\s*)", "", output, flags=re.MULTILINE)

    cleaned_output = re.sub(r"^\s*return\s*$", "", cleaned_output, flags=re.MULTILINE)

    cleaned_output = cleaned_output.replace("--- more ---", "")

    cleaned_output = re.sub(r"^\s*#\s*$", "", cleaned_output, flags=re.MULTILINE)

    cleaned_output = re.sub(r"\n\s*\n", "\n", cleaned_output)

    cleaned_output = cleaned_output.strip()

    return cleaned_output


def get_network_info(network_str: str) -> Dict[str, Any]:
    """获取网络详细信息

    Args:
        network_str: 网段（CIDR格式）

    Returns:
        Dict: 包含网络详细信息的字典
    """
    try:
        if "0.0.0.0/0" in network_str:
            return {
                "network": network_str,
                "version": "IPv4",
                "total_ips": None,
                "usable_ips": None,
                "subnet_mask": None,
                "gateway": None,
                "start_ip": None,
                "end_ip": None,
                "network_address": None,
                "broadcast_address": None,
            }

        network = ipaddress.ip_network(network_str, strict=False)

        hosts = list(network.hosts())

        network_info = {
            "network": str(network),
            "version": f"IPv{network.version}",
            "total_ips": network.num_addresses,
            "usable_ips": len(hosts),
            "subnet_mask": str(network.netmask),
            "gateway": str(hosts[0]) if hosts else "N/A",
            "start_ip": str(hosts[0]) if hosts else "N/A",
            "end_ip": str(hosts[-1]) if hosts else "N/A",
            "network_address": str(network.network_address),
            "broadcast_address": str(network.broadcast_address),
        }

        return network_info

    except ValueError as e:
        logger.error(f"无效的网段格式: {e}")
        return {"error": f"无效的网段格式: {e}"}



def validate_port_name(port: str) -> bool:
    """验证端口名称格式，防止SSH命令注入

    端口名称应仅包含字母、数字、斜杠、冒号、连字符、点和下划线，
    如 GigabitEthernet0/0/1、10GE1/0/1:1、Vlanif100、Eth-Trunk10。

    Args:
        port: 端口名称字符串

    Returns:
        bool: 格式安全返回True
    """
    if not port or not isinstance(port, str):
        return False
    if len(port) > 128:
        return False
    return bool(_PORT_NAME_PATTERN.match(port))


def validate_ip_network(network: str) -> bool:
    """验证IP网段格式

    Args:
        network: IP网段字符串（CIDR格式）

    Returns:
        bool: 格式正确返回True
    """
    try:
        ipaddress.ip_network(network, strict=False)
        return True
    except ValueError:
        return False


def normalize_mac_address(mac: str) -> str:
    """标准化MAC地址格式

    将MAC地址统一格式化为 xxxx-xxxx-xxxx 格式。

    Args:
        mac: MAC地址字符串

    Returns:
        str: 标准化后的MAC地址
    """
    if not mac or mac.upper() == "INCOMPLETE":
        return "N/A"

    mac_clean = re.sub(r"[.:\-]", "", mac.lower())

    if len(mac_clean) != 12:
        return mac

    return f"{mac_clean[:4]}-{mac_clean[4:8]}-{mac_clean[8:]}"


def get_status_text(status: int) -> str:
    """获取IP状态文本

    Args:
        status: 状态码（0-活跃, 1-非活跃, 2-封禁, 3-未使用）

    Returns:
        str: 状态文本
    """
    status_map = {0: "活跃", 1: "非活跃", 2: "封禁", 3: "未使用"}
    return status_map.get(status, "未知")


def get_status_color(status: int) -> str:
    """获取IP状态对应的颜色

    Args:
        status: 状态码

    Returns:
        str: Bootstrap颜色类名
    """
    color_map = {
        0: "success",  # 绿色
        1: "warning",  # 黄色
        2: "danger",  # 红色
        3: "secondary",  # 灰色
    }
    return color_map.get(status, "secondary")


def parse_interface_name(interface: str) -> Dict[str, str]:
    """解析接口名称

    提取接口类型和编号。

    Args:
        interface: 接口名称（如 GigabitEthernet0/0/1）

    Returns:
        Dict: 包含 type, number, full_name 的字典
    """
    match = re.match(r"([A-Za-z-]+)(\d+(?:/\d+)*)", interface)
    if match:
        return {"type": match.group(1), "number": match.group(2), "full_name": interface}
    return {"type": "Unknown", "number": "", "full_name": interface}


def calculate_network_usage(network: str, used_ips: List[str]) -> Dict[str, Any]:
    """计算网段使用率

    Args:
        network: 网段（CIDR格式）
        used_ips: 已使用的IP地址列表

    Returns:
        Dict: 包含 total_hosts, used_hosts, available_hosts, usage_rate 的字典
    """
    try:
        net = ipaddress.ip_network(network, strict=False)
        total_hosts = net.num_addresses - 2  # 减去网络地址和广播地址

        if total_hosts <= 0:
            total_hosts = 1

        used_count = len(used_ips)
        usage_rate = (used_count / total_hosts) * 100

        return {
            "total_hosts": total_hosts,
            "used_hosts": used_count,
            "available_hosts": total_hosts - used_count,
            "usage_rate": round(usage_rate, 2),
        }
    except Exception as e:
        logger.error(f"计算网段使用率失败: {e}")
        return {"total_hosts": 0, "used_hosts": 0, "available_hosts": 0, "usage_rate": 0}


def format_timestamp(timestamp) -> str:
    """格式化时间戳

    Args:
        timestamp: 时间戳对象

    Returns:
        str: 格式化后的时间字符串
    """
    if not timestamp:
        return "N/A"

    try:
        if hasattr(timestamp, "strftime"):
            return timestamp.strftime("%Y-%m-%d %H:%M:%S")
        return str(timestamp)
    except Exception:
        return "N/A"


def generate_ip_range(start_ip: str, end_ip: str) -> List[str]:
    """生成IP地址范围

    Args:
        start_ip: 起始IP地址
        end_ip: 结束IP地址

    Returns:
        List[str]: IP地址列表（最多1000个）
    """
    try:
        start = ipaddress.ip_address(start_ip)
        end = ipaddress.ip_address(end_ip)

        if start > end:
            start, end = end, start

        ip_list = []
        current = start
        while current <= end:
            ip_list.append(str(current))
            current += 1

            if len(ip_list) > 1000:
                break

        return ip_list
    except Exception as e:
        logger.error(f"生成IP范围失败: {e}")
        return []


def is_ip_in_network(ip_str: str, network_str: str) -> bool:
    """检查IP是否在网络范围内

    Args:
        ip_str: IP地址（可以带掩码）
        network_str: 网段（CIDR格式）

    Returns:
        bool: 在范围内返回True
    """
    try:
        if "/" in ip_str:
            ip = ipaddress.ip_address(ip_str.split("/")[0])
        else:
            ip = ipaddress.ip_address(ip_str)
        network = ipaddress.ip_network(network_str, strict=False)
        return ip in network
    except ValueError as e:
        logger.error(f"IP或网络格式错误: {e}")
        return False


def is_gateway(ip_with_prefix: str, network_str: Optional[str] = None) -> bool:
    """判断IP是否为网关地址

    网关通常是网络中的第一个可用IP地址。

    Args:
        ip_with_prefix: IP地址（可以带掩码）
        network_str: 网段（CIDR格式，可选）

    Returns:
        bool: 是网关返回True
    """
    try:
        if "/" in ip_with_prefix:
            ip_str = ip_with_prefix.split("/")[0]
            prefix_len = int(ip_with_prefix.split("/")[1])
        else:
            ip_str = ip_with_prefix
            prefix_len = 32  # 纯IP默认为32位掩码

        ip = ipaddress.ip_address(ip_str)

        if network_str:
            target_network = ipaddress.ip_network(network_str, strict=False)
            if ip not in target_network:
                return False
            prefix_len = target_network.prefixlen

        if prefix_len == 32:
            return False

        if prefix_len <= 29:
            network_address = ipaddress.ip_network(
                f"{ip}/{prefix_len}", strict=False
            ).network_address
            gateway_ip = ipaddress.ip_address(int(network_address) + 1)
            return ip == gateway_ip

        elif prefix_len == 30:
            network_address = ipaddress.ip_network(
                f"{ip}/{prefix_len}", strict=False
            ).network_address
            gateway_ip = ipaddress.ip_address(int(network_address) + 1)
            return ip == gateway_ip

        elif prefix_len == 31:
            return False

    except (ValueError, IndexError) as e:
        logger.error(f"IP或网络格式错误: {e}")
        return False

    return False


def cidr_to_subnet(cidr: str) -> Tuple[str, str]:
    """将CIDR格式转换为网络地址和子网掩码

    Args:
        cidr: CIDR格式的网段（如 192.168.1.0/24）

    Returns:
        Tuple[str, str]: (网络地址, 子网掩码)
    """
    network = ipaddress.IPv4Network(cidr, strict=False)
    return str(network.network_address), str(network.netmask)


def clean_netmiko_output(output: str) -> str:
    """清理Netmiko命令输出

    移除命令输出中的提示符、分页符等干扰内容。

    Args:
        output: 原始命令输出

    Returns:
        str: 清理后的输出
    """
    if not output:
        return output

    cleaned_output = re.sub(r"^(\[.*?\]\s*|<\w+>\s*)", "", output, flags=re.MULTILINE)

    cleaned_output = re.sub(r"^\s*return\s*$", "", cleaned_output, flags=re.MULTILINE)

    cleaned_output = cleaned_output.replace("--- more ---", "")

    cleaned_output = re.sub(r"^\s*#\s*$", "", cleaned_output, flags=re.MULTILINE)

    cleaned_output = re.sub(r"\n\s*\n", "\n", cleaned_output)

    cleaned_output = cleaned_output.strip()

    return cleaned_output


def get_network_info(network_str: str) -> Dict[str, Any]:
    """获取网络详细信息

    Args:
        network_str: 网段（CIDR格式）

    Returns:
        Dict: 包含网络详细信息的字典
    """
    try:
        if "0.0.0.0/0" in network_str:
            return {
                "network": network_str,
                "version": "IPv4",
                "total_ips": None,
                "usable_ips": None,
                "subnet_mask": None,
                "gateway": None,
                "start_ip": None,
                "end_ip": None,
                "network_address": None,
                "broadcast_address": None,
            }

        network = ipaddress.ip_network(network_str, strict=False)

        hosts = list(network.hosts())

        network_info = {
            "network": str(network),
            "version": f"IPv{network.version}",
            "total_ips": network.num_addresses,
            "usable_ips": len(hosts),
            "subnet_mask": str(network.netmask),
            "gateway": str(hosts[0]) if hosts else "N/A",
            "start_ip": str(hosts[0]) if hosts else "N/A",
            "end_ip": str(hosts[-1]) if hosts else "N/A",
            "network_address": str(network.network_address),
            "broadcast_address": str(network.broadcast_address),
        }

        return network_info

    except ValueError as e:
        logger.error(f"无效的网段格式: {e}")
        return {"error": f"无效的网段格式: {e}"}
