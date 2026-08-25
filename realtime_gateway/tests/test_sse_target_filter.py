# -*- coding: utf-8 -*-
"""Task 7 — 网关侧测试：验证 redis_bus 全局事件的 target_user_ids 过滤（纯同步）。

不连接 Redis；使用 asyncio.Queue 的 get_nowait() / QueueEmpty 断言。
"""
import asyncio
import json

import pytest

from realtime_gateway import redis_bus


@pytest.fixture
def clean_subscribers():
    """每个测试前重置全局订阅者列表，避免跨测试污染。"""
    redis_bus._global_subscribers = []
    yield
    redis_bus._global_subscribers = []


def test_target_filter_only_target_receives(clean_subscribers):
    """target_user_ids=[5] 时，仅 user_id=5 的队列收到，user_id=6 的队列为空。"""
    q5 = redis_bus.subscribe_global(user_id=5)
    q6 = redis_bus.subscribe_global(user_id=6)

    redis_bus._handle_global_event(json.dumps({
        "event_type": "x",
        "target_user_ids": [5],
        "ts": 1,
    }))

    raw5 = q5.get_nowait()
    data5 = json.loads(raw5)
    assert data5["event_type"] == "x"
    assert data5["target_user_ids"] == [5]

    with pytest.raises(asyncio.QueueEmpty):
        q6.get_nowait()


def test_no_target_broadcasts_to_all(clean_subscribers):
    """target_user_ids=None 时，所有订阅者都收到。"""
    q5 = redis_bus.subscribe_global(user_id=5)
    q6 = redis_bus.subscribe_global(user_id=6)

    redis_bus._handle_global_event(json.dumps({
        "event_type": "x",
        "target_user_ids": None,
        "ts": 1,
    }))

    assert json.loads(q5.get_nowait())["event_type"] == "x"
    assert json.loads(q6.get_nowait())["event_type"] == "x"


def test_missing_target_field_broadcasts_to_all(clean_subscribers):
    """字段缺失时等同全局广播，所有订阅者都收到。"""
    q5 = redis_bus.subscribe_global(user_id=5)
    q6 = redis_bus.subscribe_global(user_id=6)

    redis_bus._handle_global_event(json.dumps({
        "event_type": "y",
        "ts": 1,
    }))

    assert json.loads(q5.get_nowait())["event_type"] == "y"
    assert json.loads(q6.get_nowait())["event_type"] == "y"


def test_unsubscribe_by_queue_identity(clean_subscribers):
    """unsubscribe_global 按队列对象身份移除；移除后不再收到广播。"""
    q5 = redis_bus.subscribe_global(user_id=5)
    redis_bus.subscribe_global(user_id=6)

    redis_bus.unsubscribe_global(q5)
    assert len(redis_bus._global_subscribers) == 1
    assert redis_bus._global_subscribers[0][0] is not q5

    redis_bus._handle_global_event(json.dumps({"event_type": "z", "ts": 1}))
    with pytest.raises(asyncio.QueueEmpty):
        q5.get_nowait()


def test_subscribe_without_user_id_only_gets_broadcast(clean_subscribers):
    """未绑定用户(user_id=None)的订阅仅收广播，收不到定向事件。"""
    q_anon = redis_bus.subscribe_global(user_id=None)

    redis_bus._handle_global_event(json.dumps({
        "event_type": "x",
        "target_user_ids": [7],
        "ts": 1,
    }))
    with pytest.raises(asyncio.QueueEmpty):
        q_anon.get_nowait()

    redis_bus._handle_global_event(json.dumps({
        "event_type": "x",
        "target_user_ids": None,
        "ts": 1,
    }))
    assert json.loads(q_anon.get_nowait())["event_type"] == "x"
