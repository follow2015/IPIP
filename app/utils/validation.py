# -*- coding: utf-8 -*-
"""
输入验证模块

提供输入验证、数据清理和安全防护功能。
"""
import html
import re
from typing import Any, Dict, List, Optional

from marshmallow import Schema
from marshmallow import ValidationError as MarshmallowValidationError

from app.exceptions.validation import ValidationError, RequiredFieldError, ValueRangeError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ValidationManager:

    PATTERNS = {
        "email": re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"),
        "phone": re.compile(r"^1[3-9]\d{9}$"),
        "ipv4": re.compile(
            r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
        ),
        "ipv6": re.compile(
            r"^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$"
        ),
        "mac": re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"),
        "url": re.compile(r"^https?://[^\s/$.?#].[^\s]*$"),
        "username": re.compile(r"^[a-zA-Z0-9_-]{3,20}$"),
    }

    @classmethod
    def validate_schema(
        cls, data: Dict[str, Any], schema: Schema, partial: bool = False
    ) -> Dict[str, Any]:
        try:
            if partial:
                result = schema.load(data, partial=True)
            else:
                result = schema.load(data)
            return result
        except MarshmallowValidationError as e:
            logger.warning(f"Schema验证失败: {e.messages}")
            raise ValidationError(message="数据验证失败", errors=e.messages)

    @classmethod
    def sanitize_input(cls, value: str, allow_html: bool = False) -> str:
        if not isinstance(value, str):
            return value

        value = value.strip()

        if not allow_html:
            value = html.escape(value)

        value = "".join(char for char in value if ord(char) >= 32 or char in "\n\r\t")

        return value

    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any], allow_html: bool = False) -> Dict[str, Any]:
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = cls.sanitize_input(value, allow_html)
            elif isinstance(value, dict):
                result[key] = cls.sanitize_dict(value, allow_html)
            elif isinstance(value, list):
                result[key] = [
                    cls.sanitize_input(item, allow_html) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    @classmethod
    def validate_email(cls, email: str) -> bool:
        if not email:
            return False
        return bool(cls.PATTERNS["email"].match(email))

    @classmethod
    def validate_phone(cls, phone: str) -> bool:
        if not phone:
            return False
        return bool(cls.PATTERNS["phone"].match(phone))

    @classmethod
    def validate_ipv4(cls, ip: str) -> bool:
        if not ip:
            return False
        return bool(cls.PATTERNS["ipv4"].match(ip))

    @classmethod
    def validate_ipv6(cls, ip: str) -> bool:
        if not ip:
            return False
        return bool(cls.PATTERNS["ipv6"].match(ip))

    @classmethod
    def validate_ip(cls, ip: str) -> bool:
        return cls.validate_ipv4(ip) or cls.validate_ipv6(ip)

    @classmethod
    def validate_mac(cls, mac: str) -> bool:
        if not mac:
            return False
        return bool(cls.PATTERNS["mac"].match(mac))

    @classmethod
    def validate_url(cls, url: str) -> bool:
        if not url:
            return False
        return bool(cls.PATTERNS["url"].match(url))

    @classmethod
    def validate_username(cls, username: str) -> bool:
        if not username:
            return False
        return bool(cls.PATTERNS["username"].match(username))

    @classmethod
    def validate_required(cls, data: Dict[str, Any], required_fields: List[str]) -> None:
        missing_fields = []
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == "":
                missing_fields.append(field)

        if missing_fields:
            raise RequiredFieldError(missing_fields=missing_fields)

    @classmethod
    def validate_length(
        cls,
        value: str,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        field_name: str = "value",
    ) -> None:
        if not isinstance(value, str):
            return

        length = len(value)

        if min_length is not None and length < min_length:
            raise ValidationError(
                message=f"{field_name}长度不能少于{min_length}个字符", field=field_name
            )

        if max_length is not None and length > max_length:
            raise ValidationError(
                message=f"{field_name}长度不能超过{max_length}个字符", field=field_name
            )

    @classmethod
    def validate_range(
        cls,
        value: int,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        field_name: str = "value",
    ) -> None:
        if not isinstance(value, (int, float)):
            return

        if min_value is not None and value < min_value:
            raise ValueRangeError(field=field_name, value=value, min_value=min_value)

        if max_value is not None and value > max_value:
            raise ValueRangeError(field=field_name, value=value, max_value=max_value)

    @classmethod
    def validate_in_choices(cls, value: Any, choices: List[Any], field_name: str = "value") -> None:
        if value not in choices:
            raise ValidationError(
                message=f"{field_name}必须是以下值之一: {', '.join(map(str, choices))}",
                field=field_name,
            )

    @classmethod
    def validate_port(cls, port: int) -> bool:
        return isinstance(port, int) and 0 < port < 65536

    @classmethod
    def validate_ip_range(cls, start_ip: str, end_ip: str) -> bool:
        if not cls.validate_ipv4(start_ip) or not cls.validate_ipv4(end_ip):
            return False

        start_parts = [int(x) for x in start_ip.split(".")]
        end_parts = [int(x) for x in end_ip.split(".")]

        start_int = (
            (start_parts[0] << 24) + (start_parts[1] << 16) + (start_parts[2] << 8) + start_parts[3]
        )
        end_int = (end_parts[0] << 24) + (end_parts[1] << 16) + (end_parts[2] << 8) + end_parts[3]

        return start_int <= end_int


validation_manager = ValidationManager()
