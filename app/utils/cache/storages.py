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

REDIS_POOL_TIMEOUT = 5  # Redis 连接/读写超时时间（秒）


def _json_default(o: Any) -> Any:
    """JSON 序列化兜底：显式处理常见非原生类型，未知类型直接报错。

    替代 ``default=str`` 的静默字符串化——后者会把 datetime/Decimal/UUID 等
    转成字符串、丢失类型信息（datetime 还会变成不可解析的 "2026-07-27 14:10:43"）。
    这里将可识别类型转为 JSON 原生表达，无法识别的类型抛 TypeError，
    由调用方 ``except`` 转译为 ValueError 暴露出来，避免静默数据损坏。
    """
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, timedelta):
        return o.total_seconds()
    if isinstance(o, Decimal):
        return str(o)  # 保留精度，读取方按需解析
    if isinstance(o, UUID):
        return str(o)
    if isinstance(o, (bytes, bytearray)):
        return o.decode("utf-8", errors="replace")
    if isinstance(o, set):
        return list(o)
    raise TypeError(f"缓存序列化不支持的类型: {type(o).__name__}")


class RedisCacheStorage(CacheStorage):
    """Redis缓存存储实现"""
    
    def __init__(self, config=None, key_prefix: str = ""):
        """初始化Redis缓存存储
        
        Args:
            config: 配置对象
            key_prefix: 键前缀
        """
        self.config = config or get_config()
        self.key_prefix = key_prefix
        self.redis_client = self._init_redis()
        
    def _init_redis(self):
        """初始化Redis客户端

        关键配置说明：
        - retry_on_timeout: 超时后自动重试，防止 Broken pipe
        - health_check_interval: 定期检测连接有效性，自动剔除失效连接
        - socket_keepalive: 启用 TCP keepalive，防止空闲连接被中间设备断开
        """
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
        """生成带前缀的缓存键

        前缀与键之间使用 ':' 分隔，防止命名空间泄漏。
        如果实例未配置前缀，使用环境变量 CACHE_KEY_PREFIX（默认 ipip:）。
        前缀中的尾随冒号会被归一化，避免产生 'ipip::user:1' 这类双冒号键。
        """
        prefix = self.key_prefix or os.getenv('CACHE_KEY_PREFIX', 'ipip:')
        if prefix:
            prefix = prefix.rstrip(':')
            if prefix:
                return f"{prefix}:{key}"
        return key
    
    def _serialize_value(self, value: Any) -> str:
        """序列化值（仅 JSON，禁用 pickle 以防 RCE）

        使用 ``_json_default`` 显式处理 datetime/Decimal/UUID 等常见非原生类型，
        未知类型直接抛 TypeError（被 except 转为 ValueError 暴露），不再用
        ``default=str`` 静默字符串化而丢失类型信息。
        """
        try:
            return json.dumps(value, ensure_ascii=False, default=_json_default)
        except (TypeError, ValueError) as e:
            logger.warning("缓存值无法 JSON 序列化，丢弃: %s", e)
            raise ValueError(f"缓存值不支持序列化: {type(value)}")
    
    def _deserialize_value(self, value: str) -> Any:
        """反序列化值（仅 JSON，禁用 pickle 以防 RCE）"""
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("缓存值反序列化失败，丢弃: %s", e)
            return None
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值"""
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
        """设置缓存值"""
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
        """删除缓存"""
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
        """检查缓存是否存在"""
        if not self.redis_client:
            return False

        try:
            full_key = self._make_key(key)
            return self.redis_client.exists(full_key) > 0
        except Exception as e:
            logger.error(f"检查缓存存在性失败 (key={key}): {e}", exc_info=True)
            return False
    
    def get_ttl(self, key: str) -> int:
        """获取缓存剩余过期时间"""
        if not self.redis_client:
            return -2

        try:
            full_key = self._make_key(key)
            return self.redis_client.ttl(full_key)
        except Exception as e:
            logger.error(f"获取缓存TTL失败 (key={key}): {e}", exc_info=True)
            return -2
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """增加计数器"""
        if not self.redis_client:
            return None

        try:
            full_key = self._make_key(key)
            return self.redis_client.incrby(full_key, amount)
        except Exception as e:
            logger.error(f"增加计数器失败 (key={key}): {e}", exc_info=True)
            return None
    
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """批量获取缓存"""
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
        """批量设置缓存"""
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
        """根据模式删除缓存

        使用 SCAN 替代 KEYS，避免阻塞 Redis 事件循环。
        """
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
        """清空所有缓存"""
        return self.delete_pattern("*") > 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
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
        """计算缓存命中率"""
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)


class MemoryCacheStorage(CacheStorage):
    """内存缓存存储实现"""
    
    MAX_ENTRIES = 10000  # 默认最大条目数，防止内存泄漏

    def __init__(self, max_entries: int = MAX_ENTRIES):
        """初始化内存缓存存储

        Args:
            max_entries: 最大缓存条目数，超过后自动淘汰过期和最久未访问的条目
        """
        self._cache = {}
        self._ttl_data = {}
        self._lock = threading.RLock()
        self._max_entries = max_entries
    
    def _is_expired(self, key: str) -> bool:
        """检查键是否过期"""
        if key not in self._ttl_data:
            return False
        
        expire_time = self._ttl_data[key]
        if expire_time is None:
            return False
            
        return time.time() > expire_time
    
    def _cleanup_expired(self, key: str) -> None:
        """清理过期的键"""
        if self._is_expired(key):
            self._cache.pop(key, None)
            self._ttl_data.pop(key, None)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值"""
        with self._lock:
            self._cleanup_expired(key)
            return self._cache.get(key, default)

    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存值"""
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
        """删除缓存"""
        with self._lock:
            existed = key in self._cache
            self._cache.pop(key, None)
            self._ttl_data.pop(key, None)
            return existed

    def _evict_expired(self) -> None:
        """清理所有过期条目"""
        now = time.time()
        expired_keys = [
            k for k, ttl in self._ttl_data.items()
            if ttl is not None and now > ttl
        ]
        for k in expired_keys:
            self._cache.pop(k, None)
            self._ttl_data.pop(k, None)

    def _evict_oldest(self) -> None:
        """淘汰最旧的条目（TTL 最小或最早的）"""
        if not self._ttl_data:
            return
        oldest_key = min(self._ttl_data, key=lambda k: self._ttl_data[k] or float('inf'))
        self._cache.pop(oldest_key, None)
        self._ttl_data.pop(oldest_key, None)
    
    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        self._cleanup_expired(key)
        return key in self._cache
    
    def get_ttl(self, key: str) -> int:
        """获取缓存剩余过期时间"""
        if key not in self._cache:
            return -2
        
        if key not in self._ttl_data or self._ttl_data[key] is None:
            return -1
        
        remaining = self._ttl_data[key] - time.time()
        return max(0, int(remaining))
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """增加计数器"""
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
        """批量获取缓存"""
        result = {}
        for key in keys:
            self._cleanup_expired(key)
            if key in self._cache:
                result[key] = self._cache[key]
        return result
    
    def set_many(self, mapping: Dict[str, Any], ttl: int = None) -> bool:
        """批量设置缓存"""
        try:
            for key, value in mapping.items():
                self.set(key, value, ttl)
            return True
        except Exception as e:
            logger.error(f"批量设置内存缓存失败: {e}", exc_info=True)
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """根据模式删除缓存"""
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
        """清空所有缓存"""
        try:
            self._cache.clear()
            self._ttl_data.clear()
            return True
        except Exception as e:
            logger.error(f"清空内存缓存失败: {e}", exc_info=True)
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
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