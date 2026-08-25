# -*- coding: utf-8 -*-
"""
通知外部渠道后台投递线程

不引入任务队列中间件（Celery/RQ）——量级上，通知投递不需要跨进程/持久化重试，
一个进程内的 queue.Queue + 单条守护线程完全够用，风格与 notification_cleanup.py
的 threading.Timer 方案保持一致。

多进程部署（gunicorn -w N）下每个 worker 各自有一条独立的投递线程 + 独立队列，
互不影响——这里不需要像 SSE 场景那样做跨进程统一（投递没有"顺序/去重必须全局
一致"的硬要求，冷却窗口按进程各自维护即可接受轻微的过量发送，好过复杂的跨进程协调）。
"""
from app.core.enums import ChannelType
from app.utils.logging import get_logger
import queue
import threading
import time

logger = get_logger(__name__)

_delivery_queue: "queue.Queue[dict]" = queue.Queue(maxsize=1000)
_cooldown_cache: dict[str, float] = {}
_COOLDOWN_SECONDS = 300

_RATE_LIMIT_POLL_INTERVAL = 60
DELIVERY_TIMEOUT = 5
_seen_rate_limit_alerts: set[str] = set()
_rate_limit_alerts_last_clear = 0.0


def enqueue_delivery(notification_id: int, user_ids: list[int]) -> None:
    try:
        _delivery_queue.put_nowait({"notification_id": notification_id, "user_ids": user_ids})
    except queue.Full:
        try:
            _delivery_queue.put({"notification_id": notification_id, "user_ids": user_ids}, timeout=1)
        except queue.Full:
            logger.critical(
                "通知投递队列已满，丢弃外部渠道投递任务(死信) notification_id=%s",
                notification_id,
            )


def _drain_queue(app) -> None:
    drained = 0
    while not _delivery_queue.empty():
        try:
            task = _delivery_queue.get_nowait()
        except queue.Empty:
            break
        try:
            _process_one(app, task)
            drained += 1
        except Exception:
            logger.exception("停机排空时投递失败 notification_id=%s", task.get("notification_id"))
    if drained:
        logger.info("通知投递队列停机排空完成: %d 条", drained)


def _should_skip_cooldown(type_: str, source_module: str | None) -> bool:
    key = f"{type_}:{source_module or ''}"
    now = time.time()
    last = _cooldown_cache.get(key)
    if last is not None and now - last < _COOLDOWN_SECONDS:
        return True
    _cooldown_cache[key] = now
    return False


def _process_one(app, task: dict) -> None:
    from app.models.notification import Notification, NotificationReceipt
    from app.models.user import User
    from app.services.notification_service import NotificationService
    from extensions import db

    try:
        with app.app_context():
            notification = Notification.query.get(task["notification_id"])
            if not notification:
                return

            in_cooldown = _should_skip_cooldown(notification.type, notification.source_module)

            if not in_cooldown:
                for channel in NotificationService.get_broadcast_channels():
                    try:
                        channel.send(notification)
                    except Exception:
                        logger.exception("广播渠道 %s 投递失败", channel.get_channel_name())

            for uid in task["user_ids"]:
                receipt = NotificationReceipt.query.filter_by(
                    notification_id=notification.id, user_id=uid
                ).first()
                user = User.query.get(uid)
                if not receipt or not user:
                    continue

                status = dict(receipt.channel_status or {})

                for channel in NotificationService.get_personal_channels():
                    name = channel.get_channel_name()
                    if name == ChannelType.INBOX:
                        status[name] = "ok"
                        continue
                    if not channel.is_available(user):
                        status[name] = "skipped:unavailable"
                        continue
                    if in_cooldown:
                        status[name] = "skipped:cooldown"
                        continue
                    try:
                        ok = channel.send(notification, receipt, user)
                        status[name] = "ok" if ok else "failed:unknown"
                    except Exception as exc:
                        logger.exception("渠道 %s 投递失败 user_id=%s", name, uid)
                        status[name] = f"failed:{exc}"

                from sqlalchemy.orm.attributes import flag_modified
                receipt.channel_status = status
                flag_modified(receipt, "channel_status")

            db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("通知投递结果落库失败 notification_id=%s", task.get("notification_id"))


def _poll_rate_limit_alerts(app) -> None:
    global _rate_limit_alerts_last_clear

    try:
        from app.utils.rate_limiting.limiter import UnifiedRateLimiter
        from app.services.ops_alert_bridge import bridge_rate_limit_alert
    except ImportError:
        return

    with app.app_context():
        try:
            from app.utils.auth import rate_limiter
            if not hasattr(rate_limiter, 'storage'):
                return
            monitor = getattr(rate_limiter, '_monitor', None)
            if monitor is None or not hasattr(monitor, 'get_alerts'):
                return
            alerts = monitor.get_alerts()
        except Exception:
            return

        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            alert_key = f"{alert.get('key', '')}:{alert.get('endpoint', '')}"
            if alert_key in _seen_rate_limit_alerts:
                continue
            _seen_rate_limit_alerts.add(alert_key)
            try:
                bridge_rate_limit_alert(alert)
            except Exception:
                logger.exception("限流告警桥接失败")

        now = time.time()
        if now - _rate_limit_alerts_last_clear > 21600:
            _seen_rate_limit_alerts.clear()
            _rate_limit_alerts_last_clear = now


def _delivery_loop(app) -> None:
    last_rate_limit_poll = 0.0

    while True:
        try:
            task = _delivery_queue.get(timeout=DELIVERY_TIMEOUT)
            _process_one(app, task)
        except queue.Empty:
            pass
        except Exception:
            logger.exception("通知投递线程异常，继续循环")

        now = time.time()
        if now - last_rate_limit_poll > _RATE_LIMIT_POLL_INTERVAL:
            last_rate_limit_poll = now
            try:
                _poll_rate_limit_alerts(app)
            except Exception:
                logger.exception("RateLimitMonitor 轮询失败")


def start_delivery_worker(app) -> None:
    import atexit
    atexit.register(lambda: _drain_queue(app))
    thread = threading.Thread(target=_delivery_loop, args=(app,), daemon=True)
    thread.start()
    logger.info("通知投递后台线程已启动")
