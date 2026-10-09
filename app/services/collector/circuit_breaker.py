# -*- coding: utf-8 -*-
"""多通道采集 · 熔断计数存储（T0.12 评审 §4 拆分）。

**语义澄清**：本模块是采集通道的**熔断器**（circuit breaker）计数存储，
与"线路 / 电路资产"**没有任何关系**。线路资产是 G1 规划的独立模块
（``docs/design/G1-线路管理-数据模型设计文档-20260928.md``，落点为
``app/models/circuit.py``）。两者一度同名，为避免后续阅读与检索混淆，
本模块命名为 ``circuit_breaker``——它本来就是熔断器，不改语义，只改名字。

从 ``selector.py`` 拆出，理由与 ``_cli_session.py`` 同：**量不是质**。
评审（2026-09-27，T0.5-T0.11 §4）实测 ``selector.py`` 426 行，超本项目
collector 工作既定的"单文件 ≤300 行"门禁。熔断是一块**自成一体**的状态机
（计数累加 / 滑动窗口 TTL / 成功清零 / Redis 故障退化为不熔断），与"选哪个
通道、怎么分派"没有耦合，搬出来不会把语义拆散。

``selector.py`` 仍 re-export 本模块的全部名字：外部（含单测）按
``from ...selector import MemoryCircuitStore`` 导入的路径**不变**，本拆分为
纯结构整理，不是接口变更。
"""
from __future__ import annotations

import threading
import time
from typing import Protocol

from app.utils.logging import get_logger

logger = get_logger(__name__)

CIRCUIT_KEY_TEMPLATE = "ipm:chhealth:{channel}:{device_id}"

DEFAULT_CIRCUIT_THRESHOLD = 5
DEFAULT_CIRCUIT_TTL = 600.0


_circuit_degraded_stats: dict[str, int] = {"read": 0, "write": 0, "clear": 0}
_circuit_warn_at = 0.0
_circuit_warn_lock = threading.Lock()
_CIRCUIT_WARN_INTERVAL = 60.0  # 秒


def _warn_circuit_degraded(op: str, exc: Exception) -> None:
    """熔断计数不可用时的节流告警（首次及每 60s 一次）。

    [WARN] 语义不变：仍然是「退化成不熔断而不是拒绝采集」（见 ``RedisCircuitStore``
    类文档）。本函数只改**日志频率**，不动降级策略 —— 那属于产品语义决策。
    """
    global _circuit_warn_at
    _circuit_degraded_stats[op] = _circuit_degraded_stats.get(op, 0) + 1
    now = time.monotonic()
    with _circuit_warn_lock:
        if now - _circuit_warn_at < _CIRCUIT_WARN_INTERVAL:
            return
        _circuit_warn_at = now
    logger.warning(
        "熔断计数不可用，已退化为「不熔断」（read=%d write=%d clear=%d 次；"
        "本条每 60s 提醒一次）—— 采集照常执行，但不会因连续失败被熔断。"
        "最近一次错误: %s",
        _circuit_degraded_stats["read"], _circuit_degraded_stats["write"],
        _circuit_degraded_stats["clear"], exc,
    )


class CircuitStore(Protocol):
    """熔断计数存储。抽成协议是为了让单测不必起 Redis。"""

    def failures(self, channel: str, device_id: int) -> int: ...

    def record_failure(self, channel: str, device_id: int) -> int: ...

    def record_success(self, channel: str, device_id: int) -> None: ...


class MemoryCircuitStore:
    """进程内熔断计数（单测 / 无 Redis 环境的兜底）。

    与 Redis 版保持同一语义：失败累加并刷新窗口，成功清零。

    [WARN] 2026-10-05 评审 I-6 的修正：**加锁**。原先是裸 read-modify-write，
    多线程并发采集时计数会丢 —— 表现为"明明连续失败，却迟迟不熔断"。

    职责边界：本类只做"计数 + 过期归零"。**打开/半开的状态机在 Selector**
    （它同时掌握 threshold 与"该通道本轮还能不能用"的语境）。把 threshold 也塞进
    store 会变成两份阈值、互不一致 —— 实测形态：store 默认 5、selector 传 1 时，
    半开计数被误判成"仍在熔断"，通道**永远恢复不了**（半开放在这里时踩到过）。
    """

    def __init__(self, ttl: float = DEFAULT_CIRCUIT_TTL) -> None:
        self.ttl = float(ttl)          # 公开：Selector 默认沿用同一窗口长度
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, int], tuple[int, float]] = {}

    def _live_locked(self, key: tuple[str, int]) -> int:
        entry = self._counts.get(key)
        if entry is None:
            return 0
        count, expires_at = entry
        if time.monotonic() >= expires_at:
            self._counts.pop(key, None)
            return 0
        return count

    def failures(self, channel: str, device_id: int) -> int:
        with self._lock:
            return self._live_locked((channel, device_id))

    def record_failure(self, channel: str, device_id: int) -> int:
        key = (channel, device_id)
        with self._lock:
            count = self._live_locked(key) + 1
            self._counts[key] = (count, time.monotonic() + self.ttl)
            return count

    def record_success(self, channel: str, device_id: int) -> None:
        with self._lock:
            self._counts.pop((channel, device_id), None)


class RedisCircuitStore:
    """Redis 熔断计数（设计文档 §19.2 的键形与 TTL）。

    Redis 不可用时的取舍：**退化成"不熔断"而不是"拒绝采集"** —— 熔断是优化手段
    （少打一台已经崩了的设备），为它把整轮扫描打挂是拿可用性换一致性，方向反了。
    退化会留 warning，便于发现中间件掉了。

    多 worker 下这是**唯一**能让计数真正共享的存储（进程内计数各算各的、重启清零）
    —— Selector 的默认兜底是进程内版，接入点应优先注入本类。
    """

    def __init__(self, ttl: float = DEFAULT_CIRCUIT_TTL) -> None:
        self.ttl = float(ttl)
        self._ttl = int(ttl)

    def _client(self):
        from app.utils.redis_client import get_redis_client

        return get_redis_client()

    def _key(self, channel: str, device_id: int) -> str:
        return CIRCUIT_KEY_TEMPLATE.format(channel=channel, device_id=device_id)

    def failures(self, channel: str, device_id: int) -> int:
        try:
            raw = self._client().get(self._key(channel, device_id))
        except Exception as exc:  # noqa: BLE001 -- 熔断器读降级：已通过 _warn_circuit_degraded 留痕，返回 0（视为空结果）
            _warn_circuit_degraded("read", exc)
            return 0
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0

    def record_failure(self, channel: str, device_id: int) -> int:
        key = self._key(channel, device_id)
        try:
            client = self._client()
            count = int(client.incr(key))
            client.expire(key, self._ttl)
            return count
        except Exception as exc:  # noqa: BLE001 -- 熔断器写降级：同 141
            _warn_circuit_degraded("write", exc)
            return 0

    def record_success(self, channel: str, device_id: int) -> None:
        try:
            self._client().delete(self._key(channel, device_id))
        except Exception as exc:  # noqa: BLE001 -- 熔断器清理降级：同 141
            _warn_circuit_degraded("clear", exc)


__all__ = [
    "CIRCUIT_KEY_TEMPLATE",
    "DEFAULT_CIRCUIT_THRESHOLD",
    "DEFAULT_CIRCUIT_TTL",
    "CircuitStore",
    "MemoryCircuitStore",
    "RedisCircuitStore",
]
