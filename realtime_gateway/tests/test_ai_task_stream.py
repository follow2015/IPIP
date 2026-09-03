# -*- coding: utf-8 -*-
"""AI 任务进度 SSE 流（P0-7 迁移）单元测试。

不连接真实 Redis：`redis_bus.get_redis` 打桩为返回 fake 客户端。
验证：任务不存在 / 归属不符 fail-closed / 进度推送与终态结束 / 变更才下发。
"""
import asyncio
import json
from unittest.mock import patch

from realtime_gateway import ai_task_stream


class _FakeRedis:
    """get() 依次返回队列中的值，耗尽后返回最后值。"""

    def __init__(self, values: list):
        self._values = list(values)

    async def get(self, key):
        if len(self._values) > 1:
            return self._values.pop(0)
        return self._values[0] if self._values else None


def _state(**kw) -> bytes:
    base = {"status": "running", "progress": 0, "total": 10, "user_id": 1}
    base.update(kw)
    return json.dumps(base).encode()


def _collect(stream, timeout: float = 0.5) -> list[str]:
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


def _data_frames(frames):
    return [f[len("data: "):].strip() for f in frames if f.startswith("data: ")]


def test_task_not_found_yields_error_and_ends():
    fake = _FakeRedis([None])
    with patch.object(ai_task_stream.redis_bus, "get_redis", return_value=fake):
        frames = _collect(ai_task_stream.ai_task_event_stream("nope", user_id=1))
    assert len(frames) == 1
    payload = json.loads(_data_frames(frames)[0])
    assert payload == {"type": "error", "message": "task not found"}


def test_owner_mismatch_rejected_fail_closed():
    for state in (_state(user_id=2), _state_without_user()):
        fake = _FakeRedis([state])
        with patch.object(ai_task_stream.redis_bus, "get_redis", return_value=fake):
            frames = _collect(ai_task_stream.ai_task_event_stream("t1", user_id=1))
        payload = json.loads(_data_frames(frames)[0])
        assert payload == {"type": "error", "message": "无权访问该任务"}
        assert len(frames) == 1


def _state_without_user() -> bytes:
    return json.dumps({"status": "running", "progress": 0, "total": 10}).encode()


def test_progress_pushed_then_done_ends_stream():
    done_state = _state(status="done", progress=10, total=10, result={"session_id": 7})
    fake = _FakeRedis([_state(progress=1), done_state])
    with patch.object(ai_task_stream.redis_bus, "get_redis", return_value=fake), \
         patch.object(ai_task_stream, "POLL_INTERVAL", 0.01):
        frames = _collect(ai_task_stream.ai_task_event_stream("t1", user_id=1))
    payloads = [json.loads(x) for x in _data_frames(frames)]
    assert payloads[0]["type"] == "progress"
    assert payloads[0]["status"] == "running"
    assert payloads[-1] == {"type": "done", "result": {"session_id": 7}}
    assert len(payloads) <= 3


def test_emit_only_on_change():
    """状态未变时不得重复下发（Flask 版 0.5s 无条件 yield 问题的网关侧修正）。"""
    same = _state(progress=1)
    fake = _FakeRedis([same, same, same])
    with patch.object(ai_task_stream.redis_bus, "get_redis", return_value=fake):
        frames = _collect(ai_task_stream.ai_task_event_stream("t1", user_id=1))
    progress_frames = [x for x in _data_frames(frames) if json.loads(x)["type"] == "progress"]
    assert len(progress_frames) == 1


def test_heartbeat_when_idle():
    """长时间无状态变化时发心跳注释帧（前端解析器忽略）。"""
    fake = _FakeRedis([_state(), _state(), _state()])
    with patch.object(ai_task_stream.redis_bus, "get_redis", return_value=fake), \
         patch.object(ai_task_stream, "HEARTBEAT_INTERVAL", 0.02), \
         patch.object(ai_task_stream, "POLL_INTERVAL", 0.01):
        frames = _collect(ai_task_stream.ai_task_event_stream("t1", user_id=1), timeout=0.3)
    assert any(f.startswith(": keepalive") for f in frames)


async def _async_of(fake):
    return fake
