# -*- coding: utf-8 -*-
"""
缓存存储实现

提供不同缓存后端的具体实现。
"""
import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.utils.logging import get_logger
import threading
import time

import redis
from config import get_config

from app.interfaces.cache import CacheStorage

logger = get_logger(__name__)

REDIS_POOL_TIMEOUT = 5


def _json_default(o: Any) -> Any:
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, timedelta):
        return o.total_seconds()
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, UUID):
        return str(o)
    if isinstance(o, (bytes, bytearray)):
        return o.decode("utf-8", errors="replace")
    if isinstance(o, set):
        return list(o)
    raise TypeError(f"缓存序列化不支持的类型: {type(o).__name__}")


class RedisCacheStorage(CacheStorage):
    
    def __init__(self, config=None, key_prefix: str = ""):
        self.config = config or get_config()
        self.key_prefix = key_prefix
        self.redis_client = self._init_redis()
        
    def _init_redis(self):
        try:
            config_instance = self.config() if isinstance(self.config, type) else self.config
            redis_password = (
                config_instance.REDIS_PASSWORD if config_instance.REDIS_PASSWORD else None
            )

            redis_client = redis.Redis(
                host=config_instance.REDIS_HOST,
                port=config_instance.REDIS_PORT,
                db=config_instance.REDIS_DB,
                password=redis_password,
                decode_responses=True,
                socket_connect_timeout=REDIS_POOL_TIMEOUT,
                socket_timeout=REDIS_POOL_TIMEOUT,
                retry_on_timeout=True,
                health_check_interval=30,
                socket_keepalive=True,
            )

            redis_client.ping()
            logger.info("Redis客户端初始化成功")
            return redis_client
        except Exception as e:
            logger.warning(f"Redis客户端初始化失败: {e}")
            return None
    
    def _make_key(self, key: str) -> str:
        prefix = self.key_prefix or os.getenv('CACHE_KEY_PREFIX', 'ipip:')
        if prefix:
            prefix = prefix.rstrip(':')
            if prefix:
                return f"{prefix}:{key}"
        return key
    
    def _serialize_value(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, default=_json_default)
        except (TypeError, ValueError) as e:
            logger.warning("缓存值无法 JSON 序列化，丢弃: %s", e)
            raise ValueError(f"缓存值不支持序列化: {type(value)}")
    
    def _deserialize_value(self, value: str) -> Any:
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("缓存值反序列化失败，丢弃: %s", e)
            return None
    
    def get(self, key: str, default: Any = None) -> Any:
        if not self.redis_client:
            logger.warning("Redis客户端未初始化，无法获取缓存")
            return default

        try:
            full_key = self._make_key(key)
            value = self.redis_client.get(full_key)

            if value is None:
                return default

            return self._deserialize_value(value)
        except Exception as e:
            logger.error(f"获取缓存失败 (key={key}): {e}", exc_info=True)
            return default
    
    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        if not self.redis_client:
            logger.warning("Redis客户端未初始化，无法设置缓存")
            return False

        try:
            full_key = self._make_key(key)
            serialized_value = self._serialize_value(value)

            if ttl is not None:
                self.redis_client.setex(full_key, ttl, serialized_value)
            else:
                self.redis_client.set(full_key, serialized_value)
                
            logger.debug(f"设置缓存成功 (key={key}, ttl={ttl})")
            return True
        except Exception as e:
            logger.error(f"设置缓存失败 (key={key}): {e}", exc_info=True)
            return False
    
    def delete(self, key: str) -> bool:
        if not self.redis_client:
            logger.warning("Redis客户端未初始化，无法删除缓存")
            return False

        try:
            full_key = self._make_key(key)
            result = self.redis_client.delete(full_key)
            logger.debug(f"删除缓存 (key={key}, result={result})")
            return result > 0
        except Exception as e:
            logger.error(f"删除缓存失败 (key={key}): {e}", exc_info=True)
            return False
    
    def exists(self, key: str) -> bool:
        if not self.redis_client:
            return False

        try:
            full_key = self._make_key(key)
            return self.redis_client.exists(full_key) > 0
        except Exception as e:
            logger.error(f"检查缓存存在性失败 (key={key}): {e}", exc_info=True)
            return False
    
    def get_ttl(self, key: str) -> int:
        if not self.redis_client:
            return -2

        try:
            full_key = self._make_key(key)
            return self.redis_client.ttl(full_key)
        except Exception as e:
            logger.error(f"获取缓存TTL失败 (key={key}): {e}", exc_info=True)
            return -2
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        if not self.redis_client:
            return None

        try:
            full_key = self._make_key(key)
            return self.redis_client.incrby(full_key, amount)
        except Exception as e:
            logger.error(f"增加计数器失败 (key={key}): {e}", exc_info=True)
            return None
    
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        if not self.redis_client:
            return {}

        try:
            full_keys = [self._make_key(key) for key in keys]
            values = self.redis_client.mget(full_keys)

            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = self._deserialize_value(value)

            return result
        except Exception as e:
            logger.error(f"批量获取缓存失败: {e}", exc_info=True)
            return {}
    
    def set_many(self, mapping: Dict[str, Any], ttl: int = None) -> bool:
        if not self.redis_client:
            return False

        try:
            pipeline = self.redis_client.pipeline()
            for key, value in mapping.items():
                full_key = self._make_key(key)
                serialized_value = self._serialize_value(value)

                if ttl is not None:
                    pipeline.setex(full_key, ttl, serialized_value)
                else:
                    pipeline.set(full_key, serialized_value)

            pipeline.execute()
            logger.debug(f"批量设置缓存成功 (count={len(mapping)})")
            return True
        except Exception as e:
            logger.error(f"批量设置缓存失败: {e}", exc_info=True)
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        if not self.redis_client:
            logger.warning("Redis客户端未初始化，无法删除缓存")
            return 0

        try:
            full_pattern = self._make_key(pattern)
            keys = []
            cursor = 0
            while True:
                cursor, batch = self.redis_client.scan(cursor, match=full_pattern, count=100)
                keys.extend(batch)
                if cursor == 0:
                    break

            if not keys:
                return 0

            count = self.redis_client.delete(*keys)
            logger.info(f"批量删除缓存 (pattern={pattern}, count={count})")
            return count
        except Exception as e:
            logger.error(f"批量删除缓存失败 (pattern={pattern}): {e}", exc_info=True)
            return 0
    
    def clear_all(self) -> bool:
        return self.delete_pattern("*") > 0
    
    def get_stats(self) -> Dict[str, Any]:
        if not self.redis_client:
            return {"status": "disconnected"}

        try:
            info = self.redis_client.info()
            return {
                "status": "connected",
                "used_memory": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                )
            }
        except Exception as e:
            logger.error(f"获取缓存统计信息失败: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)


class MemoryCacheStorage(CacheStorage):
    
    MAX_ENTRIES = 10000

    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._cache = {}
        self._ttl_data = {}
        self._lock = threading.RLock()
        self._max_entries = max_entries
    
    def _is_expired(self, key: str) -> bool:
        if key not in self._ttl_data:
            return False
        
        expire_time = self._ttl_data[key]
        if expire_time is None:
            return False
            
        return time.time() > expire_time
    
    def _cleanup_expired(self, key: str) -> None:
        if self._is_expired(key):
            self._cache.pop(key, None)
            self._ttl_data.pop(key, None)
    
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            self._cleanup_expired(key)
            return self._cache.get(key, default)

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        try:
            with self._lock:
                if len(self._cache) >= self._max_entries:
                    self._evict_expired()
                    if len(self._cache) >= self._max_entries:
                        self._evict_oldest()

                self._cache[key] = value
                if ttl is not None:
                    self._ttl_data[key] = time.time() + ttl
                else:
                    self._ttl_data[key] = None
            return True
        except Exception as e:
            logger.error(f"设置内存缓存失败 (key={key}): {e}", exc_info=True)
            return False
    
    def delete(self, key: str) -> bool:
        with self._lock:
            existed = key in self._cache
            self._cache.pop(key, None)
            self._ttl_data.pop(key, None)
            return existed

    def _evict_expired(self) -> None:
        now = time.time()
        expired_keys = [
            k for k, ttl in self._ttl_data.items()
            if ttl is not None and now > ttl
        ]
        for k in expired_keys:
            self._cache.pop(k, None)
            self._ttl_data.pop(k, None)

    def _evict_oldest(self) -> None:
        if not self._ttl_data:
            return
        oldest_key = min(self._ttl_data, key=lambda k: self._ttl_data[k] or float('inf'))
        self._cache.pop(oldest_key, None)
        self._ttl_data.pop(oldest_key, None)
    
    def exists(self, key: str) -> bool:
        self._cleanup_expired(key)
        return key in self._cache
    
    def get_ttl(self, key: str) -> int:
        if key not in self._cache:
            return -2
        
        if key not in self._ttl_data or self._ttl_data[key] is None:
            return -1
        
        remaining = self._ttl_data[key] - time.time()
        return max(0, int(remaining))
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        try:
            self._cleanup_expired(key)
            current = self._cache.get(key, 0)
            if not isinstance(current, (int, float)):
                current = 0
            new_value = current + amount
            self._cache[key] = new_value
            return new_value
        except Exception as e:
            logger.error(f"增加内存缓存计数器失败 (key={key}): {e}", exc_info=True)
            return None
    
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        result = {}
        for key in keys:
            self._cleanup_expired(key)
            if key in self._cache:
                result[key] = self._cache[key]
        return result
    
    def set_many(self, mapping: Dict[str, Any], ttl: int = None) -> bool:
        try:
            for key, value in mapping.items():
                self.set(key, value, ttl)
            return True
        except Exception as e:
            logger.error(f"批量设置内存缓存失败: {e}", exc_info=True)
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        import fnmatch
        
        count = 0
        keys_to_delete = []
        
        for key in list(self._cache.keys()):
            if fnmatch.fnmatch(key, pattern):
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            if self.delete(key):
                count += 1
        
        return count
    
    def clear_all(self) -> bool:
        try:
            self._cache.clear()
            self._ttl_data.clear()
            return True
        except Exception as e:
            logger.error(f"清空内存缓存失败: {e}", exc_info=True)
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        expired_keys = []
        for key in list(self._cache.keys()):
            if self._is_expired(key):
                expired_keys.append(key)
        
        for key in expired_keys:
            self._cleanup_expired(key)
        
        return {
            "status": "active",
            "total_keys": len(self._cache),
            "memory_usage": f"{len(str(self._cache))} bytes (estimated)"
        }
