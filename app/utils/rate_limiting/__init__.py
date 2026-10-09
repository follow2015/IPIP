# -*- coding: utf-8 -*-
"""
统一频率限制器模块

提供统一的频率限制功能，支持多种存储后端和限制策略。
"""
from .limiter import UnifiedRateLimiter
from .storages import (
    FailoverRateLimitStorage,
    MemoryRateLimitStorage,
    RateLimitStorageUnavailable,
    RedisRateLimitStorage,
)
from .strategies import SlidingWindowStrategy, FixedWindowStrategy

unified_rate_limiter = UnifiedRateLimiter()

__all__ = [
    "UnifiedRateLimiter",
    "MemoryRateLimitStorage", 
    "RedisRateLimitStorage",
    "FailoverRateLimitStorage",
    "RateLimitStorageUnavailable",
    "SlidingWindowStrategy",
    "FixedWindowStrategy",
    "unified_rate_limiter",
]