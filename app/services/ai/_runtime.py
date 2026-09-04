# -*- coding: utf-8 -*-
"""AI 运行时工具：redis 客户端、审计、指标、缓存的统一接入点。

C1 修复：把"组件存在但未接线"的熔断/审计/指标/缓存接到调用路径。
本模块提供 service 层用的薄封装，避免每个 service 重复样板。
"""
import time
from typing import Any, Optional

from app.services.ai.ai_audit_logger import AIAuditLogger
from app.services.ai.ai_cache import AIResponseCache
from app.services.ai.metrics import record_call
from app.utils.logging import get_logger

logger = get_logger(__name__)

_AUDIT = AIAuditLogger()


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
    """统一审计 + 指标埋点（best-effort，不抛异常）。"""
    try:
        from config import Config
        default_model = getattr(Config, "AI_MODEL", "unknown")
        record_call(scenario=scenario, model=model or default_model, user_id=user_id,
                    tokens=tokens or 0, duration_seconds=duration_ms / 1000.0,
                    status=status)
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.metrics.record_failed %s", e)
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
        self.duration_ms = int((time.monotonic() - self.start) * 1000)
        return False
