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

    @staticmethod
    def parse(ports: list[str] = None, port_range: str = None) -> list[str]:
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
        m = _PORT_PREFIX_PATTERN.match(port_name)
        if not m:
            return None

        type_prefix = m.group(1)
        remainder = m.group(2)

        last_slash = remainder.rfind("/")
        if last_slash == -1:
            return None

        prefix_part = remainder[:last_slash + 1]
        num_part = remainder[last_slash + 1:]

        try:
            port_num = int(num_part)
        except ValueError:
            return None

        return (f"{type_prefix}{prefix_part}", port_num)

    @staticmethod
    def build_range_expr(ports: list[str], device_type: str) -> str:
        if not ports:
            return ""

        if device_type == SwitchDeviceTypeCode.CISCO:
            return " , ".join(ports)
        else:
            return " ".join(ports)

    @staticmethod
    def build_trunkport_expr(ports: list[str]) -> str:
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
        if device_type != SwitchDeviceTypeCode.CISCO:
            return port_range

        def _convert_segment(match: re.Match) -> str:
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
