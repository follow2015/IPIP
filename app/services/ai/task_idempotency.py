# -*- coding: utf-8 -*-
"""AI 任务幂等占位（方案 §6.1.2，remedial 重复下发防护）。


`acks_late=False`（at-most-once）已经堵死「worker 崩溃后 Celery 重投」，但
**堵不住客户端重试**：前端在 401 时会自动重放原请求
（`frontend-new/src/services/api-client.ts:105`），请求超时/网络抖动时用户也会
重试。每次重试都会走一次新的 `.delay()`，生成全新 task.id。

因此幂等键必须由**客户端**在「用户确认动作」发生时生成，并在重试中原样携带；
路由层用这个 key 做**原子**占位，只有占位成功才真正入队。


`get_progress()` 在任务 done / 超时后会 `task_state.delete(task_id)`
（`rag_ingest_async.py:97/101`）。若幂等记录存在 `ai:task:` 下，前端订阅完 SSE
键即被删除，此后重试 100% 穿透。故必须用独立键空间。


`load()` 判断再 `save()` 是读-改-写：双击或并发重试的两个请求都会读到 None，
然后双双入队 → 命令被下发两次。`SET NX` 是单条 Redis 命令，天然互斥。
"""
from typing import Optional, Tuple

from app.utils.logging import get_logger

logger = get_logger(__name__)

_PREFIX = "ai:idem:"
_TTL = 86400


def _scoped_key(key: str, user_id: int) -> str:
    """a10：幂等键按 user_id 命名空间隔离。

    幂等键由客户端生成，若全局共享同一键空间，跨用户撞键会拿到他人的
    task_id（归属校验可兜底，但存在性信息仍外泄）。user_id 为必填参数，
    在签名层面杜绝调用方遗漏。
    """
    return f"{_PREFIX}{user_id}:{key}"


class IdempotencyUnavailableError(RuntimeError):
    """A8：fail_closed 模式下 Redis 不可用——高危写操作拒绝放行（路由转 503）。"""


def _get_redis():
    """解析 Redis 客户端，不可用时返回 None。

    a8：直连公开入口 `app.utils.redis_client.get_redis_client`，不再依赖
    `switch_events._get_redis` 这一私有同名函数（后者仅为兼容 shim）。
    """
    try:
        from app.utils.redis_client import get_redis_client
        return get_redis_client()
    except Exception:  # noqa: BLE001
        return None


def try_claim(
    key: str, task_id: str, user_id: int, fail_closed: bool = False
) -> Tuple[bool, Optional[str]]:
    """原子占位：成功返回 (True, None)，重复返回 (False, 首次的 task_id)。

    Args:
        key: 客户端生成的幂等键（同一次用户确认动作复用同一个）。
        task_id: 本次拟入队的 task id。首次调用时写入，供后续重试返回。
        user_id: a10——幂等键按用户命名空间隔离，必填（防跨用户撞键穿透）。
        fail_closed: A8——高危设备写操作（remedial execute）传 True：
            Redis 不可用/异常时抛 `IdempotencyUnavailableError`（路由转 503），
            而非放行。降级发生在**占位之前**，幂等键不被消费，Redis 恢复后
            重试可正常占位。非高危调用方（agentic 诊断等）保持默认 False
            的 fail-open，不因 Redis 故障阻断。

    Returns:
        (是否首次占位, 已存在的 task_id)。
        首次占位 → (True, None)，调用方应入队；
        重复请求 → (False, 首次 task_id)，调用方应直接返回该 task_id 而不入队。

    Raises:
        IdempotencyUnavailableError: fail_closed=True 且 Redis 不可用/异常。
    """
    try:
        r = _get_redis()
        if r is None:
            if fail_closed:
                raise IdempotencyUnavailableError(
                    "Redis 不可用，高危操作的重复下发防护失效，已拒绝执行")
            logger.warning(
                "ai.idem.redis_unavailable key=%s 降级放行（重复下发防护失效）", key)
            return True, None
        rkey = _scoped_key(key, user_id)
        if r.set(rkey, task_id, nx=True, ex=_TTL):
            return True, None
        existing = r.get(rkey)
        if existing is None:
            logger.warning("ai.idem.race key=%s 占位失败但键不存在，放行", key)
            return True, None
        return False, existing
    except IdempotencyUnavailableError:
        raise  # fail-closed 信号，不得被下方兜底吞掉
    except Exception as e:  # noqa: BLE001
        if fail_closed:
            raise IdempotencyUnavailableError(
                f"Redis 异常，高危操作拒绝执行: {e}") from e
        logger.warning("ai.idem.claim_failed key=%s: %s 降级放行", key, e)
        return True, None


def get_claimed_task_id(key: str, user_id: int) -> Optional[str]:
    """读取该幂等键已占位的 task_id，不存在返回 None。

    Args:
        key: 幂等键。
        user_id: a10——与 try_claim 同一用户命名空间，必填。

    Returns:
        首次入队的 task id，或 None（未占位 / Redis 不可用）。
    """
    try:
        r = _get_redis()
        if r is None:
            return None
        return r.get(_scoped_key(key, user_id))
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.idem.read_failed key=%s: %s", key, e)
        return None
