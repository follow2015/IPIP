# -*- coding: utf-8 -*-
"""
统一缓存管理模块

提供统一的缓存管理接口和实现。
"""
from app.utils.cache.manager import UnifiedCacheManager, cache_manager
from app.utils.cache.storages import RedisCacheStorage, MemoryCacheStorage
from app.utils.cache.key_generator import StandardCacheKeyGenerator
from app.utils.cache.strategies import TTLCacheStrategy, LRUCacheStrategy, AdaptiveCacheStrategy

def cached(key_pattern: str = None, ttl: int = None):
    """缓存装饰器（向后兼容）
    
    自动缓存函数返回值。
    
    Args:
        key_pattern: 缓存键模式，可以使用{arg_name}引用参数
        ttl: 过期时间（秒）
    
    Example:
        @cached(key_pattern='room:{room_id}', ttl=3600)
        def get_room(room_id):
            return Room.query.get(room_id)
    """
    return cache_manager.remember(key_pattern or "cached_func", ttl)

__all__ = [
    'cache_manager',
    'cached',
    'UnifiedCacheManager',
    'RedisCacheStorage',
    'MemoryCacheStorage', 
    'StandardCacheKeyGenerator',
    'TTLCacheStrategy',
    'LRUCacheStrategy',
    'AdaptiveCacheStrategy'
]