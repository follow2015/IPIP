# -*- coding: utf-8 -*-
"""
Redis 订阅总线 — 网关核心模块

职责：
1. 订阅 Redis Pub/Sub（sw:{device_id} 和 events:global）
2. 将事件分发到本地 asyncio.Queue（fan-out 给本副本的 SSE 连接）
3. 断线重放：get_events_since 从 Redis 共享 ring 读取（ring 由发布侧
   app/services/switch_events.py 通过 Lua LPUSH+LTRIM+EXPIRE 维护）

seq 归属说明（多副本硬性前提）：
  seq 由发布侧（Flask switch_events.py）通过 Redis INCR 分配并写入 payload，
  网关只透传、绝不重新分配——若网关分配，多副本会各自 INCR 导致 seq 重复。
  ring 也在 Redis 共享，断线重连路由到任一副本都能重放。

线程安全说明：
  本模块运行在 uvicorn 单进程 asyncio 事件循环中，
  本地订阅者状态（_subscribers / _global_subscribers）都是单线程访问，
  无需加锁。seq/ring 已外移至 Redis，本模块无跨副本共享的进程内状态，
  支持多副本水平扩容（每副本独立订阅 Pub/Sub，Redis 自然广播）。
"""
import asyncio
import json
import logging

import redis.asyncio as aioredis

from . import config

logger = logging.getLogger(__name__)


_subscribers: dict[int, list[asyncio.Queue]] = {}

_global_subscribers: list[tuple[asyncio.Queue, int | None]] = []

_redis: aioredis.Redis | None = None


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



async def get_events_since(device_id: int, since_seq: int) -> list[dict]:
    """从 Redis 共享 ring 取出 seq > since_seq 的事件（供断线重放）。

    ring 由发布侧 switch_events.py 维护（LPUSH 头插，LRANGE 返回新→旧），
    这里统一按 seq 升序返回，与迁移前进程内 deque（旧→新）的语义一致。

    Redis 异常时返回空列表（重放是 best-effort，不阻断连接建立）。
    """
    try:
        r = await get_redis()
        raw_events = await r.lrange(config.RING_KEY_FMT.format(device_id=device_id), 0, -1)
    except Exception as exc:
        logger.warning("读取 ring 失败 device=%d: %s", device_id, exc)
        return []

    events: list[dict] = []
    for raw in raw_events:
        try:
            e = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("ring 内存在无效 JSON 事件，跳过 device=%d", device_id)
            continue
        if e.get("seq", 0) > since_seq:
            events.append(e)
    events.sort(key=lambda e: e.get("seq", 0))
    return events



def _handle_device_event(device_id: int, raw_data: str) -> None:
    """处理交换机级事件：透传 seq（发布侧已分配）→ fan-out 到本地订阅者。

    缺 seq 的兼容处理（发布方未迁移的部署窗口期）：注入 seq=0，
    保证前端 DeviceEventBus 的 Math.max 游标不被 undefined 污染成 NaN。
    """
    try:
        event_dict = json.loads(raw_data)
    except json.JSONDecodeError:
        logger.warning("无效 JSON 事件，device=%d", device_id)
        return

    if "seq" not in event_dict:
        logger.warning(
            "事件缺少 seq（发布方未迁移？），device=%d event_id=%s",
            device_id, event_dict.get("event_id"),
        )
        event_dict["seq"] = 0
        raw_data = json.dumps(event_dict, ensure_ascii=False)

    queues = list(_subscribers.get(device_id, []))
    for q in queues:
        try:
            q.put_nowait(raw_data)
        except asyncio.QueueFull:
            logger.warning(
                "SSE 客户端队列已满，丢弃事件 device=%d seq=%s",
                device_id, event_dict.get("seq"),
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
    断线自动重连（5s 间隔）。多副本部署时每个副本独立运行本循环，
    Redis Pub/Sub 自然广播到所有副本。
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
