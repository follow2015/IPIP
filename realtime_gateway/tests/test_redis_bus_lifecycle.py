# -*- coding: utf-8 -*-
"""网关生命周期测试（S1 降级启动重试 + S3 pubsub 连接释放）。

S1：Redis 在网关启动时不可用，也必须启动订阅任务——start_subscriber 内部
    是 while 循环，靠循环内 get_redis() 重试即可在 Redis 恢复后自动订阅。
    修复前降级分支不启动任务，SSE 永久不可用直至重启进程（与 lifespan
    注释"等 Redis 恢复后订阅会自动重连"的承诺相悖）。
S3：订阅循环的重连与取消两条路径都必须关闭旧 pubsub，否则每次重连泄漏
    一条 Pub/Sub 专用连接，Redis 抖动时连接耗尽。

不连接真实 Redis。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from realtime_gateway import redis_bus



def test_lifespan_starts_subscriber_even_when_redis_unavailable():
    """S1：启动期 Redis 不可用，订阅任务仍必须启动（靠循环重试自动恢复）。"""
    from realtime_gateway.main import lifespan

    calls = []

    async def flaky_get_redis():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("redis down")
        return MagicMock()

    with patch.object(redis_bus, "get_redis", flaky_get_redis), \
            patch.object(redis_bus, "start_subscriber", new=AsyncMock()) as sub:

        async def run() -> None:
            async with lifespan(None):
                pass

        asyncio.run(run())

    assert sub.called, "降级模式也必须启动订阅任务，否则 Redis 恢复后不会自动订阅"


def test_get_redis_not_cached_on_ping_failure():
    """S1 配套：ping 失败不得缓存坏客户端，否则重试永远拿到同一个坏连接。

    修复前 from_url 先赋值给全局再 ping，ping 失败时 _redis 已指向坏客户端，
    后续调用直接返回它——start_subscriber 的重试形同虚设。
    """
    redis_bus._redis = None

    good = MagicMock()
    good.ping = AsyncMock(return_value=True)

    bad = MagicMock()
    bad.ping = AsyncMock(side_effect=RuntimeError("down"))

    with patch.object(redis_bus.aioredis.Redis, "from_url",
                      side_effect=[bad, good]) as from_url:
        with pytest.raises(RuntimeError):
            asyncio.run(redis_bus.get_redis())
        client = asyncio.run(redis_bus.get_redis())

    assert from_url.call_count == 2, "ping 失败的客户端不得被缓存"
    assert client is good

    redis_bus._redis = None  # 还原全局，避免污染其他用例



class _FakePubSub:
    """记录关闭调用的 pubsub：listen 抛异常以触发重连/取消分支。"""

    def __init__(self, closed: list, error: BaseException):
        self._closed = closed
        self._error = error

    async def psubscribe(self, *args, **kwargs) -> None:
        return None

    async def subscribe(self, *args, **kwargs) -> None:
        return None

    async def listen(self):
        raise self._error
        yield  # pragma: no cover（仅使本函数成为 async generator）

    async def aclose(self) -> None:
        self._closed.append("aclose")


def _run_subscriber(errors: list[BaseException], closed: list) -> list:
    """驱动 start_subscriber 循环若干次后以 CancelledError 终止。

    返回循环中创建的 pubsub 列表——断言口径是"每个创建的 pubsub 都被关闭"，
    而不是固定条数（异常重连一次 = 旧 pubsub 关闭 + 新 pubsub 建起，
    终止时新 pubsub 也要关闭，故条数随循环次数变化）。
    """
    pubsubs = []

    async def fake_get_redis():
        r = MagicMock()
        err = errors.pop(0) if errors else asyncio.CancelledError()
        pubsub = _FakePubSub(closed, err)
        pubsubs.append(pubsub)
        r.pubsub.return_value = pubsub
        return r

    with patch.object(redis_bus, "get_redis", fake_get_redis), \
            patch.object(redis_bus.asyncio, "sleep", new=AsyncMock()):
        asyncio.run(redis_bus.start_subscriber())

    return pubsubs


def test_pubsub_closed_on_reconnect():
    """S3：订阅异常重连前必须关闭旧 pubsub（否则每次重连泄漏一条连接）。"""
    closed: list[str] = []
    pubsubs = _run_subscriber([RuntimeError("boom")], closed)

    assert len(pubsubs) == 2, "一次异常应触发重连：旧 pubsub + 新 pubsub"
    assert len(closed) == len(pubsubs), (
        "每个创建的 pubsub 都必须关闭：重连前 aclose 旧的，终止时 aclose 当前的"
    )


def test_pubsub_closed_on_cancel():
    """S3：任务被取消（优雅停机）时同样要关闭 pubsub。"""
    closed: list[str] = []
    pubsubs = _run_subscriber([asyncio.CancelledError()], closed)

    assert len(pubsubs) == 1
    assert len(closed) == len(pubsubs), "优雅停机时不得遗留 pubsub 连接"
