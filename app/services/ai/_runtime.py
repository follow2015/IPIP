# -*- coding: utf-8 -*-
"""AI 运行时工具：redis 客户端、审计、指标、缓存的统一接入点。

C1 修复：把"组件存在但未接线"的熔断/审计/指标/缓存接到调用路径。
本模块提供 service 层用的薄封装，避免每个 service 重复样板。
"""
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional

from app.services.ai.ai_audit_logger import AIAuditLogger
from app.services.ai.ai_cache import AIResponseCache
from app.utils.logging import get_logger

logger = get_logger(__name__)

_AUDIT = AIAuditLogger()

_bound_scenario: ContextVar[str] = ContextVar("ai_bound_scenario", default="unknown")


@contextmanager
def bind_scenario(scenario: str) -> Iterator[None]:
    """在上下文内绑定 AI 场景，供 provider 层埋点读取。

    Args:
        scenario: 场景名，如 "rag" / "skill.device_inspect" / "agentic.diagnosis"。
    """
    token = _bound_scenario.set(scenario or "unknown")
    try:
        yield
    finally:
        _bound_scenario.reset(token)


def current_scenario() -> str:
    """返回当前上下文绑定的 AI 场景，未绑定时为 "unknown"。"""
    return _bound_scenario.get()


def get_redis_client():
    """复用全局 Redis 单例池（app.utils.redis_client），失败返回 None。

    B3 修复：原实现 except 后静默 `return None`，Redis 故障时缓存与审计会
    静默失效而运维完全无感知（仅表现为"缓存命中率莫名归零"）。此处补 warning
    日志，使基础设施故障可观测。

    V2 收敛：连接逻辑统一收敛至 app.utils.redis_client，本函数保留为 AI 域
    兼容包装（make_cache 等调用方不变），仅补域级故障日志。
    """
    try:
        from app.utils.redis_client import get_redis_client as _shared
        return _shared()
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.redis.unavailable %s", e)
        return None


def make_cache() -> AIResponseCache:
    """构造注入了 redis 的 AIResponseCache。"""
    return AIResponseCache(redis_client=get_redis_client())


def observe_call(scenario: str, user_id: int, request: Any, response: Any,
                 status: str, duration_ms: int, tokens: Optional[int] = None,
                 model: Optional[str] = None, base_url: Optional[str] = None) -> None:
    """统一审计埋点（best-effort，不抛异常）。

    注意：本函数**不再写 Prometheus/Redis 指标**。token 与耗时的真值只在
    provider 层（resp.usage）可得，指标已下沉到 openai_provider 的
    chat/chat_stream 出口，此处再计一次会造成双计。
    """
    try:
        _AUDIT.log(user_id=user_id, scenario=scenario, request=request,
                   response=response, duration_ms=duration_ms, status=status,
                   tokens=tokens, model=model, base_url=base_url)
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.audit.log_failed %s", e)


class CallTimer:
    """with 上下文计时器，记录耗时毫秒。"""

    def __init__(self):
        self.start = 0.0
        self.duration_ms = 0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, *exc):
        self.duration_ms = self.elapsed_ms()
        return False

    def elapsed_ms(self) -> int:
        """返回自进入上下文以来的耗时（毫秒），可随时调用。

        为什么调用方必须用它而不是读 `duration_ms`：`duration_ms` 只在
        `__exit__` 里赋值，而调用方普遍在 **with 体内的 finally** 中读值——
        此刻 `__exit__` 尚未执行，读到的是初始值 0。表现为审计日志里
        `duration_ms` 恒为 0（AI 调用的耗时审计全部失效）。
        """
        return int((time.monotonic() - self.start) * 1000)
