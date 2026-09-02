# -*- coding: utf-8 -*-
"""网关侧测试：seq 透传 + Redis 共享 ring 重放（方案 A 落地验证）。

覆盖：
- _handle_device_event 透传发布侧 seq（绝不重新分配）
- 缺 seq 兼容：注入 0，防前端 Math.max 游标被 undefined 污染成 NaN
- get_events_since 从 Redis ring 读取：seq 过滤 + 升序返回
- Redis 异常时重放降级为空列表（best-effort，不阻断连接）

不连接真实 Redis。
"""
import asyncio
import json

import pytest

from realtime_gateway import redis_bus


@pytest.fixture
def clean_subscribers():
    redis_bus._subscribers = {}
    redis_bus._global_subscribers = []
    yield
    redis_bus._subscribers = {}
    redis_bus._global_subscribers = []



def test_device_event_passthrough_seq(clean_subscribers):
    """带 seq 的事件原样透传，网关绝不重新分配。"""
    q = redis_bus.subscribe(7)
    raw = json.dumps({"event_id": "e1", "device_id": 7, "op_type": "port_update", "seq": 41})
    redis_bus._handle_device_event(7, raw)
    assert q.get_nowait() == raw  # payload 逐字节一致


def test_device_event_missing_seq_injects_zero(clean_subscribers):
    """缺 seq（发布方未迁移窗口期）注入 0：不影响前端 Math.max 游标。"""
    q = redis_bus.subscribe(7)
    redis_bus._handle_device_event(7, json.dumps({"event_id": "e2", "op_type": "x"}))
    data = json.loads(q.get_nowait())
    assert data["seq"] == 0


def test_device_event_invalid_json_no_crash(clean_subscribers):
    """无效 JSON 不崩溃、不 fan-out。"""
    q = redis_bus.subscribe(7)
    redis_bus._handle_device_event(7, "not-json")
    with pytest.raises(asyncio.QueueEmpty):
        q.get_nowait()


def test_device_event_no_subscriber_no_crash(clean_subscribers):
    """无订阅者时静默丢弃（其他副本可能有订阅者）。"""
    redis_bus._handle_device_event(7, json.dumps({"event_id": "e3", "seq": 1}))


def test_device_event_queue_full_drops(clean_subscribers, monkeypatch):
    """订阅队列满时丢弃该事件，不影响其他订阅者。"""
    monkeypatch.setattr(redis_bus.config, "CLIENT_QUEUE_SIZE", 1)
    q = redis_bus.subscribe(7)
    redis_bus._handle_device_event(7, json.dumps({"event_id": "e1", "seq": 1}))
    redis_bus._handle_device_event(7, json.dumps({"event_id": "e2", "seq": 2}))
    assert json.loads(q.get_nowait())["event_id"] == "e1"
    with pytest.raises(asyncio.QueueEmpty):
        q.get_nowait()



class _FakeAsyncRedis:
    """lrange 返回预置 ring（头插顺序 = 新→旧，与 LPUSH 语义一致）。"""

    def __init__(self, ring_events, error=None):
        self._raw = [json.dumps(e, ensure_ascii=False) for e in ring_events]
        self._error = error
        self.lrange_key = None

    async def lrange(self, key, start, end):
        if self._error:
            raise self._error
        self.lrange_key = key
        return self._raw


@pytest.fixture
def patch_get_redis(monkeypatch):
    """替换 get_redis 协程为返回 fake 客户端。"""
    def _install(fake):
        async def _fake_get_redis():
            return fake
        monkeypatch.setattr(redis_bus, "get_redis", _fake_get_redis)
        return fake
    return _install


@pytest.mark.anyio
async def test_get_events_since_filters_and_sorts_asc(patch_get_redis):
    """过滤 seq > since_seq 并按 seq 升序返回（LRANGE 原始顺序为新→旧）。"""
    fake = patch_get_redis(_FakeAsyncRedis([
        {"event_id": "c", "seq": 3},
        {"event_id": "a", "seq": 1},
        {"event_id": "e", "seq": 5},
    ]))
    events = await redis_bus.get_events_since(7, 0)
    assert [e["seq"] for e in events] == [1, 3, 5]
    assert fake.lrange_key == "ring:7"


@pytest.mark.anyio
async def test_get_events_since_since_seq_exclusive(patch_get_redis):
    """since_seq 为排他下界（只取严格大于）。"""
    patch_get_redis(_FakeAsyncRedis([
        {"seq": 3}, {"seq": 1}, {"seq": 5},
    ]))
    events = await redis_bus.get_events_since(7, 2)
    assert [e["seq"] for e in events] == [3, 5]


@pytest.mark.anyio
async def test_get_events_since_invalid_json_skipped(patch_get_redis):
    """ring 内坏行跳过，不影响其余事件。"""
    fake = _FakeAsyncRedis([{"seq": 2}])
    fake._raw.insert(0, "broken-json")
    patch_get_redis(fake)
    events = await redis_bus.get_events_since(7, 0)
    assert [e["seq"] for e in events] == [2]


@pytest.mark.anyio
async def test_get_events_since_redis_error_returns_empty(patch_get_redis):
    """Redis 异常时重放降级为空列表（best-effort，不阻断 SSE 连接建立）。"""
    patch_get_redis(_FakeAsyncRedis([], error=ConnectionError("redis down")))
    events = await redis_bus.get_events_since(7, 0)
    assert events == []
