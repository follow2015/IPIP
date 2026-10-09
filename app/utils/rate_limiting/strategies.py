# -*- coding: utf-8 -*-
"""
频率限制策略实现

提供不同的频率限制算法实现，每个策略拥有独立的算法逻辑。
存储层仅提供 KV 读写原语（get/set/incr/expire/exists/zadd/zremrangebyscore/zcard）。

[WARN] **本模块当前是死代码**（2026-09-30 核实，见评审 B1 的「核实补充」）
--------------------------------------------------------------------------
`UnifiedRateLimiter` 的判定路径是 `limiter.is_allowed()` → `storage.check_limit()`
（`limiter.py:100`），**不经过策略层**。`SlidingWindowStrategy` 只在
`limiter.py:53` 被实例化一次，用途仅仅是 `get_strategy_name()` 填到
`limit_info` 里；本模块的 `check_limit(storage, key, ...)` 全仓零调用
（它的签名还多一个 `storage` 参数，与存储层不同）。

保留理由：`RateLimitStrategy` 是 `app/interfaces/rate_limiting.py` 声明的
接口，短期内删掉会让 `UnifiedRateLimiter(strategy=...)` 的入参失去意义。

但请注意：正因为没人调用，这里的缺陷**不会暴露**。2026-09-30 已把
`id(cache_key)` 那处 member 生成改成 uuid4（与存储层同口径），避免将来
有人把策略层接上就复现 B1。**接上之前，本模块仍需按存储层的标准重新评审**
（原子性、member 唯一性、降级语义）。
"""
from app.utils.logging import get_logger
import time
import uuid
from typing import Dict, Any, Tuple

from app.interfaces.rate_limiting import RateLimitStrategy, RateLimitStorage
import app.utils.redis_keys as redis_keys

logger = get_logger(__name__)


class SlidingWindowStrategy(RateLimitStrategy):
    """滑动窗口策略

    使用滑动时间窗口算法实现频率限制，提供更精确的限制控制。
    算法：记录每个请求的时间戳，只统计窗口内的请求数。
    Redis 后端使用 ZSET 实现，内存后端使用 deque 实现。
    """

    def check_limit(self, storage: RateLimitStorage, key: str,
                   limit: int, window: int) -> Tuple[bool, int]:
        """检查限制（滑动窗口算法）

        Args:
            storage: 存储后端
            key: 限制键
            limit: 限制数量
            window: 时间窗口（秒）

        Returns:
            Tuple[bool, int]: (是否允许, 剩余数量)
        """
        current_time = time.time()
        window_start = current_time - window
        cache_key = redis_keys.ratelimit_key("sw", key)

        if hasattr(storage, 'redis_client'):
            return self._check_limit_redis(storage, cache_key, limit, window, current_time, window_start)

        return self._check_limit_memory(storage, cache_key, limit, window, current_time, window_start)

    def _check_limit_redis(self, storage: RateLimitStorage, cache_key: str,
                          limit: int, window: int, current_time: float,
                          window_start: float) -> Tuple[bool, int]:
        """Redis 滑动窗口实现（基于 ZSET）"""
        try:
            redis = storage.redis_client

            redis.zremrangebyscore(cache_key, 0, window_start)

            current_count = redis.zcard(cache_key)

            if current_count >= limit:
                return False, 0

            request_id = f"{current_time}:{uuid.uuid4().hex}"
            redis.zadd(cache_key, {request_id: current_time})
            redis.expire(cache_key, window)

            remaining = limit - current_count - 1
            return True, remaining

        except Exception as e:  # noqa: BLE001 -- 限流器 fail-open：限流组件故障不得阻断业务请求，按"放行"处理并告警
            logger.error(f"Redis滑动窗口检查失败: key={cache_key}, error={e}")
            return True, limit

    def _check_limit_memory(self, storage: RateLimitStorage, cache_key: str,
                           limit: int, window: int, current_time: float,
                           window_start: float) -> Tuple[bool, int]:
        """内存滑动窗口实现（基于时间戳列表）"""
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

        except Exception as e:  # noqa: BLE001 -- 限流器 fail-open：限流组件故障不得阻断业务请求，按"放行"处理并告警
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
    """固定窗口策略

    使用固定窗口算法实现频率限制，内存使用较少但精度稍低。
    算法：将时间划分为固定窗口，每个窗口内独立计数。
    """

    def check_limit(self, storage: RateLimitStorage, key: str,
                   limit: int, window: int) -> Tuple[bool, int]:
        """检查限制（固定窗口算法）

        Args:
            storage: 存储后端
            key: 限制键
            limit: 限制数量
            window: 时间窗口（秒）

        Returns:
            Tuple[bool, int]: (是否允许, 剩余数量)
        """
        current_time = int(time.time())
        cache_key = redis_keys.ratelimit_key("fw", key)

        if hasattr(storage, 'redis_client'):
            return self._check_limit_redis(storage, cache_key, limit, window, current_time)

        return self._check_limit_memory(storage, cache_key, limit, window, current_time)

    def _check_limit_redis(self, storage: RateLimitStorage, cache_key: str,
                          limit: int, window: int, current_time: int) -> Tuple[bool, int]:
        """Redis 固定窗口实现"""
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

        except Exception as e:  # noqa: BLE001 -- 限流器 fail-open：限流组件故障不得阻断业务请求，按"放行"处理并告警
            logger.error(f"Redis固定窗口检查失败: key={cache_key}, error={e}")
            return True, limit

    def _check_limit_memory(self, storage: RateLimitStorage, cache_key: str,
                           limit: int, window: int, current_time: int) -> Tuple[bool, int]:
        """内存固定窗口实现"""
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

        except Exception as e:  # noqa: BLE001 -- 限流器 fail-open：限流组件故障不得阻断业务请求，按"放行"处理并告警
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
    """令牌桶策略

    使用令牌桶算法实现频率限制，支持突发流量。
    算法：以固定速率向桶中添加令牌，每次请求消耗一个令牌。
    """

    def __init__(self, bucket_size: int = None):
        """初始化令牌桶策略

        Args:
            bucket_size: 桶大小，如果为None则使用limit作为桶大小
        """
        self.bucket_size = bucket_size

    def check_limit(self, storage: RateLimitStorage, key: str,
                   limit: int, window: int) -> Tuple[bool, int]:
        """检查限制（令牌桶算法）

        Args:
            storage: 存储后端
            key: 限制键
            limit: 限制数量（每窗口生成的令牌数）
            window: 时间窗口（秒）

        Returns:
            Tuple[bool, int]: (是否允许, 剩余令牌数)
        """
        current_time = time.time()
        bucket_size = self.bucket_size or limit
        tokens_per_second = limit / window
        cache_key = redis_keys.ratelimit_key("tb", key)

        if hasattr(storage, 'redis_client'):
            return self._check_limit_redis(storage, cache_key, bucket_size, tokens_per_second, current_time)

        return self._check_limit_memory(storage, cache_key, bucket_size, tokens_per_second, current_time)

    def _check_limit_redis(self, storage: RateLimitStorage, cache_key: str,
                          bucket_size: int, tokens_per_second: float,
                          current_time: float) -> Tuple[bool, int]:
        """Redis 令牌桶实现"""
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

        except Exception as e:  # noqa: BLE001 -- 限流器 fail-open：限流组件故障不得阻断业务请求，按"放行"处理并告警
            logger.error(f"Redis令牌桶检查失败: key={cache_key}, error={e}")
            return True, bucket_size

    def _check_limit_memory(self, storage: RateLimitStorage, cache_key: str,
                           bucket_size: int, tokens_per_second: float,
                           current_time: float) -> Tuple[bool, int]:
        """内存令牌桶实现"""
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

        except Exception as e:  # noqa: BLE001 -- 限流器 fail-open：限流组件故障不得阻断业务请求，按"放行"处理并告警
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
