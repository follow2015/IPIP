# -*- coding: utf-8 -*-
"""S2：断线重放与订阅建立之间的竞态。

原实现先 `get_events_since`（LRANGE 读 ring）再 `subscribe`：两步之间发布的事件
既不在重放结果里、订阅也尚未建立，重连窗口期事件静默丢失——恰好是"断线重放"
要覆盖的场景。修复为先订阅后重放，并按 seq 去重合并。

不连接真实 Redis。
"""
import asyncio
import json
from unittest.mock import patch

from realtime_gateway import redis_bus, sse


def _collect(stream, timeout: float = 0.5) -> list[str]:
    """驱动 SSE 生成器至超时，收集已产出的帧。"""
    frames: list[str] = []

    async def run() -> None:
        async for frame in stream:
            frames.append(frame)

    async def drive() -> None:
        try:
            await asyncio.wait_for(run(), timeout)
        except asyncio.TimeoutError:
            pass

    asyncio.run(drive())
    return frames


def _data_seqs(frames: list[str]) -> list:
    """提取数据帧中的 seq（跳过心跳帧）。"""
    seqs = []
    for frame in frames:
        if not frame.startswith("data: "):
            continue
        seqs.append(json.loads(frame[len("data: "):].strip()).get("seq"))
    return seqs


def test_subscribe_happens_before_replay():
    """S2：必须先建立订阅再读 ring，否则两步之间的事件无人接收。"""
    order: list[str] = []

    async def fake_get_events_since(device_id, since_seq):
        order.append("replay")
        return [{"seq": 1}]

    def fake_subscribe(device_id):
        order.append("subscribe")
        return asyncio.Queue()

    with patch.object(redis_bus, "subscribe", fake_subscribe), \
            patch.object(redis_bus, "get_events_since", fake_get_events_since), \
            patch.object(redis_bus, "unsubscribe", lambda *a: None):
        _collect(sse.device_event_stream(7, since_seq=0))

    assert order == ["subscribe", "replay"], (
        "先重放后订阅会让窗口期事件静默丢失"
    )


def test_window_event_not_duplicated():
    """S2：订阅后已推送过的事件，重放时不得再发一遍。"""
    async def fake_get_events_since(device_id, since_seq):
        return [{"seq": 1}, {"seq": 2}, {"seq": 3}]

    def fake_subscribe(device_id):
        q: asyncio.Queue = asyncio.Queue()
        q.put_nowait(json.dumps({"seq": 3}))  # 订阅建立后即到达
        return q

    with patch.object(redis_bus, "subscribe", fake_subscribe), \
            patch.object(redis_bus, "get_events_since", fake_get_events_since), \
            patch.object(redis_bus, "unsubscribe", lambda *a: None):
        frames = _collect(sse.device_event_stream(7, since_seq=0))

    assert _data_seqs(frames) == [1, 2, 3], "seq 3 被重复投递或顺序错乱"


def test_event_arrived_after_subscribe_is_not_lost():
    """S2：ring 读取滞后时，队列里已到达的事件必须补发（不得丢）。"""
    async def fake_get_events_since(device_id, since_seq):
        return [{"seq": 1}]

    def fake_subscribe(device_id):
        q: asyncio.Queue = asyncio.Queue()
        q.put_nowait(json.dumps({"seq": 2}))  # ring 读取前已入队
        return q

    with patch.object(redis_bus, "subscribe", fake_subscribe), \
            patch.object(redis_bus, "get_events_since", fake_get_events_since), \
            patch.object(redis_bus, "unsubscribe", lambda *a: None):
        frames = _collect(sse.device_event_stream(7, since_seq=0))

    assert _data_seqs(frames) == [1, 2], "队列中的新事件不得因重放逻辑被丢弃"


def test_event_during_replay_not_duplicated():
    """S2 补充：重放挂起期间到达的事件不得被「重放 + 实时」各投一次。

    发布侧顺序是「ring 落定后再 publish」，故重放的网络往返期间到达的事件
    必然同时在 ring 结果与实时队列里——实时循环必须按 seq 去重。
    """
    q_holder: dict = {}

    async def fake_get_events_since(device_id, since_seq):
        q_holder["q"].put_nowait(json.dumps({"seq": 2}))
        return [{"seq": 1}, {"seq": 2}]

    def fake_subscribe(device_id):
        q: asyncio.Queue = asyncio.Queue()
        q_holder["q"] = q
        return q

    with patch.object(redis_bus, "subscribe", fake_subscribe), \
            patch.object(redis_bus, "get_events_since", fake_get_events_since), \
            patch.object(redis_bus, "unsubscribe", lambda *a: None):
        frames = _collect(sse.device_event_stream(7, since_seq=0))

    assert _data_seqs(frames) == [1, 2], "seq 2 被「重放 + 实时」重复投递"
