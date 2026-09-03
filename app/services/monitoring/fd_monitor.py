# -*- coding: utf-8 -*-
"""进程级文件描述符（FD）监控。

长期运行的监控进程若发生 socket/线程泄漏（如极端场景遗弃的 daemon 线程），
FD 数会持续攀升并最终耗尽，导致后续探测/连接全部失败。本模块提供一个轻量后台
daemon 线程，周期读取 Linux 的 ``/proc/self/fd`` 目录计数，超过阈值仅发
``critical`` 告警——**不**自动退出。

设计取舍（与 ``app/services/monitoring/adapters/base_adapter.py`` 的孤儿线程计数
告警策略一致）：本项目不走 k8s/docker 编排，进程退出后无人拉起会导致监控**永久宕机**，
故 FD 超限只告警、不 ``os._exit``，交由运维按告警人工重启回收资源。

非 Linux 平台（macOS / Windows 开发机）无 ``/proc/self/fd``，自动降级为 no-op。
"""
from app.utils.logging import get_logger
import os
import threading
import time

logger = get_logger(__name__)

_fd_monitor_lock = threading.Lock()
_fd_monitor_thread = None
_fd_monitor_started = False

DEFAULT_FD_WARN_THRESHOLD = 1024
DEFAULT_FD_CHECK_INTERVAL = 30.0

_PROC_SELF_FD = "/proc/self/fd"


def _count_open_fds() -> "int | None":
    """返回当前进程打开的 FD 数；不支持的平台（无 /proc）返回 None。"""
    if not os.path.isdir(_PROC_SELF_FD):
        return None
    try:
        return len(os.listdir(_PROC_SELF_FD))
    except OSError:
        return None


def _fd_monitor_loop(threshold: int, interval: float, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            count = _count_open_fds()
            if count is None:
                logger.debug("FD 监控：当前平台无 %s，停止监控线程", _PROC_SELF_FD)
                return
            if count >= threshold:
                logger.critical(
                    "监控进程打开的 FD 数达 %d（阈值 %d），疑似 socket/线程泄漏；"
                    "请排查对端或网络，必要时人工重启监控进程回收资源。",
                    count, threshold,
                )
        except Exception:  # noqa: BLE001 - 监控线程自身不得因异常退出
            logger.warning("FD 监控线程异常", exc_info=True)
        stop_event.wait(interval)


def start_fd_monitor(
    threshold: int = DEFAULT_FD_WARN_THRESHOLD,
    interval: float = DEFAULT_FD_CHECK_INTERVAL,
    stop_event: "threading.Event | None" = None,
) -> bool:
    """启动 FD 监控后台线程（幂等，全程仅启动一次）。

    返回 True 表示本次实际新建并启动了线程；已在运行 / 平台不支持则返回 False。
    """
    global _fd_monitor_thread, _fd_monitor_started
    with _fd_monitor_lock:
        if _fd_monitor_started:
            return False
        if _count_open_fds() is None:
            logger.debug("FD 监控：当前平台不支持 %s，跳过启动", _PROC_SELF_FD)
            _fd_monitor_started = True  # 已决策，避免重复尝试
            return False
        if stop_event is None:
            stop_event = threading.Event()
        _fd_monitor_thread = threading.Thread(
            target=_fd_monitor_loop,
            args=(threshold, interval, stop_event),
            name="monitor-fd-watch",
            daemon=True,
        )
        _fd_monitor_thread.start()
        _fd_monitor_started = True
        logger.info("FD 监控线程已启动（阈值=%d，间隔=%.0fs）", threshold, interval)
        return True


def reset_fd_monitor_for_test() -> None:
    """测试专用：重置单例状态，允许再次 start（不停止已运行的线程）。"""
    global _fd_monitor_thread, _fd_monitor_started
    with _fd_monitor_lock:
        _fd_monitor_thread = None
        _fd_monitor_started = False
