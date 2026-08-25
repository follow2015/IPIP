# -*- coding: utf-8 -*-
"""监控告警发件箱轮询发送器（进程内，解耦事务与投递）

由监控 worker（in-Flask）与独立微服务（StandaloneMonitorService）各自在独立
daemon 线程内启动一个 ``MonitorOutboxSender.run_loop``：周期性读取
``monitor_alert_outbox`` 中 ``status='pending'`` 的行，调用
``notification_service.notify_strict`` 投递，成功后标记 ``sent``。
（必须用 ``notify_strict`` 而非 ``notify``：后者吞掉投递异常返回 None，与幂等
去重的 None 无法区分，会把失败行误标 ``sent``，告警永久静默丢失。）

设计要点（与项目部署约束一致）：
- 本项目不走 k8s/docker（无容器编排），不依赖「进程崩溃靠编排重启回收」；
  发件器自带独立线程、独立会话、失败重试（attempts 上限后置 failed），无需外部
  supervisor 即可自愈。
- 「至少一次投递」：崩溃重放时 notify 的 ``idempotency_key`` 幂等去重，不会
  产生重复通知（见 notification_service.notify 的幂等检查）。
"""
import json
import logging
import threading
from datetime import datetime, timezone

from app.models.monitor_alert_outbox import MonitorAlertOutbox
from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _invoke_notify(notify, payload: dict) -> None:
    """按「严格投递」语义调用通知服务，兼容多种注入形式。

    优先 ``notify_strict``：真实投递失败会抛异常，可与幂等去重返回的 ``None``
    区分开（P0-1）。若用 ``notify``，异常被吞成 ``None``，发件器无法判定结果，
    会把失败行误标 ``sent`` → 告警静默丢失。

    退化顺序：``notify_strict`` → ``.notify`` → 裸可调用（兼容测试假对象）。
    """
    fn = getattr(notify, "notify_strict", None)
    if callable(fn):
        fn(**payload)
        return
    fn = getattr(notify, "notify", None)
    if callable(fn):
        logger.warning(
            "outbox _invoke_notify 退化到 notify()（无 notify_strict），"
            "投递失败可能被误标 sent；请确保 notify 对象提供 notify_strict 方法"
        )
        fn(**payload)
        return
    notify(**payload)


class MonitorOutboxSender:
    """进程内发件轮询器：把 outbox 待发行转成真实通知。"""

    LOCK_NAME = "outbox"

    def __init__(self, notify=None, repo=None, batch_size: int = 100,
                 max_attempts: int = 5, interval: float = 5.0,
                 redis_client=None, dead_letter_retry_hours: int = 24):
        self._notify = notify
        self._repo = repo
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self.interval = interval
        self._redis = redis_client
        self._redis_resolved = redis_client is not None
        self.dead_letter_retry_hours = dead_letter_retry_hours

    def _notify_service(self):
        if self._notify is not None:
            return self._notify
        from app.services.notification_service import notification_service
        return notification_service


    def _lock_ttl(self) -> int:
        """互斥锁 TTL：覆盖一轮发送耗时，同时保证崩溃后快速接管。"""
        return max(int(self.interval * 4), 60)

    def _get_redis(self, app):
        """惰性解析 Redis 客户端（失败返回 None，走降级路径）。"""
        if self._redis_resolved:
            return self._redis
        self._redis_resolved = True
        try:
            from app.services.monitoring.monitor_worker import _redis_client

            self._redis = _redis_client(app)
        except Exception:
            logger.warning("outbox 发件器 Redis 客户端构建失败（降级为无互斥）", exc_info=True)
            self._redis = None
        return self._redis

    def _acquire_round_lock(self, app) -> bool:
        """抢占本轮发送的进程间互斥锁。

        为什么需要（P0-3）：``find_pending`` 只是普通 SELECT，而发件线程在
        **每个 gunicorn worker 里各起一个**，多进程并发会拉到同一批 pending 行 →
        重复投递 + ``attempts`` 并发自增竞态（可能未满 max_attempts 就被判 failed）。

        降级策略：Redis 不可用时**继续发送**（返回 True）而非跳过——告警投递
        停摆的代价远高于重复投递，且重复投递会被 notify 的 ``idempotency_key``
        幂等去重挡住（与探测循环 ``MONITOR_REDIS_DOWN_MODE`` 默认 skip 的取舍不同：
        探测双跑会放大全网负载，发件双跑只是幂等重试）。
        """
        from flask import current_app

        if not current_app.config.get("MONITOR_OUTBOX_LOCK_ENABLED", True):
            return True
        r = self._get_redis(app)
        if r is None:
            return True
        try:
            from app.services.monitoring.monitor_worker import lock_owner_token

            ok = bool(r.set(
                f"monitor:lock:{self.LOCK_NAME}", lock_owner_token(),
                nx=True, ex=self._lock_ttl(),
            ))
            if not ok:
                logger.debug("outbox 本轮互斥锁被其他进程持有，跳过")
            return ok
        except Exception:
            logger.warning("outbox 互斥锁获取失败（降级为无互斥继续发送）", exc_info=True)
            return True

    def _release_round_lock(self) -> None:
        """释放互斥锁（Lua CAS，仅当仍由本进程持有）。"""
        if self._redis is None:
            return
        try:
            from app.services.monitoring.monitor_worker import _release_lock

            _release_lock(self._redis, self.LOCK_NAME)
        except Exception:
            logger.warning("outbox 互斥锁释放失败（TTL 兜底过期）", exc_info=True)

    def send_pending(self, app, session=None) -> int:
        """在 app context 内投递所有 pending 行，返回成功发送数。

        ``session`` 缺省时用全局 db.session（线程局部，独立于轮询线程）。
        每条：解析 payload → notify → 成功标记 sent，异常标记 failed/重试。
        失败行单独 rollback 后继续处理其余行；成功行每 commit_every 条批量提交，
        减少 DB 压力（替代逐行 commit）。
        """
        notify = self._notify_service()
        sent = 0
        commit_every = 10  # 每 10 条成功行批量提交一次
        with app.app_context():
            if session is None:
                from extensions import db
                session = db.session
            if not self._acquire_round_lock(app):
                return 0
            try:
                if self._repo is None:
                    self._repo = MonitorAlertOutboxRepository(session=session)
                repo = self._repo
                rows = repo.find_pending(self.batch_size)
                for row in rows:
                    try:
                        payload = json.loads(row.payload_json)
                        _invoke_notify(notify, payload)
                    except Exception as e:  # 单条失败不影响其余行
                        try:
                            repo.mark_failed(row.id, str(e)[:500], self.max_attempts)
                            session.commit()  # 隔离提交 failed 标记
                        except Exception:
                            logger.warning(
                                "监控告警 outbox mark_failed 也失败 row=%s，本条留待下次重试",
                                row.id, exc_info=True,
                            )
                            session.rollback()  # 仅回滚本条未决写入
                        else:
                            logger.warning(
                                "监控告警 outbox 投递失败 row=%s device=%s: %s",
                                row.id, row.device_id, e,
                            )
                        continue
                    repo.mark_sent(row.id, datetime.now(timezone.utc))
                    sent += 1
                    if sent % commit_every == 0:
                        try:
                            session.commit()
                        except Exception:
                            logger.warning("outbox 批量提交失败，rollback 后继续", exc_info=True)
                            session.rollback()
                if sent % commit_every != 0:
                    try:
                        session.commit()
                    except Exception:
                        logger.warning("outbox 末尾提交失败", exc_info=True)
                        session.rollback()
                try:
                    if self._repo is not None:
                        reset_count = self._repo.reset_all_failed(
                            max_age_hours=self.dead_letter_retry_hours
                        )
                        if reset_count > 0:
                            session.commit()
                            logger.info("outbox 死信恢复：重置 %d 条失败行为 pending", reset_count)
                except Exception:
                    logger.warning("outbox 死信恢复失败", exc_info=True)

                try:
                    from app.services.monitoring.escalation_service import run_escalation_scan
                    upgraded = run_escalation_scan()
                    if upgraded > 0:
                        session.commit()
                        logger.info("告警升级扫描：升级 %d 条告警", upgraded)
                except Exception:
                    logger.warning("告警升级扫描失败", exc_info=True)
                    session.rollback()
            finally:
                self._release_round_lock()
                try:
                    from extensions import db
                    db.session.remove()
                except Exception:
                    logger.warning("outbox session.remove 失败", exc_info=True)
        return sent

    def run_loop(self, app, stop_event: threading.Event) -> None:
        """守护线程入口：周期性 send_pending，stop_event 置位即退出。

        每轮动态读取 MONITOR_OUTBOX_INTERVAL（热重载，无需重启）。
        """
        while not stop_event.is_set():
            try:
                self.send_pending(app)
            except Exception:
                logger.error("监控告警 outbox 发送循环异常")
                try:
                    if self._repo is not None:
                        self._repo.session.rollback()
                except Exception:
                    logger.warning("outbox 发送异常后 rollback 失败", exc_info=True)
            try:
                with app.app_context():
                    from app.services.monitoring.dynamic_config import MonitorDynamicConfig

                    iv = MonitorDynamicConfig.get("MONITOR_OUTBOX_INTERVAL")
                if iv is not None:
                    self.interval = float(iv)
            except Exception:
                logger.warning("outbox interval 热重载读取失败（沿用旧值）", exc_info=True)
            stop_event.wait(self.interval)
