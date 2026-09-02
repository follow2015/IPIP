# -*- coding: utf-8 -*-
"""
设备级操作锁

防止同一台交换机并发执行多个 SSH 操作，
避免竞态条件导致配置乱序或事件顺序错误。

- 有 Redis 时：使用分布式锁（多进程 gunicorn 下安全）
- 无 Redis 时：使用线程锁（单进程模式）
"""
from __future__ import annotations

import contextlib
from app.utils.logging import get_logger
import threading

logger = get_logger(__name__)


class DeviceOperationConflict(Exception):
    """设备当前有操作正在执行，无法接受新操作"""


class DeviceOpLock:
    """设备级操作锁（Redis / 内存双模式）"""

    _local_locks: dict = {}
    _meta_lock = threading.Lock()

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

        Usage:
            with device_op_lock.acquire(switch.device_id):
            with device_op_lock.acquire(device_id, timeout=5, mode="read"):
        """
        from app.services.switch_events import _get_redis
        r = _get_redis()

        if lock_key is None:
            if mode == "read":
                lock_key = f"device_op_lock:ro:{device_id}"
            else:
                lock_key = f"device_op_lock:{device_id}"

        if r:
            lock = r.lock(
                lock_key,
                timeout=timeout * 2,  # 自动释放时间 = 操作超时的2倍
                blocking_timeout=timeout,  # 等待时间 = 操作超时
            )
            acquired = lock.acquire(blocking=True)
            if not acquired:
                raise DeviceOperationConflict(
                    f"设备 {device_id} 当前有 SSH 操作正在执行，请稍后重试（超时 {timeout}s）"
                )
            try:
                yield
            finally:
                try:
                    lock.release()
                except Exception:
                    logger.warning("释放设备 %s 分布式锁失败 key=%s", device_id, lock_key, exc_info=True)
        else:
            lock = self._get_local_lock(lock_key)
            acquired = lock.acquire(timeout=timeout)
            if not acquired:
                raise DeviceOperationConflict(
                    f"设备 {device_id} 当前有 SSH 操作正在执行，请稍后重试"
                )
            try:
                yield
            finally:
                lock.release()


device_op_lock = DeviceOpLock()
