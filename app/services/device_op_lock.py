# -*- coding: utf-8 -*-
"""
设备级操作锁

防止同一台交换机并发执行多个 SSH 操作，
避免竞态条件导致配置乱序或事件顺序错误。

- 有 Redis 时：使用分布式锁（多进程 gunicorn 下安全）
- 无 Redis 时：**分模式处置**（R9）
  - ``mode="write"``（SSH 配置下发）：默认 **fail-closed** —— 抛
    ``DeviceLockUnavailable``（503）。进程内 ``threading.Lock`` 在多 worker /
    Celery prefork 下**不提供任何跨进程互斥**，而并发下发的后果是配置乱序，
    宁可拒绝也不能"看起来成功"。
  - ``mode="read"``（诊断 / 配置采集）：仍降级为进程内锁并记 warning。
    这类调用方本就把"未获锁"当作正常降级路径（supported:false / 设备繁忙），
    无谓拒绝只会掐断只读能力，无收益。

逃生阀：确认为单进程部署时设 ``DEVICE_OP_LOCK_REQUIRE_REDIS=0``
（或 ``app.config["DEVICE_OP_LOCK_REQUIRE_REDIS"] = False``）恢复原降级行为。
"""
from __future__ import annotations

import contextlib
import os
import time
from app.utils.logging import get_logger
import threading

from app.exceptions.business import DeviceLockUnavailable
from app.utils import redis_keys

logger = get_logger(__name__)

POLICY_ENV = "DEVICE_OP_LOCK_REQUIRE_REDIS"
_TRUE_TOKENS = frozenset({"1", "true", "yes", "on", "strict", "distributed"})
_FALSE_TOKENS = frozenset({"0", "false", "no", "off", "local", "single"})

_LOG_THROTTLE_SECONDS = 60.0
_fail_closed_stats = {"count": 0, "last_log": 0.0}
_degrade_stats = {"count": 0, "last_log": 0.0}


class DeviceOperationConflict(Exception):
    """设备当前有操作正在执行，无法接受新操作"""


def _read_policy_setting():
    """读部署形态开关（app.config > env > None 表示未声明）。"""
    raw = None
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            raw = current_app.config.get(POLICY_ENV)
    except Exception:  # noqa: BLE001 —— 无 Flask / 无 app context 均属正常
        raw = None
    if raw is None:
        raw = os.getenv(POLICY_ENV)
    return raw


def _must_fail_closed(mode: str) -> bool:
    """无 Redis 时该模式是否必须拒绝执行。

    read 模式恒为 False：其调用方本就容忍"拿不到锁"（诊断降级 supported:false、
    配置采集报"设备繁忙"），且在单进程内的互斥仍有价值（避免与同进程写操作并发）。
    """
    if mode != "write":
        return False

    raw = _read_policy_setting()
    if raw is None:
        return True  # 未声明 ⇒ 默认 fail-closed
    if isinstance(raw, bool):
        return raw
    token = str(raw).strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    logger.warning(
        "%s=%r 无法识别，按 fail-closed 处理（可用值：%s / %s）",
        POLICY_ENV, raw, sorted(_TRUE_TOKENS)[:3], sorted(_FALSE_TOKENS)[:3],
    )
    return True


def _throttled_error(stats, message, *args):
    """按固定间隔记一条 error/warning，避免故障期间刷屏。"""
    stats["count"] += 1
    now = time.monotonic()
    if now - stats["last_log"] < _LOG_THROTTLE_SECONDS:
        return
    stats["last_log"] = now
    logger.error(message, *args)


def _log_degraded(mode: str, device_id, lock_key):
    """read 模式降级为进程内锁的可观测留痕（旧行为完全静默）。"""
    _degrade_stats["count"] += 1
    now = time.monotonic()
    if now - _degrade_stats["last_log"] < _LOG_THROTTLE_SECONDS:
        return
    _degrade_stats["last_log"] = now
    logger.warning(
        "Redis 不可用：设备 %s 的 %s 锁降级为**进程内**锁（key=%s，累计 %d 次）"
        "—— 多 worker 部署下跨进程互斥不成立",
        device_id, mode, lock_key, _degrade_stats["count"],
    )


class DeviceOpLock:
    """设备级操作锁（Redis / 内存双模式，**支持同线程内重入**）

    为什么必须支持重入
    ------------------
    这是把互斥下沉到 ``CommandDispatcher._send_config`` 的前提。下沉后，
    已经持锁的调用方（如 ``lag_config_service.remove_port_from_channel``）
    会在 with 块内部再次进入 ``_send_config`` -> 二次 acquire 同一把锁：

    - 内存模式用的是 ``threading.Lock``（**不是 RLock**），同线程二次 acquire 直接死锁；
    - Redis 模式的 redis-py 可重入只在**同一 Lock 实例**内靠 ``local.token +
      _lock_count`` 生效，而 ``acquire()`` 每次都新建 ``r.lock(...)`` 实例，
      换实例即自我等待，直到 ``blocking_timeout`` 超时才抛
      ``DeviceOperationConflict``。

    因此重入语义必须在本类实现：**同一线程**对同一 ``lock_key`` 的嵌套 acquire
    只增加计数，不再次向底层申请锁；计数归零时才真正释放。
    """

    _local_locks: dict = {}
    _meta_lock = threading.Lock()
    _reentrant_local = threading.local()

    def _get_local_lock(self, key) -> threading.Lock:
        """获取或创建设备级线程锁（按 key 隔离，key 可为 device_id 或 lock_key 字符串）"""
        with self._meta_lock:
            if key not in self._local_locks:
                self._local_locks[key] = threading.Lock()
            return self._local_locks[key]

    @contextlib.contextmanager
    def acquire(self, device_id: int, timeout: float = 60.0,
                lock_key: str = None, mode: str = "write"):
        """获取设备操作锁

        Phase 1.4：扩展 lock_key/mode 参数，支撑诊断只读锁与配置写锁隔离。
        设计文档第三节要求：诊断走独立的只读锁（timeout=5，未获锁即降级 supported:false），
        与配置下发的写锁使用不同 lock_key 命名空间，避免互相阻塞。

        Args:
            device_id: 要锁定的设备 ID
            timeout:   等待超时（秒）
            lock_key:  自定义锁键名（默认按 mode 生成命名空间）。
                       诊断只读锁用 "device_op_lock:ro:{device_id}"，
                       配置写锁用 "device_op_lock:{device_id}"（向后兼容）。
            mode:      锁模式 "write"（默认，配置下发）/ "read"（诊断只读）。
                       read 模式下未获锁不阻塞业务（调用方自行降级），故 timeout 较短。

        Raises:
            DeviceOperationConflict: 超时无法获取锁（设备繁忙）
            DeviceLockUnavailable:   无 Redis 且未声明单进程（write 模式 fail-closed）

        Usage:
            with device_op_lock.acquire(switch.device_id):
            with device_op_lock.acquire(device_id, timeout=5, mode="read"):
        """
        from app.services.switch_events import _get_redis
        r = _get_redis()

        if lock_key is None:
            if mode == "read":
                lock_key = redis_keys.device_op_lock_ro_key(device_id)
            else:
                lock_key = redis_keys.device_op_lock_key(device_id)

        held = getattr(self._reentrant_local, "map", None)
        if held is None:
            held = {}
            self._reentrant_local.map = held
        rec = held.get(lock_key)
        if rec is not None:
            rec[0] += 1
            try:
                yield
            finally:
                rec[0] -= 1
            return

        if r is None and _must_fail_closed(mode):
            _throttled_error(
                _fail_closed_stats,
                "Redis 不可用：设备 %s 的 write 锁无法建立跨进程互斥，"
                "已拒绝执行（累计 %d 次）——若为单进程部署请设置 %s=0",
                device_id, _fail_closed_stats["count"], POLICY_ENV,
            )
            raise DeviceLockUnavailable(device_id, lock_key)

        if r:
            lock = r.lock(
                lock_key,
                timeout=timeout * 2,  # 自动释放时间 = 操作超时的2倍
                blocking_timeout=timeout,  # 等待时间 = 操作超时
                thread_local=False,
            )
            acquired = lock.acquire(blocking=True)
            if not acquired:
                raise DeviceOperationConflict(
                    f"设备 {device_id} 当前有 SSH 操作正在执行，请稍后重试（超时 {timeout}s）"
                )
            held[lock_key] = [1]  # 记账：本线程外层持有（此后嵌套 acquire 走重入分支）
            stop_renew = threading.Event()
            renew_period = max((timeout * 2) / 4.0, 0.05)

            def _renew_lease():
                while not stop_renew.wait(renew_period):
                    try:
                        lock.extend(timeout * 2, replace_ttl=True)
                    except Exception:
                        logger.error(
                            "设备 %s 锁租约续期失败 key=%s —— 锁可能已过期，互斥失效",
                            device_id, lock_key, exc_info=True,
                        )
                        return

            renew_thread = threading.Thread(
                target=_renew_lease, daemon=True,
                name=f"device-op-lock-renew-{device_id}",
            )
            renew_thread.start()
            try:
                yield
            finally:
                held.pop(lock_key, None)  # 摘记账，避免异常路径残留导致永久重入
                stop_renew.set()
                renew_thread.join(timeout=1)
                try:
                    lock.release()
                except Exception:
                    logger.error(
                        "释放设备 %s 分布式锁失败 key=%s —— 锁将依赖 TTL 过期",
                        device_id, lock_key, exc_info=True,
                    )
        else:
            _log_degraded(mode, device_id, lock_key)
            lock = self._get_local_lock(lock_key)
            acquired = lock.acquire(timeout=timeout)
            if not acquired:
                raise DeviceOperationConflict(
                    f"设备 {device_id} 当前有 SSH 操作正在执行，请稍后重试"
                )
            held[lock_key] = [1]
            try:
                yield
            finally:
                held.pop(lock_key, None)
                lock.release()


device_op_lock = DeviceOpLock()
