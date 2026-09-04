# -*- coding: utf-8 -*-
"""
AI 任务进度 SSE 流（P0-7 迁移）

原实现：Flask 同步生成器（`app/services/ai/rag_ingest_async.py:get_progress`）
以 0.5s 轮询 task_state，上限 3600s，跑在 gunicorn **sync** worker（部署配置
`--timeout 120`）上——任何长任务必然触发 worker 心跳超时被强杀，并连带杀死该
worker 上所有在途请求。

本模块把进度流迁入 ASGI 网关：asyncio 协程轮询 Redis 中的任务状态
（与 Flask `app/services/ai/task_state.py` 共享同一份存储，键前缀必须一致），
单连接成本极低，无 sync worker 心跳问题。

SSE 帧格式与 Flask 版逐字段对齐（前端 `TaskProgressEvent` 契约不变）：
- 进度帧：``data: {"type":"progress","status":...,"progress":...,"total":...}``
- 终止帧：``data: {"type":"done","result":...}``
- 异常帧：``data: {"type":"error","message":...}``
- 心跳：``: keepalive``（注释行，前端解析器忽略）

归属校验（fail-closed，对齐 Flask `_check_task_ownership` 的第 1/3 条）：
- 任务状态缺失或未携带 user_id → 拒绝（旧任务/降级路径写入的状态不放行）；
- `user_id != ticket 用户` → 拒绝。
Flask 端点保留 `ai:admin` 跨用户排障能力（网关无法查库校验权限码），
生产部署的常规订阅走网关（owner-only）。
"""
import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from . import redis_bus

logger = logging.getLogger(__name__)

AI_TASK_KEY_PREFIX = "ai:task:"

POLL_INTERVAL = 1.0        # 秒；状态轮询间隔（状态变更是粗粒度的，1s 足够）
HEARTBEAT_INTERVAL = 15.0  # 秒；空闲心跳，防代理/浏览器断连
STREAM_TIMEOUT = 3600.0    # 秒；整条流上限（对齐 Flask 版 1h）


def _sse_data(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _extract_fields(state: dict) -> dict:
    """L1 对齐：显式列举下发字段，不透传 user_id 等内部字段。"""
    return {
        "type": "progress",
        "status": state.get("status"),
        "progress": state.get("progress", 0),
        "total": state.get("total", 0),
    }


async def ai_task_event_stream(task_id: str, user_id: int | None) -> AsyncGenerator[str, None]:
    """AI 任务进度 SSE 流（网关版，轮询共享 Redis 状态）。

    Args:
        task_id: Celery task id（Flask 侧 task_state 的键后缀）
        user_id: ticket/JWT 中的用户 id（归属校验）

    Yields:
        str: SSE 文本帧
    """
    r = await redis_bus.get_redis()
    key = f"{AI_TASK_KEY_PREFIX}{task_id}"

    try:
        raw = await r.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI 任务状态读取失败 task_id=%s: %s", task_id, exc)
        raw = None
    state = _parse(raw)
    if state is None:
        yield _sse_data({"type": "error", "message": "task not found"})
        return
    owner_id = state.get("user_id")
    if owner_id is None or str(owner_id) != str(user_id):
        logger.info("AI 任务进度订阅被拒绝（归属不符） task_id=%s owner=%s user=%s",
                    task_id, owner_id, user_id)
        yield _sse_data({"type": "error", "message": "无权访问该任务"})
        return

    start = time.monotonic()
    last_sent: str | None = None
    last_activity = start
    while True:
        if state is not None:
            frame = _sse_data(_extract_fields(state))
            if frame != last_sent:
                last_sent = frame
                last_activity = time.monotonic()
                yield frame
            if state.get("status") in ("done", "error"):
                yield _sse_data({"type": "done", "result": state.get("result")})
                return
        now = time.monotonic()
        if now - start > STREAM_TIMEOUT:
            yield _sse_data({"type": "error", "message": "progress timeout"})
            return
        if now - last_activity >= HEARTBEAT_INTERVAL:
            yield ": keepalive\n\n"
            last_activity = now
        await asyncio.sleep(POLL_INTERVAL)
        try:
            state = _parse(await r.get(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI 任务状态轮询失败 task_id=%s: %s", task_id, exc)
            state = None


def _parse(raw) -> dict | None:
    """解析 Redis 中的任务状态 JSON；缺失/损坏返回 None。"""
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        state = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return state if isinstance(state, dict) else None
