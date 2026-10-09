# -*- coding: utf-8 -*-
"""
频率限制存储实现

提供 Redis / 内存两种后端，以及把两者串成**主备降级**的
`FailoverRateLimitStorage`。

存储拓扑（2026-09-30 改造，详见 docs/review/后端代码评审-20260929.md B2 的
「核实补充」）
--------------------------------------------------------------------------
    UnifiedRateLimiter.storage
        └── FailoverRateLimitStorage
                ├── primary   = RedisRateLimitStorage（全局精确，Lua 原子滑动窗口）
                └── secondary = MemoryRateLimitStorage（进程内，固定窗口）

为什么是**主备**而不是缓存层那种 L1/L2 双写：
  · 缓存是「两级都能命中、miss 后回填」——读多写少，副本间允许短暂不一致；
  · 限流的计数必须全局一致才有意义，**双写会让两边计数分叉**，而内存侧在
    `--workers 4` 下根本无法反映全局。
  所以这里照抄的是缓存层的**结构**（primary/secondary + 统一入口 + 健康
  探测），不是它的**组合语义**。

Redis 不可用时发生什么（这是本模块存在的全部理由）：
  · 旧实现：`RedisRateLimitStorage.check_limit` 自己 `except` 吞掉异常并
    `return True, limit` ⇒ 完全放行（fail-open 裸奔），且 `limiter` 的
    `fail_close=True` 永远到不了——异常在存储层就没了。
  · 现在：存储层不再吞异常，改由 Failover 捕获并切到 secondary ⇒
    **精度下降（按 worker 数放大），但仍有界**；只有主备都不可用时，
    才把决策权交回 limiter 的 fail_close。
"""
from app.utils.logging import get_logger
import threading
import time
import uuid
from typing import Dict, Optional, Tuple

from app.interfaces.rate_limiting import RateLimitStorage
from app.utils.cache import cache_manager
from app.utils.storage import StorageAdapter
import app.utils.redis_keys as redis_keys

logger = get_logger(__name__)

KEY_PREFIX = redis_keys.RATELIMIT_PREFIX

_SLIDING_WINDOW_LUA = """
local key      = KEYS[1]
local now      = tonumber(ARGV[1])
local window   = tonumber(ARGV[2])
local limit    = tonumber(ARGV[3])
local member   = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
    return {0, 0}
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window * 1000)
return {1, limit - count - 1}
"""


_UNSET = object()


class RateLimitStorageUnavailable(Exception):
    """存储后端不可用（Redis 断连 / 客户端未初始化 / 脚本执行失败）。

    语义：**不是**「请放行」，而是「我判不了，交给上层决定」。
    旧实现把它当成放行处理，正是 B2 的根因——异常在存储层被吞掉，
    `limiter` 里那段正确的 fail_close 分支永远执行不到。
    """


class RedisRateLimitStorage(RateLimitStorage):
    """Redis存储实现
    
    使用Redis作为频率限制数据的存储后端。
    """
    
    def __init__(self, redis_client=_UNSET):
        """初始化Redis存储

        Args:
            redis_client: 显式传入的客户端；**省略**时取缓存层 L2 的客户端。
                [WARN] 该客户端在 Redis 不可用时是 **None**（`RedisCacheStorage.
                _init_redis()` 失败时返回 None 而非抛异常），故每个方法都先
                判空——不能让 AttributeError 冒充"限流判定成功"。

        [WARN] 默认值用 `_UNSET` 哨兵而不是 `None`，是为了让 `None` 保有它
        自己的语义（"就是没有客户端"）。若写成 `redis_client=None` 再判空回退，
        调用方**无法**表达"构造一个没有客户端的实例"，B2 的判空分支也就无法
        被直接测到——只能靠 mock 间接覆盖。
        """
        self.redis_client = cache_manager.primary_storage.redis_client \
            if redis_client is _UNSET else redis_client
        self._script = None
        logger.info("频率限制器: Redis存储初始化完成")

    @staticmethod
    def _cache_key(key: str) -> str:
        return f"{KEY_PREFIX}{key}"

    def _get_script(self):
        """懒加载 Lua 脚本对象（register_script 只发一次 EVAL，后续走 EVALSHA）。"""
        if self._script is None:
            self._script = self.redis_client.register_script(_SLIDING_WINDOW_LUA)
        return self._script

    def check_limit(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        """检查是否超过限制（滑动窗口，单次 Lua 原子完成）。

        Args:
            key: 限制键
            limit: 允许的请求数量
            window: 时间窗口（秒）

        Returns:
            Tuple[bool, int]: (是否允许请求, 剩余请求数)

        Raises:
            RateLimitStorageUnavailable: Redis 不可用。**不返回"放行"** ——
                判不了就交给上层（FailoverRateLimitStorage）降级，而不是
                假装没超限。旧实现在这里 `return True, limit`，是 B2 的根因。
        """
        client = self.redis_client
        if client is None:
            raise RateLimitStorageUnavailable("Redis 客户端未初始化")

        cache_key = self._cache_key(key)
        try:
            result = self._get_script()(
                keys=[cache_key],
                args=[int(time.time()), int(window), int(limit), uuid.uuid4().hex],
            )
        except Exception as e:
            self._script = None
            logger.warning(f"Redis频率限制检查失败: key={key}, error={e}")
            raise RateLimitStorageUnavailable(str(e)) from e

        allowed = bool(int(result[0]))
        remaining = int(result[1])
        return allowed, remaining

    def reset_limit(self, key: str) -> bool:
        """重置限制计数

        Raises:
            RateLimitStorageUnavailable: Redis 不可用
        """
        client = self.redis_client
        if client is None:
            raise RateLimitStorageUnavailable("Redis 客户端未初始化")
        try:
            result = client.delete(self._cache_key(key))
            logger.info(f"频率限制器: Redis重置计数 key={key}, result={result}")
            return result > 0
        except Exception as e:
            logger.warning(f"Redis频率限制重置失败: key={key}, error={e}")
            raise RateLimitStorageUnavailable(str(e)) from e

    def get_current_count(self, key: str) -> int:
        """获取当前计数

        Raises:
            RateLimitStorageUnavailable: Redis 不可用
        """
        client = self.redis_client
        if client is None:
            raise RateLimitStorageUnavailable("Redis 客户端未初始化")
        try:
            return int(client.zcard(self._cache_key(key)))
        except Exception as e:
            logger.warning(f"获取Redis当前计数失败: key={key}, error={e}")
            raise RateLimitStorageUnavailable(str(e)) from e

    def get_remaining_count(self, key: str, limit: int) -> int:
        """获取剩余请求数"""
        return max(0, limit - self.get_current_count(key))

    def get_reset_time(self, key: str) -> Optional[int]:
        """获取重置时间

        Raises:
            RateLimitStorageUnavailable: Redis 不可用
        """
        client = self.redis_client
        if client is None:
            raise RateLimitStorageUnavailable("Redis 客户端未初始化")
        try:
            ttl = client.ttl(self._cache_key(key))
            return int(time.time()) + int(ttl) if ttl and ttl > 0 else None
        except Exception as e:
            logger.warning(f"获取Redis重置时间失败: key={key}, error={e}")
            raise RateLimitStorageUnavailable(str(e)) from e

    def cleanup_expired(self) -> int:
        """清理过期的限制记录

        Redis 靠 PEXPIRE 自动清理，这里无需动作。返回 0 表示"无手动清理"。
        """
        return 0


class MemoryRateLimitStorage(RateLimitStorage):
    """内存存储实现（固定窗口，进程内）

    用途：单机部署，或 Redis 不可用时的**降级备机**。
    内部组合 StorageAdapter 的内存后端，避免重复实现 KV 操作。

    [WARN] 语义提醒：这是**固定窗口**，与 Redis 侧的**滑动窗口**不是同一种算法。
    降级到这里后，窗口切换瞬间最多可放行 2×limit（边界突刺）——这是为
    "Redis 挂了也还有个上界"付出的代价，比完全放行好，但不要把它当成
    与 Redis 等价的实现。
    """

    def __init__(self):
        """初始化内存存储"""
        self._adapter = StorageAdapter(redis_client=None)
        self._store: Dict[str, Dict] = self._adapter.memory_store
        self._lock = threading.RLock()
        logger.info("频率限制器: 内存存储初始化完成（复用 StorageAdapter 内存后端）")

    def check_limit(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        """检查是否超过限制（固定窗口）

        Raises:
            RateLimitStorageUnavailable: 内存存储自身异常（理论上不会，
                但语义必须与 Redis 侧一致：判不了就抛，不静默放行）。
        """
        try:
            with self._lock:
                current_time = int(time.time())

                limit_data = self._store.get(key)
                if limit_data is None or current_time >= limit_data['reset_time']:
                    limit_data = {
                        'count': 0,
                        'window_start': current_time,
                        'reset_time': current_time + window,
                    }
                    self._store[key] = limit_data

                if limit_data['count'] >= limit:
                    return False, 0

                limit_data['count'] += 1
                return True, limit - limit_data['count']

        except Exception as e:
            logger.error(f"内存频率限制检查失败: key={key}, error={e}", exc_info=True)
            raise RateLimitStorageUnavailable(str(e)) from e

    def reset_limit(self, key: str) -> bool:
        """重置限制计数"""
        with self._lock:
            if key in self._store:
                del self._store[key]
                logger.info(f"频率限制器: 内存重置计数 key={key}")
                return True
            return False

    def get_current_count(self, key: str) -> int:
        """获取当前计数"""
        with self._lock:
            limit_data = self._store.get(key)
            if limit_data is None:
                return 0
            if int(time.time()) >= limit_data['reset_time']:
                del self._store[key]
                return 0
            return limit_data['count']

    def get_remaining_count(self, key: str, limit: int) -> int:
        """获取剩余请求数"""
        return max(0, limit - self.get_current_count(key))

    def get_reset_time(self, key: str) -> Optional[int]:
        """获取重置时间"""
        with self._lock:
            limit_data = self._store.get(key)
            if limit_data is None:
                return None
            if int(time.time()) >= limit_data['reset_time']:
                return None
            return limit_data['reset_time']

    def cleanup_expired(self) -> int:
        """清理过期的限制记录

        委托给 StorageAdapter 的 cleanup_expired 方法。

        Returns:
            int: 清理的记录数量
        """
        try:
            with self._lock:
                before = len(self._store)
                self._adapter.cleanup_expired()
                cleaned = before - len(self._store)
            if cleaned:
                logger.info(f"频率限制器: 清理过期记录 count={cleaned}")
            return cleaned
        except Exception as e:
            logger.error(f"内存清理过期记录失败: error={e}", exc_info=True)
            return 0


class FailoverRateLimitStorage(RateLimitStorage):
    """主备降级存储：Redis 为主，内存为备。

    存在的理由（B2 的修复）：旧实现里 Redis 侧自己吞异常并 `return True`，
    于是「Redis 挂掉」直接等价于「限流完全放行」，而 `limiter` 那段正确的
    fail_close 分支永远执行不到。这里把降级决策**上提一层**：

        Redis 健康   → primary（全局精确）
        Redis 不健康 → secondary（进程内，按 worker 数放大，但有界）
        两者都不可用 → 抛 RateLimitStorageUnavailable，交给 limiter 的
                       fail_close / fail_open 决策

    **不是 L1/L2 双写**：见本模块 docstring。限流计数必须全局一致，双写会
    让两边计数分叉；这里只在 primary 判不了时才动用 secondary。

    恢复机制（旧代码所没有的）：
    `StorageAdapter` 的降级是单向的（`use_redis = False` 之后永不恢复），
    那对缓存可以接受（L1 仍能服务），对限流不行（会永久退化成 N 倍配额）。
    故这里用「连续失败计数 + 冷却期后探测」：连续失败达到阈值才降级，
    冷却期内直接用备机，冷却期过后**每次请求都试一次 primary**，成功即恢复。
    """

    FAILURE_THRESHOLD = 3
    PROBE_COOLDOWN = 30.0

    def __init__(self, primary: RateLimitStorage, secondary: RateLimitStorage,
                 failure_threshold: int = FAILURE_THRESHOLD,
                 probe_cooldown: float = PROBE_COOLDOWN):
        self.primary = primary
        self.secondary = secondary
        self.failure_threshold = failure_threshold
        self.probe_cooldown = probe_cooldown
        self._failures = 0
        self._degraded = False
        self._degraded_until = 0.0
        self._lock = threading.RLock()

    @property
    def degraded(self) -> bool:
        """当前是否处于降级态（只读，供监控/测试观测）。"""
        return self._degraded

    def _on_primary_failure(self, err: Exception) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                if not self._degraded:
                    logger.warning(
                        "频率限制器: Redis 连续失败 %s 次，降级到内存存储 %ss"
                        "（限流精度按 worker 数放大，但仍有界）",
                        self._failures, self.probe_cooldown,
                    )
                self._degraded = True
                self._degraded_until = time.time() + self.probe_cooldown

    def _on_primary_success(self) -> None:
        with self._lock:
            if self._failures or self._degraded:
                if self._degraded:
                    logger.info("频率限制器: Redis 已恢复，退出降级")
                self._failures = 0
                self._degraded = False
                self._degraded_until = 0.0

    def _should_try_primary(self) -> bool:
        """未降级时总走 primary；降级后冷却期内不打，冷却期过则探测一次。"""
        if not self._degraded:
            return True
        return time.time() >= self._degraded_until

    def check_limit(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        """主优先，失败降级到备；两者都失败则抛出。"""
        if self._should_try_primary():
            try:
                result = self.primary.check_limit(key, limit, window)
                self._on_primary_success()
                return result
            except Exception as e:  # noqa: BLE001 -- 降级判据：任何存储异常都要切备机
                self._on_primary_failure(e)

        try:
            return self.secondary.check_limit(key, limit, window)
        except Exception as e:
            logger.error(f"频率限制器: 主备存储均不可用 key={key}, error={e}")
            raise RateLimitStorageUnavailable(
                f"primary 与 secondary 均不可用: {e}"
            ) from e

    def reset_limit(self, key: str) -> bool:
        """主备都清一遍：避免恢复后残留旧计数。"""
        ok_primary = False
        ok_secondary = False
        if self._should_try_primary():
            try:
                ok_primary = self.primary.reset_limit(key)
                self._on_primary_success()
            except Exception as e:  # noqa: BLE001 -- 同上
                self._on_primary_failure(e)
        try:
            ok_secondary = self.secondary.reset_limit(key)
        except Exception as e:  # noqa: BLE001 -- 备机也不行时只记日志：reset 是管理操作，不影响放行判定
            logger.error(f"频率限制器: 备机重置失败 key={key}, error={e}")
        return ok_primary or ok_secondary

    def get_current_count(self, key: str) -> int:
        if self._should_try_primary():
            try:
                count = self.primary.get_current_count(key)
                self._on_primary_success()
                return count
            except Exception as e:  # noqa: BLE001 -- 同上
                self._on_primary_failure(e)
        try:
            return self.secondary.get_current_count(key)
        except Exception as e:  # noqa: BLE001 -- 查询类：全部失败返回 0（"无计数"），不抛（不阻断 limit_info 组装）
            logger.error(f"频率限制器: 主备查询当前计数均失败 key={key}, error={e}")
            return 0

    def get_remaining_count(self, key: str, limit: int) -> int:
        return max(0, limit - self.get_current_count(key))

    def get_reset_time(self, key: str) -> Optional[int]:
        if self._should_try_primary():
            try:
                reset_time = self.primary.get_reset_time(key)
                self._on_primary_success()
                return reset_time
            except Exception as e:  # noqa: BLE001 -- 同上
                self._on_primary_failure(e)
        try:
            return self.secondary.get_reset_time(key)
        except Exception as e:  # noqa: BLE001 -- 同上，返回 None 表示"未知"
            logger.error(f"频率限制器: 主备查询重置时间均失败 key={key}, error={e}")
            return None

    def cleanup_expired(self) -> int:
        cleaned = 0
        if self._should_try_primary():
            try:
                cleaned += self.primary.cleanup_expired()
                self._on_primary_success()
            except Exception as e:  # noqa: BLE001 -- 同上
                self._on_primary_failure(e)
        try:
            cleaned += self.secondary.cleanup_expired()
        except Exception as e:  # noqa: BLE001 -- 清理失败不影响放行判定
            logger.error(f"频率限制器: 备机清理失败 error={e}")
        return cleaned