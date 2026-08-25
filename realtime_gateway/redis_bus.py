# -*- coding: utf-8 -*-
"""
Redis 订阅总线 — 网关核心模块

职责：
1. 订阅 Redis Pub/Sub（sw:{device_id} 和 events:global）
2. 为每条事件分配全局唯一 seq（单进程持有，天然全局唯一）
3. 维护每台设备的环形缓冲区（断线重放）
4. 将事件分发到本地 asyncio.Queue（fan-out 给 SSE 连接）

线程安全说明：
  本模块运行在 uvicorn 单进程 asyncio 事件循环中，
  所有状态（_device_seqs / _device_rings / _subscribers）都是单线程访问，
  无需加锁。这也是网关必须单进程运行的根本原因。
"""
import asyncio
import collections
import json
import logging
import time

import redis.asyncio as aioredis

from . import config

logger = logging.getLogger(__name__)


_device_seqs: dict[int, int] = {}

_device_rings: dict[int, collections.deque] = {}

_subscribers: dict[int, list[asyncio.Queue]] = {}

_global_subscribers: list[tuple[asyncio.Queue, int | None]] = []

_redis: aioredis.Redis | None = None


def _next_seq(device_id: int) -> int:
    """获取设备下一个序列号（单调递增，单进程保证全局唯一）"""
    seq = _device_seqs.get(device_id, 0) + 1
    _device_seqs[device_id] = seq
    return seq


def _ring_store(device_id: int, event_dict: dict) -> None:
    """将事件存入设备环形缓冲区"""
    if device_id not in _device_rings:
        _device_rings[device_id] = collections.deque(maxlen=config.RING_BUFFER_SIZE)
    _device_rings[device_id].append(event_dict)


def get_events_since(device_id: int, since_seq: int) -> list[dict]:
    """从环形缓冲区取出 seq > since_seq 的事件（供断线重放）"""
    ring = _device_rings.get(device_id, collections.deque())
    return [e for e in ring if e.get("seq", 0) > since_seq]


def subscribe(device_id: int) -> asyncio.Queue:
    """注册一个设备级订阅者，返回其专属 asyncio.Queue"""
    q: asyncio.Queue = asyncio.Queue(maxsize=config.CLIENT_QUEUE_SIZE)
    _subscribers.setdefault(device_id, []).append(q)
    count = len(_subscribers[device_id])
    logger.debug("SSE 客户端订阅 device=%d，当前订阅数=%d", device_id, count)
    return q


def unsubscribe(device_id: int, q: asyncio.Queue) -> None:
    """注销设备级订阅者"""
    subs = _subscribers.get(device_id, [])
    try:
        subs.remove(q)
    except ValueError:
        pass
    if not subs:
        _subscribers.pop(device_id, None)
    logger.debug("SSE 客户端取消订阅 device=%d", device_id)


def subscribe_global(user_id: int | None = None) -> asyncio.Queue:
    """注册一个全局事件订阅者。

    Args:
        user_id: 订阅该连接的用户 id；None 表示不绑定特定用户
                 （只能收到 target_user_ids 缺失/为 None 的全局广播）。
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=config.CLIENT_QUEUE_SIZE)
    _global_subscribers.append((q, user_id))
    count = len(_global_subscribers)
    logger.debug("SSE 全局客户端订阅 user_id=%s，当前订阅数=%d", user_id, count)
    return q


def unsubscribe_global(q: asyncio.Queue) -> None:
    """注销全局事件订阅者（按队列对象身份移除）"""
    for i, (item_q, _) in enumerate(_global_subscribers):
        if item_q is q:
            _global_subscribers.pop(i)
            break
    logger.debug("SSE 全局客户端取消订阅，剩余订阅数=%d", len(_global_subscribers))



async def get_redis() -> aioredis.Redis:
    """获取 Redis 异步客户端（懒加载单例）"""
    global _redis
    if _redis is not None:
        return _redis
    _redis = aioredis.Redis.from_url(
        config.REDIS_URL,
        decode_responses=True,
        socket_timeout=None,          # PubSub 长连接不能有读取超时
        socket_connect_timeout=5,     # 连接超时 5s
    )
    await _redis.ping()
    logger.info("网关 Redis 已连接: %s", config.REDIS_URL)
    return _redis



def _handle_device_event(device_id: int, raw_data: str) -> None:
    """处理交换机级事件：分配 seq → 存环形缓冲区 → fan-out"""
    try:
        event_dict = json.loads(raw_data)
    except json.JSONDecodeError:
        logger.warning("无效 JSON 事件，device=%d", device_id)
        return

    seq = _next_seq(device_id)
    event_dict["seq"] = seq

    _ring_store(device_id, event_dict)

    payload = json.dumps(event_dict, ensure_ascii=False)

    queues = list(_subscribers.get(device_id, []))
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning(
                "SSE 客户端队列已满，丢弃事件 device=%d seq=%d",
                device_id, seq,
            )


def _handle_global_event(raw_data: str) -> None:
    """处理全局事件：按 target_user_ids 过滤后 fan-out。

    target_user_ids 为 None 或字段缺失时，视为全局广播，分发给所有订阅者。
    否则只分发给绑定了目标用户 id 的订阅连接。
    """
    try:
        event = json.loads(raw_data)
    except json.JSONDecodeError:
        logger.warning("无效 JSON 全局事件，丢弃")
        return

    targets = event.get("target_user_ids")
    for q, uid in list(_global_subscribers):
        if targets is None or (uid is not None and uid in targets):
            try:
                q.put_nowait(raw_data)
            except asyncio.QueueFull:
                logger.warning("SSE 全局客户端队列已满，丢弃事件")



async def start_subscriber() -> None:
    """启动 Redis 订阅主循环（在 asyncio 事件循环中运行）。

    使用 psubscribe("sw:*") 模式订阅所有交换机事件，
    同时 subscribe 全局 channel。
    断线自动重连（5s 间隔）。
    """
    while True:
        try:
            r = await get_redis()
            pubsub = r.pubsub()
            await pubsub.psubscribe("sw:*")
            await pubsub.subscribe(config.GLOBAL_CHANNEL)
            logger.info("网关 Redis 订阅已启动")

            async for msg in pubsub.listen():
                if msg["type"] not in ("message", "pmessage"):
                    continue

                data = msg["data"]
                if isinstance(data, bytes):
                    data = data.decode()

                channel = msg.get("channel", "")
                if isinstance(channel, bytes):
                    channel = channel.decode()

                if channel == config.GLOBAL_CHANNEL:
                    _handle_global_event(data)
                else:
                    try:
                        device_id = int(channel.split(":", 1)[1])
                    except (IndexError, ValueError):
                        continue
                    _handle_device_event(device_id, data)

        except asyncio.CancelledError:
            logger.info("网关 Redis 订阅被取消，正在关闭")
            break
        except Exception as exc:
            logger.warning("网关 Redis 订阅异常，5s 后重连: %s", exc)
            await asyncio.sleep(5)
