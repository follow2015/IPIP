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

    _local_locks: dict[int, threading.Lock] = {}
    _meta_lock = threading.Lock()

    def _get_local_lock(self, device_id: int) -> threading.Lock:
        """获取或创建设备级线程锁"""
        with self._meta_lock:
            if device_id not in self._local_locks:
                self._local_locks[device_id] = threading.Lock()
            return self._local_locks[device_id]

    @contextlib.contextmanager
    def acquire(self, device_id: int, timeout: float = 60.0):
        """获取设备操作锁

        Args:
            device_id: 要锁定的设备 ID
            timeout:   等待超时（秒）

        Raises:
            DeviceOperationConflict: 超时无法获取锁（设备繁忙）

        Usage:
            with device_op_lock.acquire(switch.device_id):
        """
        from app.services.switch_events import _get_redis
        r = _get_redis()

        if r:
            lock_key = f"device_op_lock:{device_id}"
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
