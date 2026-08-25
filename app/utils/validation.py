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
    """验证管理器

    提供输入验证、数据清理和常用验证方法。
    """

    PATTERNS = {
        "email": re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"),
        "phone": re.compile(r"^1[3-9]\d{9}$"),  # 中国手机号
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
        """使用Marshmallow schema验证数据

        Args:
            data: 待验证的数据
            schema: Marshmallow schema实例
            partial: 是否允许部分验证（用于更新操作）

        Returns:
            Dict: 验证后的数据

        Raises:
            ValidationError: 验证失败时抛出
        """
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
        """清理输入数据

        Args:
            value: 输入值
            allow_html: 是否允许HTML标签

        Returns:
            str: 清理后的值
        """
        if not isinstance(value, str):
            return value

        value = value.strip()

        if not allow_html:
            value = html.escape(value)

        value = "".join(char for char in value if ord(char) >= 32 or char in "\n\r\t")

        return value

    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any], allow_html: bool = False) -> Dict[str, Any]:
        """清理字典中的所有字符串值

        Args:
            data: 输入字典
            allow_html: 是否允许HTML标签

        Returns:
            Dict: 清理后的字典
        """
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
        """验证邮箱格式

        Args:
            email: 邮箱地址

        Returns:
            bool: 格式正确返回True
        """
        if not email:
            return False
        return bool(cls.PATTERNS["email"].match(email))

    @classmethod
    def validate_phone(cls, phone: str) -> bool:
        """验证手机号格式（中国）

        Args:
            phone: 手机号

        Returns:
            bool: 格式正确返回True
        """
        if not phone:
            return False
        return bool(cls.PATTERNS["phone"].match(phone))

    @classmethod
    def validate_ipv4(cls, ip: str) -> bool:
        """验证IPv4地址格式

        Args:
            ip: IP地址

        Returns:
            bool: 格式正确返回True
        """
        if not ip:
            return False
        return bool(cls.PATTERNS["ipv4"].match(ip))

    @classmethod
    def validate_ipv6(cls, ip: str) -> bool:
        """验证IPv6地址格式

        Args:
            ip: IP地址

        Returns:
            bool: 格式正确返回True
        """
        if not ip:
            return False
        return bool(cls.PATTERNS["ipv6"].match(ip))

    @classmethod
    def validate_ip(cls, ip: str) -> bool:
        """验证IP地址格式（IPv4或IPv6）

        Args:
            ip: IP地址

        Returns:
            bool: 格式正确返回True
        """
        return cls.validate_ipv4(ip) or cls.validate_ipv6(ip)

    @classmethod
    def validate_mac(cls, mac: str) -> bool:
        """验证MAC地址格式

        Args:
            mac: MAC地址

        Returns:
            bool: 格式正确返回True
        """
        if not mac:
            return False
        return bool(cls.PATTERNS["mac"].match(mac))

    @classmethod
    def validate_url(cls, url: str) -> bool:
        """验证URL格式

        Args:
            url: URL地址

        Returns:
            bool: 格式正确返回True
        """
        if not url:
            return False
        return bool(cls.PATTERNS["url"].match(url))

    @classmethod
    def validate_username(cls, username: str) -> bool:
        """验证用户名格式

        Args:
            username: 用户名

        Returns:
            bool: 格式正确返回True
        """
        if not username:
            return False
        return bool(cls.PATTERNS["username"].match(username))

    @classmethod
    def validate_required(cls, data: Dict[str, Any], required_fields: List[str]) -> None:
        """验证必需字段

        Args:
            data: 数据字典
            required_fields: 必需字段列表

        Raises:
            ValidationError: 缺少必需字段时抛出
        """
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
        """验证字符串长度

        Args:
            value: 字符串值
            min_length: 最小长度
            max_length: 最大长度
            field_name: 字段名

        Raises:
            ValidationError: 长度不符合要求时抛出
        """
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
        """验证数值范围

        Args:
            value: 数值
            min_value: 最小值
            max_value: 最大值
            field_name: 字段名

        Raises:
            ValidationError: 数值不在范围内时抛出
        """
        if not isinstance(value, (int, float)):
            return

        if min_value is not None and value < min_value:
            raise ValueRangeError(field=field_name, value=value, min_value=min_value)

        if max_value is not None and value > max_value:
            raise ValueRangeError(field=field_name, value=value, max_value=max_value)

    @classmethod
    def validate_in_choices(cls, value: Any, choices: List[Any], field_name: str = "value") -> None:
        """验证值是否在允许的选项中

        Args:
            value: 值
            choices: 允许的选项列表
            field_name: 字段名

        Raises:
            ValidationError: 值不在选项中时抛出
        """
        if value not in choices:
            raise ValidationError(
                message=f"{field_name}必须是以下值之一: {', '.join(map(str, choices))}",
                field=field_name,
            )

    @classmethod
    def validate_port(cls, port: int) -> bool:
        """验证端口号

        Args:
            port: 端口号

        Returns:
            bool: 端口号有效返回True
        """
        return isinstance(port, int) and 0 < port < 65536

    @classmethod
    def validate_ip_range(cls, start_ip: str, end_ip: str) -> bool:
        """验证IP地址范围

        Args:
            start_ip: 起始IP
            end_ip: 结束IP

        Returns:
            bool: 范围有效返回True
        """
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
