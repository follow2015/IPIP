# -*- coding: utf-8 -*-
"""
接口定义模块

定义系统中各个组件的接口契约，确保组件间的解耦和可测试性。
"""

from .cache import CacheStorage, CacheManager, CacheKeyGenerator
from .rate_limiting import RateLimitStorage, RateLimiter
from .logging import Logger, LogFormatter

__all__ = [
    "CacheStorage",
    "CacheManager",
    "CacheKeyGenerator",
    
    "RateLimitStorage",
    "RateLimiter",
    
    "Logger",
    "LogFormatter",
]
