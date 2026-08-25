# -*- coding: utf-8 -*-
"""
IP地址处理工具类

提供IP地址的格式化、解析和搜索功能。
"""
import json
import re
from typing import List, Optional


class IPAddressHelper:
    """IP地址处理工具类"""

    @staticmethod
    def format_ip_address(ip_address) -> str:
        """格式化IP地址，支持 JSON 列表和纯字符串

        Args:
            ip_address: IP地址（JSON字符串 / Python列表 / 单个字符串）

        Returns:
            str: 逗号分隔的 IP 地址字符串
        """
        if not ip_address:
            return ""

        if isinstance(ip_address, list):
            return ", ".join(str(ip) for ip in ip_address)

        if isinstance(ip_address, str):
            try:
                parsed = json.loads(ip_address)
                if isinstance(parsed, list):
                    return ", ".join(str(ip) for ip in parsed)
                return str(parsed)
            except (json.JSONDecodeError, ValueError):
                return ip_address

        return str(ip_address)

    @staticmethod
    def parse_ip_address(ip_string: str) -> Optional[str]:
        """将逗号分隔的 IP 字符串解析为 JSON 格式存储值

        Args:
            ip_string: "192.168.1.1" 或 "192.168.1.1, 10.0.0.1"

        Returns:
            Optional[str]: JSON 字符串；输入为空时返回 None
        """
        if not ip_string or not ip_string.strip():
            return None

        ips = [ip.strip() for ip in ip_string.split(",") if ip.strip()]
        if not ips:
            return None

        return json.dumps(ips[0]) if len(ips) == 1 else json.dumps(ips)

    @staticmethod
    def build_ip_search_filter(model_class, keyword: str):
        """构建参数化的 IP 地址搜索 SQLAlchemy filter 条件

        使用 SQLAlchemy ORM 表达式，不拼接裸 SQL，消除 SQL 注入风险。

        Args:
            model_class: 包含 ip_address 列的 ORM 模型类
            keyword: 搜索关键词

        Returns:
            SQLAlchemy BinaryExpression（可直接传入 query.filter()）

        Usage:
            from app.utils.ip_address_helper import ip_address_helper
            from app.models.device import Device

            query = query.filter(ip_address_helper.build_ip_search_filter(Device, "10.0.0"))
        """
        from sqlalchemy import or_, func, cast, String

        ip_col = model_class.ip_address

        return or_(
            cast(ip_col, String).ilike(f"%{keyword}%"),
            func.json_contains(ip_col, json.dumps(keyword)).is_(True),
        )

    @staticmethod
    def validate_ip_address(ip_address: str) -> bool:
        """验证 IP 地址格式（IPv4 / IPv6）

        Args:
            ip_address: 单个 IP 地址字符串

        Returns:
            bool: 格式合法返回 True
        """
        if not ip_address or not isinstance(ip_address, str):
            return False

        ipv4 = r"^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$"
        ipv6 = r"^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$"

        return bool(re.match(ipv4, ip_address) or re.match(ipv6, ip_address))

    @staticmethod
    def validate_ip_list(ip_string: str) -> List[str]:
        """校验逗号分隔的多个 IP 地址，返回非法 IP 列表

        Args:
            ip_string: 逗号分隔的 IP 字符串

        Returns:
            List[str]: 格式非法的 IP 列表；全部合法时为空列表
        """
        if not ip_string:
            return []

        ips = [ip.strip() for ip in ip_string.split(",") if ip.strip()]
        return [ip for ip in ips if not IPAddressHelper.validate_ip_address(ip)]

    @staticmethod
    def extract_ips_from_json(json_string: str) -> List[str]:
        """从 JSON 字符串中提取 IP 地址列表

        Args:
            json_string: JSON 格式的 IP 地址字符串（数组或单个字符串）

        Returns:
            List[str]: IP 地址列表；解析失败时尝试作为普通字符串处理
        """
        if not json_string:
            return []

        try:
            parsed = json.loads(json_string)
            if isinstance(parsed, list):
                return [str(ip) for ip in parsed]
            if isinstance(parsed, str):
                return [parsed]
            return []
        except (json.JSONDecodeError, ValueError):
            return [json_string] if json_string.strip() else []


ip_address_helper = IPAddressHelper()
