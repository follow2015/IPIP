# -*- coding: utf-8 -*-
"""
存储适配器模块

提供统一的存储接口，支持 Redis 和内存双模式存储。
当 Redis 不可用时，自动降级到内存存储。
"""
import json
from app.utils.logging import get_logger
import time
from typing import Any, Optional, Dict

logger = get_logger(__name__)


class StorageAdapter:
    """存储适配器
    
    支持 Redis 和内存双模式存储，提供统一的存储接口。
    当 Redis 连接失败时，自动降级到内存存储。
    """

    def __init__(self, redis_client=None):
        """初始化存储适配器
        
        Args:
            redis_client: Redis 客户端实例，如果为 None 则使用内存存储
        """
        self.redis_client = redis_client
        self.memory_store: Dict[str, Dict[str, Any]] = {}
        self.use_redis = redis_client is not None
        
        if self.use_redis:
            try:
                self.redis_client.ping()
                logger.info("存储适配器: 使用 Redis 存储")
            except Exception as e:
                logger.warning(f"存储适配器: Redis 连接失败，降级到内存存储: {str(e)}")
                self.use_redis = False
        else:
            logger.info("存储适配器: 使用内存存储")

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置键值对
        
        Args:
            key: 键名
            value: 值（支持任意可序列化的类型）
            ttl: 过期时间（秒），None 表示永不过期
            
        Returns:
            bool: 操作是否成功
        """
        try:
            if self.use_redis:
                try:
                    serialized_value = json.dumps(value)
                    if ttl:
                        self.redis_client.setex(key, ttl, serialized_value)
                    else:
                        self.redis_client.set(key, serialized_value)
                    return True
                except Exception as e:
                    logger.warning(f"Redis set 失败，降级到内存存储: {str(e)}")
                    self.use_redis = False
            
            expire_at = None
            if ttl:
                expire_at = time.time() + ttl
            
            self.memory_store[key] = {
                'value': value,
                'expire_at': expire_at
            }
            return True
            
        except Exception as e:
            logger.error(f"存储适配器 set 失败: key={key}, error={str(e)}")
            return False

    def get(self, key: str) -> Optional[Any]:
        """获取值
        
        Args:
            key: 键名
            
        Returns:
            Any: 存储的值，如果不存在或已过期则返回 None
        """
        try:
            if self.use_redis:
                try:
                    value = self.redis_client.get(key)
                    if value is None:
                        return None
                    return json.loads(value)
                except Exception as e:
                    logger.warning(f"Redis get 失败，降级到内存存储: {str(e)}")
                    self.use_redis = False
            
            if key not in self.memory_store:
                return None
            
            item = self.memory_store[key]
            
            if item['expire_at'] is not None and time.time() > item['expire_at']:
                del self.memory_store[key]
                return None
            
            return item['value']
            
        except Exception as e:
            logger.error(f"存储适配器 get 失败: key={key}, error={str(e)}")
            return None

    def delete(self, key: str) -> bool:
        """删除键
        
        Args:
            key: 键名
            
        Returns:
            bool: 操作是否成功
        """
        try:
            if self.use_redis:
                try:
                    self.redis_client.delete(key)
                    return True
                except Exception as e:
                    logger.warning(f"Redis delete 失败，降级到内存存储: {str(e)}")
                    self.use_redis = False
            
            if key in self.memory_store:
                del self.memory_store[key]
            return True
            
        except Exception as e:
            logger.error(f"存储适配器 delete 失败: key={key}, error={str(e)}")
            return False

    def exists(self, key: str) -> bool:
        """检查键是否存在
        
        Args:
            key: 键名
            
        Returns:
            bool: 键是否存在且未过期
        """
        try:
            if self.use_redis:
                try:
                    return self.redis_client.exists(key) > 0
                except Exception as e:
                    logger.warning(f"Redis exists 失败，降级到内存存储: {str(e)}")
                    self.use_redis = False
            
            if key not in self.memory_store:
                return False
            
            item = self.memory_store[key]
            
            if item['expire_at'] is not None and time.time() > item['expire_at']:
                del self.memory_store[key]
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"存储适配器 exists 失败: key={key}, error={str(e)}")
            return False

    def incr(self, key: str) -> int:
        """递增计数器
        
        Args:
            key: 键名
            
        Returns:
            int: 递增后的值
        """
        try:
            if self.use_redis:
                try:
                    return self.redis_client.incr(key)
                except Exception as e:
                    logger.warning(f"Redis incr 失败，降级到内存存储: {str(e)}")
                    self.use_redis = False
            
            if key not in self.memory_store:
                self.memory_store[key] = {'value': 0, 'expire_at': None}
            
            item = self.memory_store[key]
            
            if item['expire_at'] is not None and time.time() > item['expire_at']:
                item['value'] = 0
            
            if not isinstance(item['value'], int):
                item['value'] = 0
            
            item['value'] += 1
            return item['value']
            
        except Exception as e:
            logger.error(f"存储适配器 incr 失败: key={key}, error={str(e)}")
            return 0

    def expire(self, key: str, ttl: int) -> bool:
        """设置过期时间
        
        Args:
            key: 键名
            ttl: 过期时间（秒）
            
        Returns:
            bool: 操作是否成功
        """
        try:
            if self.use_redis:
                try:
                    return self.redis_client.expire(key, ttl) > 0
                except Exception as e:
                    logger.warning(f"Redis expire 失败，降级到内存存储: {str(e)}")
                    self.use_redis = False
            
            if key not in self.memory_store:
                return False
            
            self.memory_store[key]['expire_at'] = time.time() + ttl
            return True
            
        except Exception as e:
            logger.error(f"存储适配器 expire 失败: key={key}, error={str(e)}")
            return False

    def cleanup_expired(self):
        """清理过期的内存存储项
        
        这个方法仅用于内存存储模式，定期清理过期的键值对。
        Redis 会自动处理过期键。
        """
        if self.use_redis:
            return
        
        current_time = time.time()
        expired_keys = [
            key for key, item in self.memory_store.items()
            if item['expire_at'] is not None and current_time > item['expire_at']
        ]
        
        for key in expired_keys:
            del self.memory_store[key]
        
        if expired_keys:
            logger.debug(f"清理了 {len(expired_keys)} 个过期的内存存储项")
