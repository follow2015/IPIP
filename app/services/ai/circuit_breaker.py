# -*- coding: utf-8 -*-
"""AI 调用熔断器，按 provider 维度独立，状态存 Redis（跨进程共享）。

八轮评审新增（P1）：错误率超阈值快速失败，返回预设兜底回复，避免雪崩。
用轻量自实现替代 pybreaker，避免额外依赖且行为可控。

v3（Celery 异步化配套，方案 §6.2）：状态由**进程内字典**改为 **Redis**。

为什么要改：Celery 化后进程数 = gunicorn worker + celery worker（未来还会横向
加机器）。进程内存储时每个进程各自攒够 `failure_threshold` 才跳闸，provider
故障时等效冲击量 = 进程数 × 阈值，「保护 provider 别被打死」的设计初衷被稀释。

线程安全：Redis 路径由 `HINCRBY` / `SET NX` 的原子性保证，无需分布式锁；
降级路径由 `_MemoryState` 自己的 `threading.Lock` 保证（等同改造前的 C6 语义）。
"""
import os
import threading
import time
from typing import Callable, Dict, List, Optional

from app.exceptions.system import ExternalServiceError
from app.utils.logging import get_logger

logger = get_logger(__name__)

_PREFIX = "ai:cb:"
_PROBE_SUFFIX = ":probe"
_INDEX_KEY = f"{_PREFIX}_index"

_STATE_TTL = 3600

_KNOWN_PROVIDERS = ("agentic", "ssh")


class AICircuitOpenError(ExternalServiceError):
    """熔断开启时抛出。"""

    def __init__(self, provider: str):
        super().__init__(service_name="ai", operation="circuit_breaker",
                         message=f"AI 服务 {provider} 暂不可用（熔断开启），请稍后重试")


def _get_redis():
    """解析 Redis 客户端，不可用时返回 None（降级内存模式）。

    a8：直连公开入口 `app.utils.redis_client.get_redis_client`，不再依赖
    `switch_events._get_redis` 这一私有同名函数（后者仅为兼容 shim）。
    """
    try:
        from app.utils.redis_client import get_redis_client
        return get_redis_client()
    except Exception:  # noqa: BLE001
        return None


def _index_provider(r, name: str) -> None:
    """把 provider 名登记进索引集合，供运维端点枚举。

    登记失败不影响熔断主逻辑（索引只服务于可观测性），故静默吞异常。
    """
    try:
        r.sadd(_INDEX_KEY, name)
    except Exception:  # noqa: BLE001
        pass



class _RedisState:
    """Redis 状态后端：跨进程共享。

    失败计数用 `HINCRBY` 原子累加，无需分布式锁；半开探测用 `SET NX` 发令牌，
    保证每个冷却周期内**全局只有一次**探测（而非每进程各一次）。
    """

    storage = "redis"

    def __init__(self, r, name: str, ttl: int = _STATE_TTL):
        self._r = r
        self._name = name
        self._key = f"{_PREFIX}{name}"
        self._probe_key = f"{_PREFIX}{name}{_PROBE_SUFFIX}"
        self._ttl = ttl

    def _refresh_ttl(self) -> None:
        try:
            self._r.expire(self._key, self._ttl)
        except Exception:  # noqa: BLE001
            pass  # TTL 刷新失败不影响计数正确性

    def failures(self) -> int:
        val = self._r.hget(self._key, "failures")
        return int(val) if val else 0

    def incr_failures(self) -> int:
        n = int(self._r.hincrby(self._key, "failures", 1))
        self._refresh_ttl()
        _index_provider(self._r, self._name)
        return n

    def opened_at(self) -> float:
        val = self._r.hget(self._key, "opened_at")
        return float(val) if val else 0.0

    def mark_opened(self, ts: float) -> None:
        self._r.hset(self._key, "opened_at", str(ts))
        self._refresh_ttl()
        _index_provider(self._r, self._name)

    def clear(self) -> None:
        """清零失败计数与开启时间。"""
        self._r.hset(self._key, mapping={"failures": 0, "opened_at": str(0.0)})
        self._refresh_ttl()

    def acquire_probe(self, ttl: int) -> bool:
        """抢占半开探测令牌：每个冷却周期全局仅一次。"""
        return bool(self._r.set(self._probe_key, "1", nx=True, ex=ttl))


class _MemoryState:
    """进程内状态后端：Redis 不可用时的降级路径。

    与改造前语义一致（各进程独立计数），仅保证单进程内线程安全。
    """

    storage = "memory"

    def __init__(self):
        self._failures = 0
        self._opened_at = 0.0
        self._probe_until = 0.0
        self._lock = threading.Lock()

    def failures(self) -> int:
        with self._lock:
            return self._failures

    def incr_failures(self) -> int:
        with self._lock:
            self._failures += 1
            return self._failures

    def opened_at(self) -> float:
        with self._lock:
            return self._opened_at

    def mark_opened(self, ts: float) -> None:
        with self._lock:
            self._opened_at = ts

    def clear(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = 0.0
            self._probe_until = 0.0

    def acquire_probe(self, ttl: int) -> bool:
        with self._lock:
            now = time.time()
            if now < self._probe_until:
                return False
            self._probe_until = now + ttl
            return True



class CircuitBreaker:
    """熔断器：连续失败数超阈值则开启，冷却后半开试探。

    M11 修复：阈值/冷却从 Config 读取，避免硬编码。
    v3：状态外置 Redis，跨进程共享（§6.2）；Redis 不可用时降级进程内。
    """

    def __init__(self, name: str, failure_threshold: Optional[int] = None,
                 cooldown_seconds: Optional[int] = None,
                 state=None):
        self.name = name
        if failure_threshold is None:
            failure_threshold = self._config("AI_CIRCUIT_FAILURE_THRESHOLD", 5)
        if cooldown_seconds is None:
            cooldown_seconds = self._config("AI_CIRCUIT_COOLDOWN_SECONDS", 30)
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

        self.storage = "redis"
        if state is not None:
            self._state = state
            self.storage = getattr(state, "storage", "redis")
        else:
            r = _get_redis()
            if r is not None:
                self._state = _RedisState(r, name)
            else:
                logger.warning(
                    "ai.circuit.redis_unavailable provider=%s 降级进程内计数"
                    "（多进程下熔断保护会稀释）", name)
                self._state = _MemoryState()
                self.storage = "memory"

    @staticmethod
    def _config(key: str, default: int) -> int:
        """从 Config 或环境变量读取阈值配置。"""
        try:
            from config import Config
            value = getattr(Config, key, None)
            if value is not None:
                return int(value)
        except Exception:  # noqa: BLE001
            pass
        try:
            return int(os.getenv(key, default))
        except (TypeError, ValueError):
            return default

    def _is_open(self) -> bool:
        return self._state.failures() >= self.failure_threshold

    def _ensure_redis_state(self) -> None:
        """A4 修复：降级实例在 Redis 恢复后重建共享状态。

        get_circuit_breaker 单例在构造时绑定存储后端且永不重建——若首次调用
        恰逢 Redis 故障，熔断将永久按进程独立计数（跨进程保护稀释且不可恢复，
        需重启进程）。本方法在每次决策前惰性探测：仍是 memory 才探测 Redis，
        已是 redis 的实例零额外开销。并发重建无害（多个 _RedisState 绑定同一
        Redis key，先到者的引用被覆盖而已）。
        """
        if self.storage != "memory":
            return
        r = _get_redis()
        if r is None:
            return
        self._state = _RedisState(r, self.name)
        self.storage = "redis"
        logger.info("ai.circuit.redis_recovered provider=%s 已重建共享熔断状态",
                    self.name)

    def allow_request(self) -> bool:
        """是否允许本次调用（含半开探测窗口）。

        未开启 → 允许；已开启但冷却期已过 → 抢占探测令牌，成功者放行。
        探测成功由 record_success 闭合，失败由 record_failure 重新计时。
        """
        self._ensure_redis_state()
        if not self._is_open():
            return True
        if (time.time() - self._state.opened_at()) < self.cooldown_seconds:
            return False
        return self._state.acquire_probe(self.cooldown_seconds)

    def record_success(self) -> None:
        """调用成功 → 闭合（清零失败计数）。"""
        self._state.clear()

    def record_failure(self) -> None:
        """调用失败 → 累加失败；跨越阈值时开启熔断并刷新计时。"""
        self._ensure_redis_state()
        failures = self._state.incr_failures()
        if failures >= self.failure_threshold:
            self._state.mark_opened(time.time())
            logger.warning("ai.circuit.opened provider=%s failures=%s",
                           self.name, failures)

    def reset(self) -> None:
        """手动重置熔断状态：清零失败计数与开启时间。

        供运维端点（monitor_admin_service.reset_circuit）调用。封装为方法而非
        让调用方直接改状态字段，确保 Redis 与内存两条路径行为一致。
        """
        self._state.clear()

    def snapshot(self) -> Dict[str, object]:
        """返回状态快照，供运维端点读取。

        替代原先直接访问 `_failures` / `_opened_at` 私有字段的写法——
        状态外置后不存在可直接读取的进程内字段。
        """
        opened = self._is_open()
        opened_at = self._state.opened_at()
        cooldown_remaining = (
            max(0, self.cooldown_seconds - (time.time() - opened_at)) if opened else 0
        )
        return {
            "name": self.name,
            "failures": self._state.failures(),
            "threshold": self.failure_threshold,
            "open": opened,
            "cooldown_seconds": self.cooldown_seconds,
            "cooldown_remaining": round(cooldown_remaining, 1),
            "storage": self.storage,
        }

    def call(self, fn: Callable):
        if not self.allow_request():
            raise AICircuitOpenError(self.name)
        try:
            result = fn()
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


_BREAKERS: Dict[str, CircuitBreaker] = {}
_BREAKERS_LOCK = threading.Lock()


def get_circuit_breaker(provider: str) -> CircuitBreaker:
    """获取按 provider 维度独立的熔断器。

    进程内单例字典仅用于**复用实例**（避免每次调用重新解析 Redis），
    熔断状态本身不再存于该字典，而在 Redis（或降级时的实例内）。
    """
    with _BREAKERS_LOCK:
        if provider not in _BREAKERS:
            _BREAKERS[provider] = CircuitBreaker(provider)
        return _BREAKERS[provider]


def known_providers(r=None) -> List[str]:
    """返回应出现在运维视图中的 provider 列表。

    Redis 化后无法从进程内字典枚举（进程只认识自己用过的 provider）。来源按优先级：
    1. Redis 索引集合（**跨进程完整**，由 `_index_provider` 在写状态时登记）；
    2. 已知常量 + 配置中的 `AI_PROVIDER`（Redis 不可用时兜底，覆盖尚未产生
       失败记录的 provider，使其以 0 计数出现在运维视图里）。
    """
    names: List[str] = []
    if r is None:
        r = _get_redis()
    if r is not None:
        try:
            names = sorted(
                d.decode() if isinstance(d, (bytes, bytearray)) else d
                for d in (r.smembers(_INDEX_KEY) or [])
            )
        except Exception:  # noqa: BLE001
            names = []

    with _BREAKERS_LOCK:
        seen = list(_BREAKERS.keys())
    extras = [*_KNOWN_PROVIDERS, *seen]
    try:
        from config import Config
        configured = getattr(Config, "AI_PROVIDER", None)
        if configured:
            extras.append(configured)
    except Exception:  # noqa: BLE001
        pass
    for name in dict.fromkeys(extras):
        if name and name not in names:
            names.append(name)
    return names
