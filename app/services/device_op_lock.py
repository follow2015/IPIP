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
    pass


class DeviceOpLock:

    _local_locks: dict[int, threading.Lock] = {}
    _meta_lock = threading.Lock()

    def _get_local_lock(self, device_id: int) -> threading.Lock:
        with self._meta_lock:
            if device_id not in self._local_locks:
                self._local_locks[device_id] = threading.Lock()
            return self._local_locks[device_id]

    @contextlib.contextmanager
    def acquire(self, device_id: int, timeout: float = 60.0):
        from app.services.switch_events import _get_redis
        r = _get_redis()

        if r:
            lock_key = f"device_op_lock:{device_id}"
            lock = r.lock(
                lock_key,
                timeout=timeout * 2,
                blocking_timeout=timeout,
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
                    logger.warning("释放设备 %s 分布式锁失败", device_id, exc_info=True)
        else:
            lock = self._get_local_lock(device_id)
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
