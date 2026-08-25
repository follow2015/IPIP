# -*- coding: utf-8 -*-
"""
统一消息通知服务

业务代码只调用 notification_service.notify() 一个入口产生通知，
不再各自决定"怎么提示用户"。

P0 实现 inbox 渠道（站内信持久化），P2 扩展 email/webhook 等。
P2 修订：外部渠道（email/webhook）改为后台线程异步投递，不阻塞主业务请求。
"""
from app.utils.logging import get_logger
from datetime import datetime, timezone

from app.core.enums import ChannelType, PERSONAL_CHANNELS, SeverityLevel
from app.models.notification import Notification, NotificationReceipt
from app.models.user import User
from app.core.enums import UserStatus
from app.models.rbac import Role, UserRole
from app.persistence.notification_repository import NotificationRepository, NotificationReceiptRepository
from app.persistence.user_repository import UserRepository

logger = get_logger(__name__)


class NotificationService:

    def __init__(self, notif_repo: NotificationRepository = None,
                 receipt_repo: NotificationReceiptRepository = None,
                 user_repo: UserRepository = None):
        self._notif_repo = notif_repo or NotificationRepository()
        self._receipt_repo = receipt_repo or NotificationReceiptRepository()
        self._user_repo = user_repo or UserRepository()

    _personal_channel_registry: dict[str, "PersonalChannel"] = {}
    _broadcast_channel_registry: dict[str, "BroadcastChannel"] = {}

    @classmethod
    def register_personal_channel(cls, channel: "PersonalChannel"):
        cls._personal_channel_registry[channel.get_channel_name()] = channel

    @classmethod
    def register_broadcast_channel(cls, channel: "BroadcastChannel"):
        cls._broadcast_channel_registry[channel.get_channel_name()] = channel

    @classmethod
    def get_personal_channels(cls) -> list["PersonalChannel"]:
        return list(cls._personal_channel_registry.values())

    @classmethod
    def get_broadcast_channels(cls) -> list["BroadcastChannel"]:
        return list(cls._broadcast_channel_registry.values())


    def notify(
        self,
        type: str,
        severity: str = SeverityLevel.INFO,
        title: str = "",
        content: str | None = None,
        payload: dict | None = None,
        source_module: str | None = None,
        target_type: str = "user",
        target_id: str | int | None = None,
        channels: tuple[str, ...] = (ChannelType.INBOX,),
        idempotency_key: str | None = None,
        ack_required: bool = False,
        allow_broadcast: bool = True,
    ) -> Notification | None:
        try:
            return self.notify_strict(
                type=type, severity=severity, title=title, content=content,
                payload=payload, source_module=source_module,
                target_type=target_type, target_id=target_id, channels=channels,
                idempotency_key=idempotency_key, ack_required=ack_required,
                allow_broadcast=allow_broadcast,
            )
        except Exception:
            logger.warning(
                "通知投递失败（已忽略，不影响主流程）: type=%s target=%s:%s",
                type, target_type, target_id,
            )
            return None

    def notify_strict(
        self,
        type: str,
        severity: str = SeverityLevel.INFO,
        title: str = "",
        content: str | None = None,
        payload: dict | None = None,
        source_module: str | None = None,
        target_type: str = "user",
        target_id: str | int | None = None,
        channels: tuple[str, ...] = (ChannelType.INBOX,),
        idempotency_key: str | None = None,
        ack_required: bool = False,
        allow_broadcast: bool = True,
    ) -> Notification | None:
        try:
            return self._notify_inner(
                type, severity, title, content, payload, source_module,
                target_type, target_id, channels, idempotency_key, ack_required,
                allow_broadcast,
            )
        except Exception:
            logger.error(
                "通知投递失败: type=%s target=%s:%s",
                type, target_type, target_id, exc_info=True,
            )
            try:
                self._notif_repo.session.rollback()
            except Exception:
                logger.warning("通知投递失败后回滚数据库失败", exc_info=True)
            raise

    def _notify_inner(
        self,
        type: str,
        severity: str,
        title: str,
        content: str | None,
        payload: dict | None,
        source_module: str | None,
        target_type: str,
        target_id: str | int | None,
        channels: tuple[str, ...],
        idempotency_key: str | None,
        ack_required: bool,
        allow_broadcast: bool,
    ) -> Notification | None:
        if idempotency_key:
            existing = self._notif_repo.find_one(
                {"idempotency_key": idempotency_key}
            )
            if existing:
                logger.debug("通知幂等去重: key=%s", idempotency_key)
                return None

        notification = Notification(
            type=type,
            severity=severity,
            title=title,
            content=content,
            payload=payload,
            source_module=source_module,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            idempotency_key=idempotency_key,
        )
        self._notif_repo.session.add(notification)
        self._notif_repo.session.flush()

        user_ids = self._resolve_targets(target_type, target_id)

        for uid in user_ids:
            user = self._user_repo.find_by_id(uid)
            effective_channels = NotificationService._resolve_channels(
                user, channels, type, severity
            ) if user else list(channels)

            receipt = NotificationReceipt(
                notification_id=notification.id,
                user_id=uid,
                delivered_channels=effective_channels,
                channel_status={ChannelType.INBOX: "ok"} if ChannelType.INBOX in effective_channels else {},
                ack_required=ack_required,
            )
            self._receipt_repo.session.add(receipt)

        self._notif_repo.session.flush()

        if not _is_request_context():
            self._notif_repo.session.commit()

        logger.info(
            "通知已创建: type=%s severity=%s target=%s:%s users=%d",
            type, severity, target_type, target_id, len(user_ids),
        )

        try:
            from app.services.switch_events import _redis_publish_global
            import json, time as _time
            _redis_publish_global(json.dumps({
                "event_type": "notification_created",
                "payload": {
                    "notification_id": notification.id,
                    "type": type,
                    "severity": severity,
                },
                "target_user_ids": user_ids if target_type != "broadcast" else None,
                "ts": int(_time.time() * 1000),
            }, ensure_ascii=False))
        except Exception:
            pass

        has_personal_external = any(ch not in (ChannelType.INBOX,) for ch in channels)
        _broadcast_names = set(NotificationService._broadcast_channel_registry.keys())
        has_broadcast_channels = (
            allow_broadcast
            and bool(channels_set := set(channels) & _broadcast_names)
            and bool(NotificationService._broadcast_channel_registry)
        )
        if (has_personal_external or has_broadcast_channels) and user_ids:
            try:
                from app.services.notification_delivery_worker import enqueue_delivery
                enqueue_delivery(notification.id, user_ids)
            except Exception:
                logger.exception("外部渠道投递入队失败（inbox 已投递，不影响用户）")

        return notification


    def get_unread_count(self, user_id: int) -> int:
        return self._receipt_repo.count(
            {"user_id": user_id, "read_at": None}
        )

    def get_notifications(
        self,
        user_id: int,
        page: int = 1,
        per_page: int = 20,
        unread_only: bool = False,
    ) -> dict:
        items, total = self._receipt_repo.list_by_user_paginated(
            user_id, page=page, per_page=per_page, unread_only=unread_only,
        )

        unread_count = self._receipt_repo.count_unread(user_id)

        return {
            "items": [NotificationService._format_receipt(r) for r in items],
            "total": total,
            "unread_count": unread_count,
        }

    def mark_read(self, user_id: int, notification_ids: list[int] | None = None) -> int:
        if notification_ids:
            count = self._receipt_repo.mark_read_by_ids(user_id, notification_ids)
            self._receipt_repo.session.flush()
            return count
        return self._receipt_repo.mark_read(user_id)

    def delete_read(self, user_id: int) -> int:
        count = self._receipt_repo.delete_read(user_id)
        self._receipt_repo.session.flush()
        return count

    def mark_acked(self, user_id: int, notification_id: int) -> bool:
        receipt = self._receipt_repo.find_by_user_and_notification(user_id, notification_id)
        if not receipt or not receipt.ack_required:
            return False
        receipt.acked_at = datetime.now(timezone.utc)
        self._receipt_repo.session.flush()
        return True


    def get_preferences(self, user_id: int) -> dict:
        user = self._user_repo.find_by_id(user_id)
        if not user:
            return NotificationService._default_prefs()
        return user.notification_prefs or NotificationService._default_prefs()

    def update_preferences(self, user_id: int, prefs: dict) -> dict:
        user = self._user_repo.find_by_id(user_id)
        if not user:
            return NotificationService._default_prefs()

        current = user.notification_prefs or NotificationService._default_prefs()
        if "channels" in prefs:
            current["channels"] = {**current.get("channels", {}), **prefs["channels"]}
        if "subscribed_types" in prefs:
            current["subscribed_types"] = prefs["subscribed_types"]
        if "quiet_hours" in prefs:
            current["quiet_hours"] = {**current.get("quiet_hours", {}), **prefs["quiet_hours"]}

        user.notification_prefs = current
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user, "notification_prefs")
        self._notif_repo.session.flush()
        return current

    @staticmethod
    def _default_prefs() -> dict:
        return {
            "channels": {ChannelType.INBOX: True, ChannelType.EMAIL: True},
            "subscribed_types": [],
            "quiet_hours": {"enabled": False, "start": "22:00", "end": "08:00"},
        }


    def _resolve_targets(self, target_type: str, target_id) -> list[int]:
        session = self._user_repo.session
        if target_type == "user":
            if target_id is None:
                logger.warning("通知目标 target_type=user 但 target_id 为空，跳过投递")
                return []
            return [int(target_id)]
        elif target_type == "role":
            role = session.query(Role).filter_by(name=str(target_id)).first()
            if not role:
                return []
            user_ids = [
                ur.user_id
                for ur in session.query(UserRole).filter_by(role_id=role.id).all()
            ]
            active = session.query(User).filter(
                User.id.in_(user_ids), User.status == UserStatus.ACTIVE
            ).all()
            return [u.id for u in active]
        elif target_type == "broadcast":
            active = session.query(User).filter_by(status=0).all()
            return [u.id for u in active]
        else:
            logger.warning("未知 target_type: %s", target_type)
            return []

    @staticmethod
    def _resolve_channels(user: User, requested_channels: tuple[str, ...],
                          notif_type: str, severity: str) -> list[str]:
        prefs = user.notification_prefs
        if not prefs:
            return [ch for ch in requested_channels if ch in PERSONAL_CHANNELS]

        if NotificationService._in_quiet_hours(prefs) and severity != SeverityLevel.CRITICAL:
            return [ChannelType.INBOX]

        channel_prefs = prefs.get("channels", {})
        result = [ch for ch in requested_channels
                  if ch in PERSONAL_CHANNELS and (ch == ChannelType.INBOX or channel_prefs.get(ch, True))]

        subscribed = prefs.get("subscribed_types", [])
        if subscribed and notif_type not in subscribed and severity != SeverityLevel.CRITICAL:
            return [ChannelType.INBOX] if ChannelType.INBOX in result else []

        return result

    @staticmethod
    def _in_quiet_hours(prefs: dict) -> bool:
        qh = prefs.get("quiet_hours", {})
        if not qh.get("enabled"):
            return False

        start_str = qh.get("start", "22:00")
        end_str = qh.get("end", "08:00")

        try:
            from datetime import time as dt_time, timezone
            start = dt_time(int(start_str.split(":")[0]), int(start_str.split(":")[1]))
            end = dt_time(int(end_str.split(":")[0]), int(end_str.split(":")[1]))

            try:
                from config import get_config
                tz_name = getattr(get_config(), 'APP_TIMEZONE', 'Asia/Shanghai')
            except Exception:
                tz_name = 'Asia/Shanghai'

            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(tz_name)
            except Exception:
                from datetime import timedelta
                tz = timezone(timedelta(hours=8))

            now = datetime.now(tz).time()

            if start <= end:
                return start <= now <= end
            else:
                return now >= start or now <= end
        except (ValueError, IndexError):
            return False

    @staticmethod
    def _format_receipt(receipt: NotificationReceipt) -> dict:
        n = receipt.notification
        return {
            "id": n.id,
            "receipt_id": receipt.id,
            "type": n.type,
            "severity": n.severity,
            "title": n.title,
            "content": n.content,
            "payload": n.payload,
            "source_module": n.source_module,
            "is_read": receipt.read_at is not None,
            "read_at": receipt.read_at.isoformat() if receipt.read_at else None,
            "ack_required": receipt.ack_required,
            "acked_at": receipt.acked_at.isoformat() if receipt.acked_at else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }


notification_service = NotificationService()


def _is_request_context() -> bool:
    try:
        from flask import has_request_context
        return has_request_context()
    except Exception:
        return False
