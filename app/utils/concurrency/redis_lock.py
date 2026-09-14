# -*- coding: utf-8 -*-
"""Redis 分布式锁的公共原语（owner token / 原子释放）。

背景（整改 T2.6）
----------------
「按进程 owner token 做 CAS 释放」这段逻辑原先**只存在于**
`app/services/monitoring/monitor_worker.py` 的私有函数里，却被另外两个模块
跨模块借用：

- `app/services/monitoring/outbox_sender.py`：跨模块借用 monitor_worker 的
  **私有** `_release_lock`（v2 评审指出的分层问题）；
- `app/services/monitoring/standalone_service.py`：把它列进私有符号导入清单后
  再包一层实例方法。

本模块把它提升为公共原语，使上列调用方不再依赖别的服务的私有实现。

范围说明：**只搬「owner token + 原子释放」**。`monitor_worker` 的
`_acquire_lock` / `_renew_lock` / `_lock_ttl` 与轮询循环和看门狗强耦合，
本次不动（避免扩大改动面）；它们改为从本模块取 `owner_token()`。
"""
import os
import socket
import threading
import uuid

_RELEASE_LOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

_OWNER_TOKEN: str | None = None
_OWNER_PID: int | None = None
_OWNER_MUTEX = threading.Lock()


def owner_token() -> str:
    """返回本进程唯一的锁 owner token（`<host>:<pid>:<uuid4>`）。

    host / pid 前缀仅为排障可读性（``redis-cli get monitor:lock:snmp`` 能直接
    看出锁的归属进程）；唯一性由 uuid4 保证。

    Returns:
        str：本进程的锁归属标识。
    """
    global _OWNER_TOKEN, _OWNER_PID
    pid = os.getpid()
    if _OWNER_TOKEN is None or _OWNER_PID != pid:
        with _OWNER_MUTEX:
            if _OWNER_TOKEN is None or _OWNER_PID != pid:
                try:
                    host = socket.gethostname()
                except Exception:
                    host = "unknown"
                _OWNER_TOKEN = f"{host}:{pid}:{uuid.uuid4().hex}"
                _OWNER_PID = pid
    return _OWNER_TOKEN


def release_owner_lock(r, key: str) -> None:
    """显式释放锁（仅当仍由本进程持有时），避免 TTL 等待期内的空窗。

    使用 Lua 脚本做原子 compare-and-delete，消除 GET 与 DELETE 之间的 TOCTOU
    竞态：若锁恰好在此窗口内 TTL 过期、另一进程抢到新锁，原实现会误删别人的锁
    导致双跑。Lua 脚本保证 compare+delete 在 Redis 单线程内原子执行。比对的
    owner 是本进程唯一 token（见 `owner_token`）。

    Args:
        r: Redis 客户端（调用方保证非 None）。
        key: 完整的锁键（由调用方按各自前缀组装，如 `monitor:lock:snmp`）。
    """
    r.eval(_RELEASE_LOCK_LUA, 1, key, owner_token())
