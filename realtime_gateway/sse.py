# -*- coding: utf-8 -*-
"""
SSE 帧封装 — asyncio.Queue → SSE 文本帧

将 redis_bus 分发到 asyncio.Queue 中的事件取出，
格式化为 SSE 协议文本帧（data: ...\n\n），
同时处理心跳和空闲超时断开。

与旧版 Flask 侧 switch_events.py 的 event_stream / global_event_stream 对齐：
- KEEPALIVE_INTERVAL = 25s（防止代理/浏览器断开空闲连接）
- MAX_IDLE_SECONDS = 300s（5分钟无数据主动断开，防止客户端无声断连导致 Queue 泄漏）
"""
import asyncio
import logging
import time

from . import config
from . import redis_bus

logger = logging.getLogger(__name__)


async def device_event_stream(device_id: int, since_seq: int = 0) -> asyncio.AsyncGenerator[str, None]:
    """SSE 事件流生成器（交换机级别，含断线重放）

    连接建立时先推送 since_seq 之后的历史事件，再进入实时监听。

    Args:
        device_id:  交换机 device_id（devices.id）
        since_seq:  客户端最后收到的序列号（0 表示首次连接）

    Yields:
        str: SSE 格式的文本帧
    """
    missed = redis_bus.get_events_since(device_id, since_seq)
    for event_dict in missed:
        import json
        yield f"data: {json.dumps(event_dict, ensure_ascii=False)}\n\n"

    q = redis_bus.subscribe(device_id)

    try:
        last_active = time.monotonic()
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=config.KEEPALIVE_INTERVAL)
                last_active = time.monotonic()
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                idle = time.monotonic() - last_active
                if idle > config.MAX_IDLE_SECONDS:
                    logger.debug("SSE 设备连接空闲超时断开 device=%d", device_id)
                    break
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        redis_bus.unsubscribe(device_id, q)


async def global_event_stream(user_id: int | None = None) -> asyncio.AsyncGenerator[str, None]:
    """SSE 全局事件流生成器。

    不绑定特定交换机，用于接收机房扫描完成等全局事件。

    Args:
        user_id: 当前连接用户 id；传入后网关按 target_user_ids 过滤 fan-out。

    Yields:
        str: SSE 格式的文本帧
    """
    q = redis_bus.subscribe_global(user_id=user_id)

    try:
        last_active = time.monotonic()
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=config.KEEPALIVE_INTERVAL)
                last_active = time.monotonic()
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                idle = time.monotonic() - last_active
                if idle > config.MAX_IDLE_SECONDS:
                    logger.debug("SSE 全局连接空闲超时断开")
                    break
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        redis_bus.unsubscribe_global(q)
