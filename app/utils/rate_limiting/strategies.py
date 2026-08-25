# -*- coding: utf-8 -*-
"""
频率限制策略实现

提供不同的频率限制算法实现，每个策略拥有独立的算法逻辑。
存储层仅提供 KV 读写原语（get/set/incr/expire/exists/zadd/zremrangebyscore/zcard）。
"""
from app.utils.logging import get_logger
import time
from typing import Dict, Any, Tuple, List

from app.interfaces.rate_limiting import RateLimitStrategy, RateLimitStorage

logger = get_logger(__name__)


class SlidingWindowStrategy(RateLimitStrategy):

    def check_limit(self, storage: RateLimitStorage, key: str,
                   limit: int, window: int) -> Tuple[bool, int]:
        current_time = time.time()
        window_start = current_time - window
        cache_key = f"ratelimit:sw:{key}"

        if hasattr(storage, 'redis_client'):
            return self._check_limit_redis(storage, cache_key, limit, window, current_time, window_start)

        return self._check_limit_memory(storage, cache_key, limit, window, current_time, window_start)

    def _check_limit_redis(self, storage: RateLimitStorage, cache_key: str,
                          limit: int, window: int, current_time: float,
                          window_start: float) -> Tuple[bool, int]:
        try:
            redis = storage.redis_client

            redis.zremrangebyscore(cache_key, 0, window_start)

            current_count = redis.zcard(cache_key)

            if current_count >= limit:
                return False, 0

            request_id = f"{current_time}:{id(cache_key)}"
            redis.zadd(cache_key, {request_id: current_time})
            redis.expire(cache_key, window)

            remaining = limit - current_count - 1
            return True, remaining

        except Exception as e:
            logger.error(f"Redis滑动窗口检查失败: key={cache_key}, error={e}")
            return True, limit

    def _check_limit_memory(self, storage: RateLimitStorage, cache_key: str,
                           limit: int, window: int, current_time: float,
                           window_start: float) -> Tuple[bool, int]:
        try:
            timestamps = storage._store.get(cache_key, {}).get('timestamps', [])

            timestamps = [ts for ts in timestamps if ts > window_start]

            current_count = len(timestamps)

            if current_count >= limit:
                storage._store[cache_key] = {'timestamps': timestamps}
                return False, 0

            timestamps.append(current_time)
            storage._store[cache_key] = {'timestamps': timestamps}

            remaining = limit - current_count - 1
            return True, remaining

        except Exception as e:
            logger.error(f"内存滑动窗口检查失败: key={cache_key}, error={e}")
            return True, limit

    def get_strategy_name(self) -> str:
        return "sliding_window"

    def get_strategy_config(self) -> Dict[str, Any]:
        return {
            "name": self.get_strategy_name(),
            "description": "滑动窗口算法，提供精确的频率限制",
            "precision": "high",
            "memory_usage": "medium"
        }


class FixedWindowStrategy(RateLimitStrategy):

    def check_limit(self, storage: RateLimitStorage, key: str,
                   limit: int, window: int) -> Tuple[bool, int]:
        current_time = int(time.time())
        cache_key = f"ratelimit:fw:{key}"

        if hasattr(storage, 'redis_client'):
            return self._check_limit_redis(storage, cache_key, limit, window, current_time)

        return self._check_limit_memory(storage, cache_key, limit, window, current_time)

    def _check_limit_redis(self, storage: RateLimitStorage, cache_key: str,
                          limit: int, window: int, current_time: int) -> Tuple[bool, int]:
        try:
            redis = storage.redis_client
            window_key = f"{cache_key}:{current_time // window}"

            count = redis.incr(window_key)
            if count == 1:
                redis.expire(window_key, window)

            if count > limit:
                return False, 0

            remaining = limit - count
            return True, remaining

        except Exception as e:
            logger.error(f"Redis固定窗口检查失败: key={cache_key}, error={e}")
            return True, limit

    def _check_limit_memory(self, storage: RateLimitStorage, cache_key: str,
                           limit: int, window: int, current_time: int) -> Tuple[bool, int]:
        try:
            if cache_key not in storage._store:
                storage._store[cache_key] = {
                    'count': 0,
                    'window_start': current_time,
                    'reset_time': current_time + window
                }

            limit_data = storage._store[cache_key]

            if current_time >= limit_data['reset_time']:
                storage._store[cache_key] = {
                    'count': 0,
                    'window_start': current_time,
                    'reset_time': current_time + window
                }
                limit_data = storage._store[cache_key]

            if limit_data['count'] >= limit:
                return False, 0

            limit_data['count'] += 1
            remaining = limit - limit_data['count']

            return True, remaining

        except Exception as e:
            logger.error(f"内存固定窗口检查失败: key={cache_key}, error={e}")
            return True, limit

    def get_strategy_name(self) -> str:
        return "fixed_window"

    def get_strategy_config(self) -> Dict[str, Any]:
        return {
            "name": self.get_strategy_name(),
            "description": "固定窗口算法，内存使用少但精度稍低",
            "precision": "medium",
            "memory_usage": "low"
        }


class TokenBucketStrategy(RateLimitStrategy):

    def __init__(self, bucket_size: int = None):
        self.bucket_size = bucket_size

    def check_limit(self, storage: RateLimitStorage, key: str,
                   limit: int, window: int) -> Tuple[bool, int]:
        current_time = time.time()
        bucket_size = self.bucket_size or limit
        tokens_per_second = limit / window
        cache_key = f"ratelimit:tb:{key}"

        if hasattr(storage, 'redis_client'):
            return self._check_limit_redis(storage, cache_key, bucket_size, tokens_per_second, current_time)

        return self._check_limit_memory(storage, cache_key, bucket_size, tokens_per_second, current_time)

    def _check_limit_redis(self, storage: RateLimitStorage, cache_key: str,
                          bucket_size: int, tokens_per_second: float,
                          current_time: float) -> Tuple[bool, int]:
        try:
            redis = storage.redis_client

            bucket_data = redis.hgetall(cache_key)
            if not bucket_data:
                redis.hset(cache_key, mapping={
                    'tokens': bucket_size,
                    'last_refill': current_time
                })
                redis.expire(cache_key, 3600)
                available_tokens = bucket_size
            else:
                last_tokens = float(bucket_data.get(b'tokens', bucket_size))
                last_refill = float(bucket_data.get(b'last_refill', current_time))

                elapsed = current_time - last_refill
                refill = elapsed * tokens_per_second
                available_tokens = min(bucket_size, last_tokens + refill)

            if available_tokens < 1:
                return False, 0

            new_tokens = available_tokens - 1
            redis.hset(cache_key, mapping={
                'tokens': new_tokens,
                'last_refill': current_time
            })

            return True, int(new_tokens)

        except Exception as e:
            logger.error(f"Redis令牌桶检查失败: key={cache_key}, error={e}")
            return True, bucket_size

    def _check_limit_memory(self, storage: RateLimitStorage, cache_key: str,
                           bucket_size: int, tokens_per_second: float,
                           current_time: float) -> Tuple[bool, int]:
        try:
            if cache_key not in storage._store:
                storage._store[cache_key] = {
                    'tokens': float(bucket_size),
                    'last_refill': current_time
                }

            bucket_data = storage._store[cache_key]

            elapsed = current_time - bucket_data['last_refill']
            refill = elapsed * tokens_per_second
            available_tokens = min(bucket_size, bucket_data['tokens'] + refill)

            if available_tokens < 1:
                return False, 0

            bucket_data['tokens'] = available_tokens - 1
            bucket_data['last_refill'] = current_time

            return True, int(bucket_data['tokens'])

        except Exception as e:
            logger.error(f"内存令牌桶检查失败: key={cache_key}, error={e}")
            return True, bucket_size

    def get_strategy_name(self) -> str:
        return "token_bucket"

    def get_strategy_config(self) -> Dict[str, Any]:
        return {
            "name": self.get_strategy_name(),
            "description": "令牌桶算法，支持突发流量",
            "precision": "high",
            "memory_usage": "medium",
            "bucket_size": self.bucket_size
        }
