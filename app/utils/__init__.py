# -*- coding: utf-8 -*-
"""
工具函数包

包含各种工具类和辅助函数。
"""
from app.utils.auth import (
    AuthenticationManager,
    PermissionManager,
    auth_manager,
    login_required,
    permission_manager,
    permission_required,
    role_required,
)
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
def __getattr__(name):
    if name == 'APIResponse':
        from app.api.base import APIResponse
        return APIResponse
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
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
