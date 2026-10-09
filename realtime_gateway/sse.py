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
from collections.abc import AsyncGenerator

from . import config
from . import redis_bus

logger = logging.getLogger(__name__)


def _frame(payload: str, seq) -> str:
    """组装 SSE 帧；seq 已知时一并输出 `id:` 行（M1 闭环）。

    `id:` 是标准 SSE 字段：浏览器 EventSource 会记住最后收到的 id，并在
    **自动重连**时通过 `Last-Event-ID` 请求头带回。这是断线重放能生效的关键——
    自动重连复用建连时的固定 URL，查询参数里的 `since_seq` 不会更新，只有
    `Last-Event-ID` 会随每条新事件刷新（网关侧见 `main._parse_since_seq`）。

    Args:
        payload: 已序列化的事件 JSON 字符串。
        seq: 发布侧分配的序列号；None 或缺 seq 的事件退化为不带 id 行。

    Returns:
        SSE 文本帧。
    """
    if seq is None:
        return f"data: {payload}\n\n"
    return f"id: {seq}\ndata: {payload}\n\n"


async def device_event_stream(
    device_id: int, since_seq: int | None = 0
) -> AsyncGenerator[str, None]:
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
        already: list[tuple] = []
        while True:
            try:
                already.append(q.get_nowait())
            except asyncio.QueueEmpty:
                break

        seen_seq = {seq for seq, _ in already if seq is not None}

        if since_seq is not None:
            for event_dict in await redis_bus.get_events_since(device_id, since_seq):
                if event_dict.get("seq") in seen_seq:
                    continue  # 订阅后已推送过，避免重复投递
                seen_seq.add(event_dict.get("seq"))
                yield _frame(json.dumps(event_dict, ensure_ascii=False),
                             event_dict.get("seq"))

        for seq, payload in already:
            yield _frame(payload, seq)

        last_active = time.monotonic()
        while True:
            try:
                seq, payload = await asyncio.wait_for(
                    q.get(), timeout=config.KEEPALIVE_INTERVAL)
                last_active = time.monotonic()
                if seen_seq and seq is not None and seq in seen_seq:
                    continue
                yield _frame(payload, seq)
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


async def global_event_stream(user_id: int | None = None,
                              since_seq: int | None = None,
                              ) -> AsyncGenerator[str, None]:
    """SSE 全局事件流生成器（M1：含断线重放）。

    不绑定特定交换机，用于接收机房扫描完成等全局事件。

    结构与 `device_event_stream` 完全同构（先订阅 → 排空 → 重放 → 补发 →
    实时去重）：修复前全局流没有 ring 也没有 seq，断线期间的事件永久丢失。

    Args:
        user_id: 当前连接用户 id；传入后网关按 target_user_ids 过滤 fan-out
            （**重放路径同样过滤**，见 `redis_bus.get_global_events_since`）。
        since_seq: 客户端最后收到的全局序列号。**None 表示首次连接，跳过历史
            重放**（与设备流 s12 同款语义：否则每次刷新页面都要白推一遍历史）；
            显式传 0 表示从 ring 头全量补发。

    Yields:
        str: SSE 格式的文本帧
    """
    q = redis_bus.subscribe_global(user_id=user_id)

    try:
        already: list[tuple] = []
        while True:
            try:
                already.append(q.get_nowait())
            except asyncio.QueueEmpty:
                break

        seen_seq = {seq for seq, _ in already if seq is not None}

        if since_seq is not None:
            for event_dict in await redis_bus.get_global_events_since(
                since_seq, user_id=user_id,
            ):
                if event_dict.get("seq") in seen_seq:
                    continue  # 订阅后已推送过，避免重复投递
                seen_seq.add(event_dict.get("seq"))
                yield _frame(json.dumps(event_dict, ensure_ascii=False),
                             event_dict.get("seq"))

        for seq, payload in already:
            yield _frame(payload, seq)

        last_active = time.monotonic()
        while True:
            try:
                seq, payload = await asyncio.wait_for(
                    q.get(), timeout=config.KEEPALIVE_INTERVAL)
                last_active = time.monotonic()
                if seen_seq and seq is not None and seq in seen_seq:
                    continue
                yield _frame(payload, seq)
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
