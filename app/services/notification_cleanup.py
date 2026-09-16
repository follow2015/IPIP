# -*- coding: utf-8 -*-
"""通知定时清理服务

不依赖 MySQL EVENT（需要 SYSTEM_USER 权限），
也不引入 APScheduler 等新依赖，
使用 Python 标准库 threading 实现轻量定时清理。

在 Flask create_app() 中调用 start_cleanup_scheduler() 启动。

多进程部署（gunicorn -w N）下**每个 worker 都会调用 create_app()**，因此每个
worker 各有一条清理线程。每轮清理前用 Redis `SET NX EX` 选举 leader，只有抢到
锁的 worker 执行本轮 —— 消除 N 倍无谓 DB 负载与 DELETE 持锁竞争（P1-7）。

停机走 `_stop_event`（`wait()` 而非 `sleep()`），`stop_cleanup_scheduler()`
请求退出并 join，对齐 monitor_worker 的水准（P2-19）。
"""
from __future__ import annotations

import atexit
import os
import threading
from datetime import timedelta

from app.utils.logging import get_logger
from app.utils.time_utils import now_utc_naive

logger = get_logger(__name__)

CLEANUP_INTERVAL = int(os.environ.get('NOTIFICATION_CLEANUP_INTERVAL', 86400))

RETENTION_DAYS = 90

LEADER_KEY = "notification_cleanup:leader"
LEADER_TTL = 3600

STOP_JOIN_TIMEOUT = 5.0

_stop_event = threading.Event()
_thread: threading.Thread | None = None
_atexit_registered = False


def cleanup_notifications():
    """执行一次通知清理：删除 90 天前的已读已确认回执 + 孤立通知主体。"""
    from app.persistence.notification_repository import NotificationRepository, NotificationReceiptRepository

    notif_repo = NotificationRepository()
    receipt_repo = NotificationReceiptRepository()

    try:
        cutoff = now_utc_naive() - timedelta(days=RETENTION_DAYS)

        deleted_receipts = receipt_repo.delete_read_acked_before(cutoff)

        deleted_notifications = notif_repo.delete_orphans_before(cutoff)

        notif_repo.session.commit()
        if deleted_receipts or deleted_notifications:
            logger.info(
                "通知清理完成: 删除回执=%d, 删除通知=%d",
                deleted_receipts, deleted_notifications,
            )
    except Exception as exc:
        notif_repo.session.rollback()
        logger.warning("通知清理失败: %s", exc)


def _try_acquire_leader():
    """尝试成为本轮清理的 leader。

    Returns:
        tuple[bool, object | None]：(本轮是否应执行清理, 抢到的 Redis 客户端)。
        第二个元素仅在**确实抢到锁**时非 None，供本轮结束释放；fail-open 时为
        None（无锁可释放）。

    设计取舍：
    - 抢锁沿用 scan_scheduler / monitor_worker 已验证的 `SET NX EX` 模式，释放
      复用 `app/utils/concurrency/redis_lock.py` 的 owner token + Lua CAS，
      保证不会误删他人的锁。
    - **不做心跳续约**：一轮清理是秒级幂等 DELETE，TTL 内必然结束；即使极端
      情况超时被别的 worker 重跑，删除条件（`created_at < cutoff AND is_read
      AND is_acked`）幂等，无正确性影响。续约线程只会增加停机复杂度。
    - **Redis 不可用时 fail-open**（返回 True 执行）：清理幂等，多跑一轮只是多
      一次 DB 负载；反之 fail-close 会让 90 天前的回执永远清不掉（只增不减）。
      取舍与 `outbox_sender._acquire_round_lock` 的 fail-open 一致。
    """
    from app.utils.concurrency.redis_lock import owner_token
    from app.utils.redis_client import get_redis_client

    r = get_redis_client()
    if r is None:
        logger.debug("通知清理：Redis 不可用，跳过 leader 选举直接执行（fail-open）")
        return True, None
    try:
        acquired = r.set(LEADER_KEY, owner_token(), nx=True, ex=LEADER_TTL)
    except Exception as exc:  # noqa: BLE001 - 选举失败不阻断清理（清理幂等）
        logger.warning("通知清理：leader 选举失败，降级为执行本轮: %s", exc)
        return True, None
    if not acquired:
        return False, None
    return True, r


def _release_leader(redis_client) -> None:
    """释放本轮 leader 锁（Lua CAS：只删仍属于自己的锁）。"""
    if redis_client is None:
        return
    from app.utils.concurrency.redis_lock import release_owner_lock

    try:
        release_owner_lock(redis_client, LEADER_KEY)
    except Exception as exc:  # noqa: BLE001 - 释放失败由 TTL 兜底
        logger.warning("通知清理：leader 锁释放失败（TTL 兜底过期）: %s", exc)


def _cleanup_tick() -> bool:
    """一轮清理：选举 → 执行 → 释放。

    Returns:
        bool：本轮是否实际执行了清理（False = 另有 worker 持锁）。
    """
    should_run, redis_client = _try_acquire_leader()
    if not should_run:
        logger.debug("通知清理：本进程未抢到 leader，跳过本轮（另有 worker 在执行）")
        return False
    try:
        cleanup_notifications()
    finally:
        _release_leader(redis_client)
    return True


def _cleanup_loop():
    """定时清理循环（后台守护线程）。

    用 `_stop_event.wait(interval)` 而非 `time.sleep(interval)`：停机信号能立刻
    中断等待，进程退出前不必等满一个（默认 24 小时）间隔。
    """
    while not _stop_event.wait(CLEANUP_INTERVAL):
        try:
            _cleanup_tick()
        except Exception as exc:
            logger.warning("通知清理线程异常: %s", exc)


def start_cleanup_scheduler(app) -> threading.Event:
    """启动通知清理后台线程。

    应在 create_app() 中调用，传入 Flask app 实例
    （用于确保 application context 可用）。

    Args:
        app: Flask 应用实例

    Returns:
        threading.Event：停机事件（已注册 atexit 优雅停机，返回值仅供需要
        显式控制停机的调用方/测试使用）。
    """
    global _thread, _atexit_registered

    if _thread is not None and _thread.is_alive():
        logger.debug("通知清理线程已在运行，跳过重复启动")
        return _stop_event

    _stop_event.clear()

    def _run_with_app_context():
        with app.app_context():
            _cleanup_loop()

    _thread = threading.Thread(
        target=_run_with_app_context, name="notification-cleanup", daemon=True,
    )
    _thread.start()

    if not _atexit_registered:
        atexit.register(stop_cleanup_scheduler)
        _atexit_registered = True

    logger.info(
        "通知清理线程已启动 (间隔=%ds, 保留=%d天, leader 键=%s)",
        CLEANUP_INTERVAL, RETENTION_DAYS, LEADER_KEY,
    )
    return _stop_event


def stop_cleanup_scheduler(timeout: float = STOP_JOIN_TIMEOUT) -> None:
    """请求停机并等待清理线程退出（幂等，可重复调用）。

    Args:
        timeout: join 等待上限（秒）。超时仅告警不阻塞退出。
    """
    _stop_event.set()
    thread = _thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning("通知清理线程未在 %.1fs 内退出（非阻塞退出）", timeout)
