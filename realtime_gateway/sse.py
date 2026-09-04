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
import json
import logging
import time

from . import config
from . import redis_bus

logger = logging.getLogger(__name__)


async def device_event_stream(
    device_id: int, since_seq: int | None = 0
) -> asyncio.AsyncGenerator[str, None]:
    """SSE 事件流生成器（交换机级别，含断线重放）

    连接建立时**先建立订阅**，再推送 since_seq 之后的历史事件（从 Redis 共享
    ring 读取），最后进入实时监听。先订阅可保证「重放」与「实时」之间没有空隙。

    Args:
        device_id:  交换机 device_id（devices.id）
        since_seq:  客户端最后收到的序列号。**None 表示首次连接，跳过历史重放**
                    （s12：此前按 0 重放整个 ring，最多 200 条陈旧事件，页面每次
                    刷新都白白推一遍）；显式传 0 表示从 ring 头全量补发。

    Yields:
        str: SSE 格式的文本帧
    """
    q = redis_bus.subscribe(device_id)

    try:
        already: list[str] = []
        while True:
            try:
                already.append(q.get_nowait())
            except asyncio.QueueEmpty:
                break

        seen_seq = set()
        for payload in already:
            try:
                seen_seq.add(json.loads(payload).get("seq"))
            except (json.JSONDecodeError, AttributeError):
                pass

        if since_seq is not None:
            for event_dict in await redis_bus.get_events_since(device_id, since_seq):
                if event_dict.get("seq") in seen_seq:
                    continue  # 订阅后已推送过，避免重复投递
                seen_seq.add(event_dict.get("seq"))
                yield f"data: {json.dumps(event_dict, ensure_ascii=False)}\n\n"

        for payload in already:
            yield f"data: {payload}\n\n"

        last_active = time.monotonic()
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=config.KEEPALIVE_INTERVAL)
                last_active = time.monotonic()
                if seen_seq:
                    try:
                        seq = json.loads(payload).get("seq")
                    except (json.JSONDecodeError, AttributeError):
                        seq = None
                    if seq is not None and seq in seen_seq:
                        continue
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
