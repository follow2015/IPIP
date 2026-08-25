# -*- coding: utf-8 -*-
"""
频率限制装饰器

提供统一的频率限制装饰器接口。
"""
from app.utils.logging import get_logger

from config import get_config
from .limiter import UnifiedRateLimiter

logger = get_logger(__name__)
config = get_config()

unified_rate_limiter = UnifiedRateLimiter()


def rate_limit(limit_string: str = None, key_func=None):
    if limit_string is None:
        limit_string = getattr(config, 'RATELIMIT_DEFAULT', '100 per minute')

    return unified_rate_limiter.limit_decorator(limit_string, key_func)


def rate_limit_login(f):
    login_limit = getattr(config, 'RATELIMIT_LOGIN', '5 per minute')
    return unified_rate_limiter.limit_decorator(login_limit)(f)


def rate_limit_api(f):
    api_limit = getattr(config, 'RATELIMIT_API', '100 per minute')
    return unified_rate_limiter.limit_decorator(api_limit)(f)


rate_limiter = unified_rate_limiter
