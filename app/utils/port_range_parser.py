# -*- coding: utf-8 -*-
"""
端口范围解析器

将端口范围表达式（如 "10GE1/0/1 to 10GE1/0/10"）展开为离散端口列表，
或将离散端口列表构造为厂商对应的 interface range 表达式。
"""
import re
from app.core.enums import SwitchDeviceTypeCode
from app.utils.logging import get_logger
from typing import Optional

logger = get_logger(__name__)

_PORT_PREFIX_PATTERN = re.compile(
    r"^(10GE|XGE|GE|GigabitEthernet|XGigabitEthernet|Eth|"
    r"Ten-GigabitEthernet|HundredGigE|40GE|25GE|"
    r"FortyGigE|TwoHundredGigE|50GE|100GE)"
    r"(.+)$",
    re.IGNORECASE,
)


class PortRangeParser:
    """端口范围解析器

    支持两种输入方式：
    1. 离散端口列表：["10GE1/0/1", "10GE1/0/3", "10GE1/0/5"]
    2. 范围表达式："10GE1/0/1 to 10GE1/0/10"

    两者可同时提供，合并去重。
    """

    @staticmethod
    def parse(ports: list[str] = None, port_range: str = None) -> list[str]:
        """合并离散列表和范围表达式，去重并保持顺序

        Args:
            ports: 离散端口名称列表
            port_range: 端口范围表达式（如 "10GE1/0/1 to 10GE1/0/10"）

        Returns:
            list[str]: 合并去重后的端口名称列表

        Raises:
            ValueError: ports 和 port_range 均为空时
        """
        result = []
        seen = set()

        for p in (ports or []):
            p = p.strip()
            if p and p not in seen:
                result.append(p)
                seen.add(p)

        if port_range and port_range.strip():
            expanded = PortRangeParser.expand_range(port_range)
            for p in expanded:
                if p not in seen:
                    result.append(p)
                    seen.add(p)

        if not result:
            raise ValueError("端口列表和范围表达式均不能为空")

        return result

    @staticmethod
    def expand_range(port_range: str) -> list[str]:
        """展开端口范围表达式为离散端口列表

        支持格式：
        - "10GE1/0/1 to 10GE1/0/10" → ["10GE1/0/1", ..., "10GE1/0/10"]
        - "GigabitEthernet1/0/1 to GigabitEthernet1/0/5" → 展开为5个端口
        - 多段范围用逗号分隔："10GE1/0/1 to 10GE1/0/5, 10GE1/0/10 to 10GE1/0/12"

        Args:
            port_range: 端口范围表达式

        Returns:
            list[str]: 展开后的端口名称列表
        """
        port_range = port_range.strip()
        if not port_range:
            return []

        results = []
        segments = [s.strip() for s in port_range.split(",") if s.strip()]

        for segment in segments:
            to_match = re.match(r"^(.+?)\s+to\s+(.+)$", segment, re.IGNORECASE)
            if to_match:
                start_port = to_match.group(1).strip()
                end_port = to_match.group(2).strip()
                expanded = PortRangeParser._expand_continuous(start_port, end_port)
                if expanded:
                    results.extend(expanded)
                else:
                    logger.warning("无法展开端口范围: %s to %s", start_port, end_port)
            else:
                results.append(segment)

        return results

    @staticmethod
    def _expand_continuous(start_port: str, end_port: str) -> Optional[list[str]]:
        """展开连续端口范围

        解析起始和结束端口名，提取公共前缀和端口号，生成连续列表。
        要求两个端口具有相同的前缀和槽位/卡号，仅端口号不同。

        Args:
            start_port: 起始端口名（如 "10GE1/0/1"）
            end_port: 结束端口名（如 "10GE1/0/10"）

        Returns:
            list[str]: 展开后的端口列表，无法展开时返回 None

        Raises:
            ValueError: 展开数量超过上限时
        """
        start_info = PortRangeParser._split_port_name(start_port)
        end_info = PortRangeParser._split_port_name(end_port)

        if not start_info or not end_info:
            return None

        start_prefix, start_num = start_info
        end_prefix, end_num = end_info

        if start_prefix.lower() != end_prefix.lower():
            return None

        if start_num > end_num:
            return None

        max_expand = 512
        count = end_num - start_num + 1
        if count > max_expand:
            raise ValueError(
                f"端口范围展开数量 {count} 超过上限 {max_expand}，"
                f"请缩小范围（{start_port} to {end_port}）"
            )

        return [f"{start_prefix}{i}" for i in range(start_num, end_num + 1)]

    @staticmethod
    def _split_port_name(port_name: str) -> Optional[tuple[str, int]]:
        """将端口名拆分为前缀和端口号

        Args:
            port_name: 端口名（如 "10GE1/0/1"）

        Returns:
            (prefix, port_number): 如 ("10GE1/0/", 1)，无法拆分时返回 None
        """
        m = _PORT_PREFIX_PATTERN.match(port_name)
        if not m:
            return None

        type_prefix = m.group(1)
        remainder = m.group(2)

        last_slash = remainder.rfind("/")
        if last_slash == -1:
            return None

        prefix_part = remainder[:last_slash + 1]  # 如 "1/0/"
        num_part = remainder[last_slash + 1:]      # 如 "1"

        try:
            port_num = int(num_part)
        except ValueError:
            return None

        return (f"{type_prefix}{prefix_part}", port_num)

    @staticmethod
    def build_range_expr(ports: list[str], device_type: str) -> str:
        """将离散端口列表构造为厂商对应的 interface range 表达式

        华为/H3C: 空格分隔 — "10GE1/0/1 10GE1/0/3 10GE1/0/5"
        Cisco: 逗号+空格分隔 — "Gi1/0/1 , Gi1/0/3 , Gi1/0/5"

        Args:
            ports: 离散端口名称列表
            device_type: 设备类型（huawei/h3c/cisco）

        Returns:
            str: interface range 表达式
        """
        if not ports:
            return ""

        if device_type == SwitchDeviceTypeCode.CISCO:
            return " , ".join(ports)
        else:
            return " ".join(ports)

    @staticmethod
    def build_trunkport_expr(ports: list[str]) -> str:
        """将离散端口列表构造为华为 trunkport 命令格式

        华为 CE 的 trunkport 命令要求端口类型前缀只写一次，
        后跟槽位/端口范围，连续端口用 to 连接。

        示例：
        - ["40GE1/0/1", "40GE1/0/2", "40GE1/0/3"] → "40GE 1/0/1 to 1/0/3"
        - ["40GE1/0/1", "40GE1/0/3", "40GE1/0/5"] → "40GE 1/0/1 1/0/3 1/0/5"
        - ["10GE1/0/1", "10GE1/0/2", "40GE1/0/1"]
          → "10GE 1/0/1 to 1/0/2" + "40GE 1/0/1"（多条 trunkport 命令，换行分隔）

        Args:
            ports: 离散端口名称列表

        Returns:
            str: trunkport 命令的端口表达式（多条命令用换行分隔）
        """
        if not ports:
            return ""

        groups: dict[tuple[str, str], list[int]] = {}
        for port in ports:
            info = PortRangeParser._split_port_name(port)
            if not info:
                raise ValueError(f"无法解析端口名: {port}，build_trunkport_expr 仅支持标准物理端口格式")
            full_prefix, port_num = info
            m = _PORT_PREFIX_PATTERN.match(port)
            if m:
                type_prefix = m.group(1)
                remainder = m.group(2)
                last_slash = remainder.rfind("/")
                slot_card = remainder[:last_slash + 1] if last_slash != -1 else ""
            else:
                type_prefix = full_prefix
                slot_card = ""
            key = (type_prefix, slot_card)
            groups.setdefault(key, []).append(port_num)

        parts = []
        for (type_prefix, slot_card), port_nums in sorted(groups.items()):
            port_nums.sort()
            segments = PortRangeParser._merge_continuous_nums(port_nums)
            for seg in segments:
                if seg[0] == seg[1]:
                    parts.append(f"{type_prefix} {slot_card}{seg[0]}")
                else:
                    parts.append(f"{type_prefix} {slot_card}{seg[0]} to {slot_card}{seg[1]}")

        return "\n".join(parts)

    @staticmethod
    def _merge_continuous_nums(nums: list[int]) -> list[tuple[int, int]]:
        """将排序后的整数列表合并为连续范围段

        Args:
            nums: 已排序的整数列表，如 [1, 2, 3, 5, 6, 8]

        Returns:
            list[tuple[int, int]]: 连续范围段，如 [(1, 3), (5, 6), (8, 8)]
        """
        if not nums:
            return []
        result = []
        start = end = nums[0]
        for n in nums[1:]:
            if n == end + 1:
                end = n
            else:
                result.append((start, end))
                start = end = n
        result.append((start, end))
        return result

    @staticmethod
    def build_range_expr_from_range(port_range: str, device_type: str) -> str:
        """将用户输入的范围表达式转换为厂商格式

        用户输入统一使用 "to" 关键字。
        - 华为/H3C: 保持原样（"10GE1/0/1 to 10GE1/0/10"）
        - Cisco: 转换为 "prefix start - end" 格式
          （"GigabitEthernet1/0/1 to GigabitEthernet1/0/10" → "GigabitEthernet1/0/1 - 10"）

        Args:
            port_range: 用户输入的范围表达式（如 "10GE1/0/1 to 10GE1/0/10"）
            device_type: 设备类型

        Returns:
            str: 厂商格式的 interface range 表达式
        """
        if device_type != SwitchDeviceTypeCode.CISCO:
            return port_range

        def _convert_segment(match: re.Match) -> str:
            """将单段 "X to Y" 转为 Cisco "prefix start - end" 格式"""
            start_port = match.group(1).strip()
            end_port = match.group(2).strip()

            start_info = PortRangeParser._split_port_name(start_port)
            end_info = PortRangeParser._split_port_name(end_port)

            if (start_info and end_info
                    and start_info[0].lower() == end_info[0].lower()):
                return f"{start_port} - {end_info[1]}"
            else:
                return f"{start_port} - {end_port}"

        return re.sub(
            r"(.+?)\s+to\s+(.+)",
            _convert_segment,
            port_range,
            flags=re.IGNORECASE,
        )