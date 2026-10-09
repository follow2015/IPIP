# -*- coding: utf-8 -*-
"""多通道采集 · CLI 会话与会话池（T0.12 评审 §4 拆分）。

从 ``cli_channel.py`` 拆出，理由是**量不是质**：评审（2026-09-27，T0.5-T0.11
§4）实测 ``cli_channel.py`` 443 行，违反本项目 collector 工作既定的
"单文件 ≤300 行"门禁（``capability.py`` 注释：拆分即为了让 base_channel
控制在 300 行内）。职责本身是清晰的一块 —— per-device SSH 会话 + 池化回收 ——
单纯因为撮在一起把通道类挤爆了。

本模块是**私有的**（``_`` 前缀）：只服务 ``CliChannel``，不对外承诺接口。
依赖面与拆分前完全一致（``app.infra`` / ``app.utils.logging``），不新增
ADR-004 需要评审的依赖方向。
"""
from __future__ import annotations

import threading
import time
from contextlib import ExitStack, contextmanager
from typing import Any, Iterator

from app.infra import SSHManager
from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_READ_TIMEOUT = 120

DEFAULT_IDLE_TTL = float(DEFAULT_READ_TIMEOUT) + 30.0

_DEAD_CONNECTION_EXC_NAMES = frozenset({
    "SSHConnectionError",
    "NetmikoTimeoutException",
    "NetmikoAuthenticationException",
    "ReadTimeout",
    "EOFError",
    "AttributeError",   # 典型形态：底层 conn 已被置空 -> 'NoneType' object has no attribute
    "OSError",
    "socket.timeout",
})


class _CliSession:
    """单台设备的 SSH 会话：一条连接 + 串行锁（实现握手 N→1）。

    生命周期由 ``_SessionPool`` 管理。``get_connection`` 是 contextmanager，
    不能用 ``with`` 长期持有（离开块即断连），所以这里手动
    ``__enter__`` / ``__exit__``，由 pool 决定什么时候收。
    """

    __slots__ = ("device_id", "_stack", "_ssh", "conn", "lock", "last_used", "in_flight")

    def __init__(self, device_id: int, ssh: SSHManager) -> None:
        self.device_id = device_id
        self._ssh = ssh
        self._stack: ExitStack | None = None
        self.conn: Any = None
        self.lock = threading.Lock()
        self.last_used = time.monotonic()
        self.in_flight = 0

    @contextmanager
    def in_use(self) -> Iterator[None]:
        """标记"本会话正在被使用"，期间不可被空闲回收。

        放在 ``lock`` **外层**使用（``with session.in_use(), session.lock:``）：
        等锁的时间也算在用 —— 否则排队中的调用方会看着自己的会话被回收。
        """
        self.in_flight += 1
        self.touch()
        try:
            yield
        finally:
            self.in_flight -= 1
            self.touch()

    @property
    def connected(self) -> bool:
        return self._stack is not None

    def connect(self, switch: Any) -> None:
        """建立连接（幂等：已连接则忽略）。"""
        if self._stack is not None:
            return
        stack = ExitStack()
        try:
            conn = stack.enter_context(self._ssh.get_connection(switch))
        except Exception:
            stack.close()
            raise
        self._stack = stack
        self.conn = conn
        self.last_used = time.monotonic()

    def reconnect(self, switch: Any) -> None:
        """丢弃已断连接并重建（连接类异常后的恢复手段）。"""
        self.close()
        self.connect(switch)

    def close(self) -> None:
        if self._stack is None:
            return
        try:
            self._stack.close()
        except Exception as exc:  # noqa: BLE001 -- SSH 会话关闭失败容错：连接已废弃，关闭异常不影响本次采集结果判定
            logger.warning(
                "SSH 会话关闭异常 device_id=%s: %s（连接已废弃）",
                self.device_id, exc,
            )
        finally:
            self._stack = None
            self.conn = None

    def touch(self) -> None:
        self.last_used = time.monotonic()


class _SessionPool:
    """``_CliSession`` 的注册表：按 device 复用，带空闲回收 + 显式释放。

    为什么需要空闲 TTL：``collect()`` 模板没有"收尾钩子"，通道层拿不到
    "本次采集结束"的信号。若永不回收，短生命周期进程里会出现一批既不关闭也
    不再被使用的连接（占用设备端的 vty）。这里的折中是**惰性回收**：每次取会话
    时顺带清掉超过 ``idle_ttl`` 秒未被碰过的会话；上层（T-G1-2 的接入点）也可以在
    一次扫描结束后显式调 ``release_all()`` 立刻收干净。
    """

    def __init__(self, ssh: SSHManager, idle_ttl: float = DEFAULT_IDLE_TTL) -> None:
        self._ssh = ssh
        self._idle_ttl = idle_ttl
        self._lock = threading.Lock()
        self._sessions: dict[int, _CliSession] = {}

    def get(self, device_id: int) -> _CliSession:
        with self._lock:
            self._sweep_idle_locked()
            session = self._sessions.get(device_id)
            if session is None:
                session = _CliSession(device_id, self._ssh)
                self._sessions[device_id] = session
            return session

    def _sweep_idle_locked(self) -> None:
        now = time.monotonic()
        stale = [
            key for key, session in self._sessions.items()
            if session.in_flight == 0 and now - session.last_used > self._idle_ttl
        ]
        for key in stale:
            self._sessions.pop(key).close()

    def release(self, device_id: int) -> None:
        with self._lock:
            session = self._sessions.pop(device_id, None)
        if session is not None:
            session.close()

    def release_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.close()


__all__ = ["DEFAULT_IDLE_TTL", "DEFAULT_READ_TIMEOUT", "_CliSession", "_SessionPool"]
