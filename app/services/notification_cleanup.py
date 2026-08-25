# -*- coding: utf-8 -*-
"""
通知定时清理服务

不依赖 MySQL EVENT（需要 SYSTEM_USER 权限），
也不引入 APScheduler 等新依赖，
使用 Python 标准库 threading.Timer 实现轻量定时清理。

在 Flask create_app() 中调用 start_cleanup_scheduler() 启动。
"""
from app.utils.logging import get_logger
import threading
import time
from datetime import datetime, timedelta, timezone

logger = get_logger(__name__)

CLEANUP_INTERVAL = int(__import__('os').environ.get('NOTIFICATION_CLEANUP_INTERVAL', 86400))

RETENTION_DAYS = 90


def cleanup_notifications():
    from app.persistence.notification_repository import NotificationRepository, NotificationReceiptRepository

    try:
        notif_repo = NotificationRepository()
        receipt_repo = NotificationReceiptRepository()
        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)

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


def _cleanup_loop():
    while True:
        try:
            time.sleep(CLEANUP_INTERVAL)
            cleanup_notifications()
        except Exception as exc:
            logger.warning("通知清理线程异常: %s", exc)


def start_cleanup_scheduler(app):
    def _run_with_app_context():
        with app.app_context():
            _cleanup_loop()

    thread = threading.Thread(target=_run_with_app_context, daemon=True)
    thread.start()
    logger.info("通知清理线程已启动 (间隔=%ds, 保留=%d天)", CLEANUP_INTERVAL, RETENTION_DAYS)
