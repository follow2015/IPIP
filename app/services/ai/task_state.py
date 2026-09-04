# -*- coding: utf-8 -*-
"""异步任务状态外置存储（C3 修复）。

进程内字典在多 gunicorn worker 下失效：提交 worker 与 SSE 进度 worker 不同，
导致 _TASKS.get(task_id) 永远 {} → SSE 死循环。

本模块用 Redis 作外置状态存储（JSON 序列化），无 Redis 时降级回进程内字典
（仅单 worker 部署可用，会在日志告警）。
"""
import json
import time
from typing import Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

_PREFIX = "ai:task:"
_TTL = 3600  # 任务状态保留 1 小时

_UPDATE_LUA = """
local raw = redis.call('GET', KEYS[1])
local state = {}
if raw then
    local ok, decoded = pcall(cjson.decode, raw)
    if ok and type(decoded) == 'table' then
        state = decoded
    end
end
local fields = cjson.decode(ARGV[1])
for k, v in pairs(fields) do
    state[k] = v
end
redis.call('SET', KEYS[1], cjson.encode(state), 'EX', ARGV[2])
return 1
"""

_SAVE_LUA = """
local raw = redis.call('GET', KEYS[1])
local new = cjson.decode(ARGV[1])
if raw then
    local ok, decoded = pcall(cjson.decode, raw)
    if ok and type(decoded) == 'table' then
        -- I4 继承：JSON null 解码为 cjson.null 而非 nil，故「显式传 None」
        -- 视为已携带，不继承（与 Python 侧 `"user_id" not in state` 同义）
        if new['user_id'] == nil and decoded['user_id'] ~= nil then
            new['user_id'] = decoded['user_id']
        end
    end
end
redis.call('SET', KEYS[1], cjson.encode(new), 'EX', ARGV[2])
return 1
"""

_FALLBACK: dict = {}
_FALLBACK_MAX = 1000
_FALLBACK_TTL = _TTL  # 与 Redis 侧语义对齐，避免两条路径行为分叉
_REDIS = None
_REDIS_RESOLVED = False


def _fallback_prune(now: float) -> None:
    """淘汰降级字典中的过期条目，超限时再按插入顺序淘汰最旧的（A10）。"""
    expired = [k for k, (ts, _) in _FALLBACK.items() if now - ts > _FALLBACK_TTL]
    for k in expired:
        _FALLBACK.pop(k, None)
    overflow = len(_FALLBACK) - _FALLBACK_MAX
    if overflow > 0:
        for k in list(_FALLBACK)[:overflow]:
            _FALLBACK.pop(k, None)


def _fallback_set(task_id: str, state: dict) -> None:
    """写入降级状态（先删再插，保证淘汰顺序按最近写入时间）。"""
    _FALLBACK.pop(task_id, None)
    now = time.time()
    _FALLBACK[task_id] = (now, state)
    _fallback_prune(now)


def _fallback_get(task_id: str) -> Optional[dict]:
    """读取降级状态，过期返回 None 并顺带清除。"""
    entry = _FALLBACK.get(task_id)
    if entry is None:
        return None
    ts, state = entry
    if time.time() - ts > _FALLBACK_TTL:
        _FALLBACK.pop(task_id, None)
        return None
    return state


def _get_redis():
    global _REDIS, _REDIS_RESOLVED
    if _REDIS_RESOLVED:
        return _REDIS
    _REDIS_RESOLVED = True
    try:
        from app.utils.redis_client import get_redis_client
        _REDIS = get_redis_client()
    except Exception:  # noqa: BLE001
        _REDIS = None
    if _REDIS is None:
        logger.warning("ai.task_state redis 不可用，降级为进程内字典（仅单 worker 部署正确）")
    return _REDIS


def save(task_id: str, state: dict, nx: bool = False) -> None:
    """保存任务状态（整体覆盖）。

    I4 加固：若新状态未携带 `user_id` 但已存在归属信息，保留之，防止任何
    漏写 `user_id` 的调用方清空任务归属（C1 类 fail-closed 脆弱性）。

    A3 加固：`nx=True` 时仅在键不存在时写入（SET NX）。用于 API 入队预写
    `pending`——预写永远不应赢得与 worker 的竞态：若 worker 已写入
    running/终态，预写直接放弃，避免进度回退或终态被旧 pending 覆盖。
    """
    r = _get_redis()
    if r is None:
        if nx and _fallback_get(task_id) is not None:
            return
        _fallback_set(task_id, state)
        return
    key = f"{_PREFIX}{task_id}"
    try:
        if nx:
            r.set(key, json.dumps(state, ensure_ascii=False), ex=_TTL, nx=True)
            return
        r.eval(_SAVE_LUA, 1, key, json.dumps(state, ensure_ascii=False), str(_TTL))
        return
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.task_state.lua_save_fallback %s", e)
    try:
        existing_raw = r.get(key)
        if existing_raw is not None and "user_id" not in state:
            try:
                existing = json.loads(
                    existing_raw.decode("utf-8")
                    if isinstance(existing_raw, bytes) else existing_raw
                )
                if existing.get("user_id") is not None:
                    state = {**state, "user_id": existing["user_id"]}
            except Exception:  # noqa: BLE001
                pass
        r.set(key, json.dumps(state, ensure_ascii=False), ex=_TTL)
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.task_state.save_failed %s", e)
        _fallback_set(task_id, state)


def update(task_id: str, **fields) -> None:
    """局部更新任务状态：仅覆盖给定字段，并保留已有 `user_id`（未显式传入时）。

    相比 `save` 的全量覆盖，适合「只改 status / progress」等增量写入，避免调用方
    因漏传 `user_id` 而清空任务归属（见 I4）。`user_id` 永远从已有状态继承，除非
    本次显式覆盖。

    A3：优先走 Lua 原子读改写（见 `_UPDATE_LUA`）；EVAL 不可用（仅测试用
    fake 客户端会出现）才退回非原子 GET→合并→SET，生产 redis-py 恒支持。
    """
    r = _get_redis()
    if r is None:
        existing = _fallback_get(task_id) or {}
        merged = {**existing, **fields}
        if "user_id" not in fields and existing.get("user_id") is not None:
            merged["user_id"] = existing["user_id"]
        _fallback_set(task_id, merged)
        return
    key = f"{_PREFIX}{task_id}"
    try:
        r.eval(_UPDATE_LUA, 1, key, json.dumps(fields, ensure_ascii=False),
               str(_TTL))
        return
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.task_state.lua_update_fallback %s", e)
    try:
        raw = r.get(key)
        state = (
            json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            if raw else {}
        )
    except Exception:  # noqa: BLE001
        state = {}
    state.update(fields)
    if "user_id" not in fields and state.get("user_id") is None:
        pass
    try:
        r.set(key, json.dumps(state, ensure_ascii=False), ex=_TTL)
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.task_state.update_failed %s", e)
        _fallback_set(task_id, state)


def load(task_id: str) -> Optional[dict]:
    """读取任务状态，不存在返回 None。"""
    r = _get_redis()
    if r is None:
        return _fallback_get(task_id)
    try:
        val = r.get(f"{_PREFIX}{task_id}")
        if val is None:
            return None
        if isinstance(val, bytes):
            val = val.decode("utf-8")
        return json.loads(val)
    except Exception as e:  # noqa: BLE001
        logger.warning("ai.task_state.load_failed %s", e)
        return _fallback_get(task_id)


def delete(task_id: str) -> None:
    """清理任务状态。"""
    r = _get_redis()
    if r is None:
        _FALLBACK.pop(task_id, None)
        return
    try:
        r.delete(f"{_PREFIX}{task_id}")
    except Exception:  # noqa: BLE001
        pass
