# -*- coding: utf-8 -*-
"""
IP地址处理工具类

提供IP地址的格式化、解析和搜索功能。
"""
import json
import re
from typing import List, Optional


class IPAddressHelper:

    @staticmethod
    def format_ip_address(ip_address) -> str:
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
        if not ip_string or not ip_string.strip():
            return None

        ips = [ip.strip() for ip in ip_string.split(",") if ip.strip()]
        if not ips:
            return None

        return json.dumps(ips[0]) if len(ips) == 1 else json.dumps(ips)

    @staticmethod
    def build_ip_search_filter(model_class, keyword: str):
        from sqlalchemy import or_, func, cast, String

        ip_col = model_class.ip_address

        return or_(
            cast(ip_col, String).ilike(f"%{keyword}%"),
            func.json_contains(ip_col, json.dumps(keyword)).is_(True),
        )

    @staticmethod
    def validate_ip_address(ip_address: str) -> bool:
        if not ip_address or not isinstance(ip_address, str):
            return False

        ipv4 = r"^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$"
        ipv6 = r"^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$"

        return bool(re.match(ipv4, ip_address) or re.match(ipv6, ip_address))

    @staticmethod
    def validate_ip_list(ip_string: str) -> List[str]:
        if not ip_string:
            return []

        ips = [ip.strip() for ip in ip_string.split(",") if ip.strip()]
        return [ip for ip in ips if not IPAddressHelper.validate_ip_address(ip)]

    @staticmethod
    def extract_ips_from_json(json_string: str) -> List[str]:
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
