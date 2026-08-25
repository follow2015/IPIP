# -*- coding: utf-8 -*-
"""
频率限制存储实现

提供Redis和内存两种存储后端的实现。
内存存储复用 StorageAdapter 的内存后端，避免重复实现。
"""
from app.utils.logging import get_logger
import time
from typing import Dict, Optional, Tuple

from app.interfaces.rate_limiting import RateLimitStorage
from app.utils.cache import cache_manager
from app.utils.storage import StorageAdapter

logger = get_logger(__name__)


class RedisRateLimitStorage(RateLimitStorage):
    
    def __init__(self):
        self.redis_client = cache_manager.primary_storage.redis_client
        logger.info("频率限制器: Redis存储初始化完成")
    
    def check_limit(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        try:
            current_time = int(time.time())
            window_start = current_time - window
            
            cache_key = f"ratelimit:{key}"
            
            self.redis_client.zremrangebyscore(cache_key, 0, window_start)
            
            current_count = self.redis_client.zcard(cache_key)
            
            if current_count >= limit:
                remaining = 0
                allowed = False
            else:
                request_id = f"{current_time}:{id(key)}"
                self.redis_client.zadd(cache_key, {request_id: current_time})
                
                self.redis_client.expire(cache_key, window)
                
                remaining = limit - current_count - 1
                allowed = True
            
            return allowed, remaining
            
        except Exception as e:
            logger.error(f"Redis频率限制检查失败: key={key}, error={str(e)}", exc_info=True)
            return True, limit
    
    def reset_limit(self, key: str) -> bool:
        try:
            cache_key = f"ratelimit:{key}"
            result = self.redis_client.delete(cache_key)
            logger.info(f"频率限制器: Redis重置计数 key={key}, result={result}")
            return result > 0
            
        except Exception as e:
            logger.error(f"Redis频率限制重置失败: key={key}, error={str(e)}", exc_info=True)
            return False
    
    def get_current_count(self, key: str) -> int:
        try:
            cache_key = f"ratelimit:{key}"
            return self.redis_client.zcard(cache_key)
            
        except Exception as e:
            logger.error(f"获取Redis当前计数失败: key={key}, error={str(e)}", exc_info=True)
            return 0
    
    def get_remaining_count(self, key: str, limit: int) -> int:
        current_count = self.get_current_count(key)
        return max(0, limit - current_count)
    
    def get_reset_time(self, key: str) -> Optional[int]:
        try:
            cache_key = f"ratelimit:{key}"
            ttl = self.redis_client.ttl(cache_key)
            
            if ttl > 0:
                return int(time.time()) + ttl
            else:
                return None
                
        except Exception as e:
            logger.error(f"获取Redis重置时间失败: key={key}, error={str(e)}", exc_info=True)
            return None
    
    def cleanup_expired(self) -> int:
        try:
            return 0
            
        except Exception as e:
            logger.error(f"Redis清理过期记录失败: error={str(e)}", exc_info=True)
            return 0


class MemoryRateLimitStorage(RateLimitStorage):
    
    def __init__(self):
        self._adapter = StorageAdapter(redis_client=None)
        self._store: Dict[str, Dict] = self._adapter.memory_store
        logger.info("频率限制器: 内存存储初始化完成（复用 StorageAdapter 内存后端）")
    
    def check_limit(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        try:
            current_time = int(time.time())
            
            if key not in self._store:
                self._store[key] = {
                    'count': 0,
                    'window_start': current_time,
                    'reset_time': current_time + window
                }
            
            limit_data = self._store[key]
            
            if current_time >= limit_data['reset_time']:
                self._store[key] = {
                    'count': 0,
                    'window_start': current_time,
                    'reset_time': current_time + window
                }
                limit_data = self._store[key]
            
            if limit_data['count'] >= limit:
                return False, 0
            
            limit_data['count'] += 1
            remaining = limit - limit_data['count']
            
            return True, remaining
            
        except Exception as e:
            logger.error(f"内存频率限制检查失败: key={key}, error={str(e)}", exc_info=True)
            return True, limit
    
    def reset_limit(self, key: str) -> bool:
        try:
            if key in self._store:
                del self._store[key]
                logger.info(f"频率限制器: 内存重置计数 key={key}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"内存频率限制重置失败: key={key}, error={str(e)}", exc_info=True)
            return False
    
    def get_current_count(self, key: str) -> int:
        try:
            if key not in self._store:
                return 0
            
            limit_data = self._store[key]
            current_time = int(time.time())
            
            if current_time >= limit_data['reset_time']:
                del self._store[key]
                return 0
            
            return limit_data['count']
            
        except Exception as e:
            logger.error(f"获取内存当前计数失败: key={key}, error={str(e)}", exc_info=True)
            return 0
    
    def get_remaining_count(self, key: str, limit: int) -> int:
        current_count = self.get_current_count(key)
        return max(0, limit - current_count)
    
    def get_reset_time(self, key: str) -> Optional[int]:
        try:
            if key not in self._store:
                return None
            
            limit_data = self._store[key]
            current_time = int(time.time())
            
            if current_time >= limit_data['reset_time']:
                return None
            
            return limit_data['reset_time']
            
        except Exception as e:
            logger.error(f"获取内存重置时间失败: key={key}, error={str(e)}", exc_info=True)
            return None
    
    def cleanup_expired(self) -> int:
        try:
            before = len(self._store)
            self._adapter.cleanup_expired()
            after = len(self._store)
            cleaned = before - after
            if cleaned:
                logger.info(f"频率限制器: 清理过期记录 count={cleaned}")
            return cleaned
        except Exception as e:
            logger.error(f"内存清理过期记录失败: error={str(e)}", exc_info=True)
            return 0
