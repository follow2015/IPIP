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
import time

import redis.asyncio as aioredis

from . import config

logger = logging.getLogger(__name__)


_subscribers: dict[int, list[asyncio.Queue]] = {}

_global_subscribers: list[tuple[asyncio.Queue, int | None]] = []

_redis_subscribed: set[int] = set()
_pubsub = None

_DROP_LOG_INTERVAL = 30.0
_drop_stats: dict[str, int] = {"device": 0, "global": 0}
_last_drop_log = 0.0

_redis: aioredis.Redis | None = None


def subscribe(device_id: int) -> asyncio.Queue:
    """注册一个设备级订阅者，返回其专属 asyncio.Queue

    s13：首个本地订阅者出现时才在 Redis 层订阅 sw:{device_id} 频道
    （此前 psubscribe("sw:*") 使每个副本无条件接收全部设备事件并逐条
    JSON 解析，与本地是否存在订阅者无关）。
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=config.CLIENT_QUEUE_SIZE)
    _subscribers.setdefault(device_id, []).append(q)
    count = len(_subscribers[device_id])
    logger.info("SSE 客户端订阅 device=%d，当前订阅数=%d", device_id, count)
    if count == 1:
        _schedule_redis_subscribe(device_id)
    return q


def unsubscribe(device_id: int, q: asyncio.Queue) -> None:
    """注销设备级订阅者

    s13：最后一个本地订阅者离开时，退订 Redis 层的该设备频道。
    """
    subs = _subscribers.get(device_id, [])
    try:
        subs.remove(q)
    except ValueError:
        pass
    if not subs:
        _subscribers.pop(device_id, None)
    logger.info("SSE 客户端取消订阅 device=%d", device_id)
    if device_id not in _subscribers:
        _schedule_redis_unsubscribe(device_id)


def subscribe_global(user_id: int | None = None) -> asyncio.Queue:
    """注册一个全局事件订阅者。

    Args:
        user_id: 订阅该连接的用户 id；None 表示不绑定特定用户
                 （只能收到 target_user_ids 缺失/为 None 的全局广播）。
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=config.CLIENT_QUEUE_SIZE)
    _global_subscribers.append((q, user_id))
    count = len(_global_subscribers)
    logger.info("SSE 全局客户端订阅 user_id=%s，当前订阅数=%d", user_id, count)
    return q


def unsubscribe_global(q: asyncio.Queue) -> None:
    """注销全局事件订阅者（按队列对象身份移除）"""
    for i, (item_q, _) in enumerate(_global_subscribers):
        if item_q is q:
            _global_subscribers.pop(i)
            break
    logger.info("SSE 全局客户端取消订阅，剩余订阅数=%d", len(_global_subscribers))



def _schedule_redis_subscribe(device_id: int) -> None:
    """记录订阅意图并（在订阅循环就绪时）异步执行 Redis 层订阅。"""
    if device_id in _redis_subscribed:
        return
    _redis_subscribed.add(device_id)
    _dispatch_redis_op(_ensure_redis_subscribed(device_id))


def _schedule_redis_unsubscribe(device_id: int) -> None:
    """最后一个本地订阅者离开 → 退订 Redis 层频道。

    意图同步清除（无事件循环时也生效）；Redis 层退订异步执行。
    """
    if device_id not in _redis_subscribed:
        return
    _redis_subscribed.discard(device_id)
    _dispatch_redis_op(_redis_unsubscribe_now(device_id))


def _dispatch_redis_op(coro) -> None:
    """在运行中的事件循环里排空 coro；无循环（如同步单测）时静默丢弃。"""
    try:
        asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        coro.close()  # 重连后 start_subscriber 会按 _redis_subscribed 统一补订


async def _ensure_redis_subscribed(device_id: int) -> None:
    """确保 Redis 层已订阅 sw:{device_id}（幂等，重复订阅为 Redis no-op）。"""
    if _pubsub is None:
        return  # 订阅循环未就绪：意图已记录，重连后 start_subscriber 统一补订
    try:
        await _pubsub.subscribe(f"sw:{device_id}")
    except Exception as exc:
        logger.warning("Redis 层订阅设备频道失败 device=%d: %s", device_id, exc)
        return
    _redis_subscribed.add(device_id)
    logger.info("Redis 层订阅设备频道 device=%d", device_id)


async def _redis_unsubscribe_now(device_id: int) -> None:
    """Redis 层退订 sw:{device_id}（意图已由 _schedule_redis_unsubscribe 清除）。"""
    if _pubsub is None:
        return
    try:
        await _pubsub.unsubscribe(f"sw:{device_id}")
        logger.info("Redis 层退订设备频道 device=%d", device_id)
    except Exception as exc:
        logger.warning("Redis 层退订设备频道失败 device=%d: %s", device_id, exc)



def _record_drop(kind: str, detail: str) -> None:
    """计数并在聚合窗口（30s）到期时输出一条汇总 WARNING。"""
    global _last_drop_log
    _drop_stats[kind] = _drop_stats.get(kind, 0) + 1
    now = time.monotonic()
    if now - _last_drop_log < _DROP_LOG_INTERVAL:
        return
    _last_drop_log = now
    logger.warning(
        "SSE 队列满丢弃事件（%ds 聚合）: %s %s",
        int(_DROP_LOG_INTERVAL), _drop_stats, detail,
    )
    for k in _drop_stats:
        _drop_stats[k] = 0



async def close_redis() -> None:
    """关闭 Redis 客户端（lifespan 退出时调用，优雅停机不遗留连接）。"""
    global _redis
    if _redis is None:
        return
    client, _redis = _redis, None
    try:
        await client.aclose()
    except Exception as exc:
        logger.warning("关闭 Redis 客户端失败: %s", exc)


async def get_redis() -> aioredis.Redis:
    """获取 Redis 异步客户端（懒加载单例，ping 成功才缓存）。

    S1 配套：连接必须先 ping 通过再赋给全局。原实现先赋值再 ping，
    ping 失败时 _redis 已指向坏客户端并被后续调用直接复用——start_subscriber
    的重试循环会永远拿到同一个坏连接，Redis 恢复后也无法自动订阅。
    """
    global _redis
    if _redis is not None:
        return _redis
    client = aioredis.Redis.from_url(
        config.REDIS_URL,
        decode_responses=True,
        socket_timeout=None,          # PubSub 长连接不能有读取超时
        socket_connect_timeout=5,     # 连接超时 5s
    )
    await client.ping()  # 失败不缓存：下次调用重新建连
    _redis = client
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
            _record_drop("device", f"device={device_id} seq={event_dict.get('seq')}")


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
                _record_drop("global", "global")



async def start_subscriber() -> None:
    """启动 Redis 订阅主循环（在 asyncio 事件循环中运行）。

    s13：按需 subscribe 本地实际有订阅者的 sw:{device_id} 频道（替代
    psubscribe("sw:*")——后者使每个副本无条件接收全部设备事件并逐条 JSON
    解析，规模上来后纯属浪费），同时订阅全局 channel。
    断线自动重连（5s 间隔），重连后按 _redis_subscribed 统一补订。
    多副本部署时每个副本独立运行本循环，Redis Pub/Sub 自然广播到所有副本。
    """
    global _pubsub
    while True:
        pubsub = None
        try:
            r = await get_redis()
            pubsub = r.pubsub()
            await pubsub.subscribe(config.GLOBAL_CHANNEL)
            for device_id in list(_redis_subscribed):
                await pubsub.subscribe(f"sw:{device_id}")
            _pubsub = pubsub
            logger.info(
                "网关 Redis 订阅已启动（设备频道×%d）", len(_redis_subscribed)
            )

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
        finally:
            _pubsub = None
            if pubsub is not None:
                try:
                    await pubsub.aclose()
                except Exception as exc:
                    logger.warning("关闭 pubsub 失败: %s", exc)
