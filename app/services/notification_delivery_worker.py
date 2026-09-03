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
_COOLDOWN_SECONDS = 300  # 同 type+source+channel 5 分钟内只投递一次，inbox 不受影响

_RATE_LIMIT_POLL_INTERVAL = 60  # RateLimitMonitor 轮询间隔（秒）
DELIVERY_TIMEOUT = 5  # 投递队列拉取超时时间（秒）
_seen_rate_limit_alerts: set[str] = set()  # 已通知过的限流告警去重游标
_rate_limit_alerts_last_clear = 0.0  # 上次清空去重集合的时间戳


def enqueue_delivery(notification_id: int, user_ids: list[int]) -> None:
    """由 notify() 在 DB 提交后调用，非阻塞入队。

    队列满（maxsize=1000）属极端情况：先尽力阻塞 1s 入队以减少丢失，
    仍失败则记 critical 死信日志（不再静默丢弃）。中长期应迁移到 DB outbox。
    """
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
    """进程退出前尽力排空队列（best-effort，无法应对 SIGKILL）。

    多 worker 部署下每个进程各自排空自己的内存队列；无法覆盖崩溃场景，
    中长期应以 DB outbox 替代内存队列实现持久化。
    """
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


def _get_cooldown_redis():
    """获取冷却用 Redis 客户端；不可用时返回 None。

    项目没有 `extensions.redis_client`：Redis 统一经
    `app.services.switch_events._get_redis()` 获取，与 AI 模块的
    task_state / task_idempotency / circuit_breaker 同一惯例。
    """
    from app.services.switch_events import _get_redis

    try:
        return _get_redis()
    except Exception:
        logger.warning("冷却 Redis 客户端获取失败，本次不冷却", exc_info=True)
        return None


def _should_skip_cooldown(type_: str, source_module: str | None, channel_name: str) -> bool:
    """检查同 type+source+channel 是否在冷却窗口内（Redis 化）。

    P1-fix: 冷却键加渠道维度，避免邮件挡住语音；Redis 实现多 worker 共享冷却状态。

    Returns:
        True = 应跳过（在冷却窗口内），False = 可以发送
    """
    redis_client = _get_cooldown_redis()
    if redis_client is None:
        return False  # 降级：宁可多发，不可因 Redis 故障中断全部外部渠道

    key = f"cooldown:{type_}:{source_module or ''}:{channel_name}"
    try:
        return not redis_client.set(key, str(time.time()), ex=_COOLDOWN_SECONDS, nx=True)
    except Exception:
        logger.warning("冷却状态读写失败，降级为不冷却 key=%s", key, exc_info=True)
        return False


def _process_one(app, task: dict) -> None:
    """处理一条投递任务"""
    from app.models.notification import Notification, NotificationReceipt
    from app.models.user import User
    from app.services.notification_service import NotificationService
    from extensions import db

    try:
        with app.app_context():
            notification = Notification.query.get(task["notification_id"])
            if not notification:
                return

            for channel in NotificationService.get_broadcast_channels():
                ch_name = channel.get_channel_name()
                if _should_skip_cooldown(notification.type, notification.source_module, ch_name):
                    logger.debug("广播渠道 %s 命中冷却，跳过", ch_name)
                    continue
                try:
                    ok = channel.send(notification)
                    if not ok:
                        logger.warning(
                            "广播渠道 %s 投递未成功（无匹配配置或全部失败）"
                            " notification_id=%s", ch_name, notification.id,
                        )
                except Exception:
                    logger.exception("广播渠道 %s 投递失败", ch_name)

            cooldown_decisions: dict[str, bool] = {
                ch.get_channel_name(): _should_skip_cooldown(
                    notification.type, notification.source_module, ch.get_channel_name()
                )
                for ch in NotificationService.get_personal_channels()
                if ch.get_channel_name() != ChannelType.INBOX
            }

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
                        status[name] = "ok"  # inbox 已在 notify() 主流程里落库
                        continue
                    if not channel.is_available(user):
                        status[name] = "skipped:unavailable"
                        continue
                    if cooldown_decisions.get(name):
                        status[name] = "skipped:cooldown"
                        continue
                    try:
                        _t0 = time.perf_counter()
                        ok = channel.send(notification, receipt, user)
                        _duration_ms = int((time.perf_counter() - _t0) * 1000)
                        status.update(dict(receipt.channel_status or {}))
                        if name == ChannelType.VOICE and ok:
                            pass
                        else:
                            status[name] = "ok" if ok else "failed:unknown"
                        logger.info(
                            "渠道投递完成 channel=%s user_id=%s duration_ms=%d ok=%s",
                            name, uid, _duration_ms, ok,
                        )
                    except Exception as exc:
                        logger.exception("渠道 %s 投递失败 user_id=%s", name, uid)
                        status.update(dict(receipt.channel_status or {}))
                        status[name] = f"failed:{type(exc).__name__}"

                from sqlalchemy.orm.attributes import flag_modified
                receipt.channel_status = status
                flag_modified(receipt, "channel_status")

            db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("通知投递结果落库失败 notification_id=%s", task.get("notification_id"))


def _poll_rate_limit_alerts(app) -> None:
    """RateLimitMonitor 轮询桥接

    RateLimitMonitor 目前只有 get_alerts() 拉取接口，没有回调机制，
    这里用轮询 + 内容去重的方式桥接。
    """
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
        if now - _rate_limit_alerts_last_clear > 21600:  # 6 小时
            _seen_rate_limit_alerts.clear()
            _rate_limit_alerts_last_clear = now


def _delivery_loop(app) -> None:
    """后台投递线程主循环"""
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
    """启动后台投递线程（应在 create_app() 中调用）"""
    import atexit
    atexit.register(lambda: _drain_queue(app))  # 进程退出前尽力排空，减少通知丢失
    thread = threading.Thread(target=_delivery_loop, args=(app,), daemon=True)
    thread.start()
    logger.info("通知投递后台线程已启动")
