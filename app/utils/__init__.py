# -*- coding: utf-8 -*-
"""
工具函数包

包含各种工具类和辅助函数。
"""
from app.utils.cache import UnifiedCacheManager, cache_manager
from app.utils.cache import cached
from app.exceptions.handlers import register_error_handlers
from app.utils.health_check import ErrorStatistics, HealthChecker, error_statistics, health_checker
from app.utils.logging.manager import UnifiedLogManager, log_execution_time, log_manager
from app.utils.network_utils import (
    calculate_network_usage,
    cidr_to_subnet,
    clean_netmiko_output,
    format_timestamp,
    generate_ip_range,
    get_network_info,
    get_status_color,
    get_status_text,
    is_gateway,
    is_ip_in_network,
    normalize_mac_address,
    parse_interface_name,
    validate_ip_address,
    validate_ip_network,
)
from app.utils.rate_limiting.decorators import (
    rate_limit,
    rate_limit_api,
    rate_limit_login,
    rate_limiter,
)
_LAZY_AUTH_NAMES = frozenset({
    "AuthenticationManager",
    "PermissionManager",
    "auth_manager",
    "permission_manager",
    "login_required",
    "permission_required",
    "role_required",
})


def _missing_attribute_hint() -> str:
    """拼 AttributeError 的补充提示（审计 A-P2-5）。

    **实测边界，勿再试图"修好它"**：`from app.utils import sse_login_required` 这种
    from-import 形态下，本提示**到不了用户** —— CPython 的 import 机制会先清掉
    AttributeError，再抛自己的 `cannot import name ... from 'app.utils'`（普通模块与
    包形态均如此，Python 3.14 实测，见 tests 内的对照用例）。只有**属性访问**形态
    （`app.utils.sse_login_required`，即 REPL / 调试器里探索时的形态）能看到本提示。

    想让 from-import 也成功，唯一办法是把符号加进 `_LAZY_AUTH_NAMES` —— 那正是上面
    注释拒绝的事。故此处只给**事实性**指引（认证类符号的规范路径是什么），不宣称
    `name` 一定属于认证面，以免对拼错的名字给出误导。
    """
    return (
        "提示：utils 门面有意只再导出部分工具符号；认证授权类符号（含 sse_* 变体、"
        "请求上下文访问器）的规范路径是 `from app.services.auth import ...`。"
    )


def __getattr__(name):
    if name == 'APIResponse':
        from app.api.base import APIResponse
        return APIResponse
    if name in _LAZY_AUTH_NAMES:
        import importlib
        return getattr(importlib.import_module('app.utils.auth'), name)
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}。{_missing_attribute_hint()}"
    )
from app.exceptions.validation import ValidationError
from app.utils.validation import ValidationManager, validation_manager

__all__ = [
    "UnifiedCacheManager",
    "cache_manager",
    "cached",
    "APIResponse",
    "AuthenticationManager",
    "PermissionManager",
    "auth_manager",
    "permission_manager",
    "login_required",
    "permission_required",
    "role_required",
    "ValidationManager",
    "ValidationError",
    "validation_manager",
    "rate_limiter",
    "rate_limit",
    "rate_limit_login",
    "rate_limit_api",
    "register_error_handlers",
    "UnifiedLogManager",
    "log_manager",
    "log_execution_time",
    "HealthChecker",
    "ErrorStatistics",
    "health_checker",
    "error_statistics",    # 网络工具函数
    "validate_ip_address",
    "validate_ip_network",
    "normalize_mac_address",
    "get_status_text",
    "get_status_color",
    "parse_interface_name",
    "calculate_network_usage",
    "format_timestamp",
    "generate_ip_range",
    "is_ip_in_network",
    "is_gateway",
    "cidr_to_subnet",
    "clean_netmiko_output",
    "get_network_info",
]
