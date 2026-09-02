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
from app.services.channels.base import PersonalChannel, BroadcastChannel

logger = get_logger(__name__)


class NotificationService:
    """统一消息通知服务"""

    def __init__(self, notif_repo: NotificationRepository = None,
                 receipt_repo: NotificationReceiptRepository = None,
                 user_repo: UserRepository = None):
        self._notif_repo = notif_repo or NotificationRepository()
        self._receipt_repo = receipt_repo or NotificationReceiptRepository()
        self._user_repo = user_repo or UserRepository()

    _personal_channel_registry: dict[str, PersonalChannel] = {}
    _broadcast_channel_registry: dict[str, BroadcastChannel] = {}

    @classmethod
    def register_personal_channel(cls, channel: PersonalChannel):
        """注册个人渠道"""
        cls._personal_channel_registry[channel.get_channel_name()] = channel

    @classmethod
    def register_broadcast_channel(cls, channel: BroadcastChannel):
        """注册广播渠道"""
        cls._broadcast_channel_registry[channel.get_channel_name()] = channel

    @classmethod
    def get_personal_channels(cls) -> list[PersonalChannel]:
        return list(cls._personal_channel_registry.values())

    @classmethod
    def get_broadcast_channels(cls) -> list[BroadcastChannel]:
        return list(cls._broadcast_channel_registry.values())

    @classmethod
    def get_personal_channel_names(cls) -> tuple[str, ...]:
        """个人渠道名（registry 优先，registry 为空时回退 PERSONAL_CHANNELS）。

        app/__init__.py 在 testing 配置下不注册任何渠道，registry 恒为空。
        若纯 registry 派生，_resolve_channels 会过滤掉包括 inbox 在内的
        全部渠道，造成通知零投递，故此处提供常量兜底默认值。
        """
        if cls._personal_channel_registry:
            return tuple(cls._personal_channel_registry.keys())
        return tuple(PERSONAL_CHANNELS)


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
        """产生一条通知并投递给目标用户。

        Args:
            type: 通知类型（业务语义标识）
            severity: 严重程度 info/warning/critical
            title: 通知标题
            content: 通知正文
            payload: 业务载荷（跳转用）
            source_module: 来源模块
            target_type: 目标类型 user/role/broadcast
            target_id: 目标标识（user_id / role_name / None for broadcast）
            channels: 投递渠道（inbox/email/wechat_work/feishu）
            idempotency_key: 幂等键，防止重复通知
            ack_required: 是否需要手动确认
            allow_broadcast: 是否允许广播渠道（企微/飞书）投递。
                设为 False 时，即使广播渠道已注册，也不会入队投递。
                用于责任人缺失等场景，避免外部轰炸。

        Returns:
            Notification 实例；幂等去重、目标为空、或投递过程本身出错时返回 None。

        注意：本方法内部捕获所有异常并回滚，不会向上抛出。
        通知是主业务操作的附带效果，不应该因为通知投递失败（如目标用户解析出错、
        DB 瞬时故障）而让一个已经成功提交的批量操作在 API 层面变成 500。

        警告：返回 None 无法区分「幂等去重」与「投递出错」。需要据投递结果决定
        重试/标记失败的调用方（如监控告警 outbox 发件器）必须改用
        :meth:`notify_strict`，否则会把失败当成功，造成告警静默丢失。
        """
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
        """与 :meth:`notify` 完全相同，但真实投递失败会向上抛出异常。

        语义约定（调用方据此判定投递结果）：

        - 返回 ``Notification``：投递成功；
        - 返回 ``None``：幂等去重命中或目标为空——**属于成功语义**，无需重试；
        - 抛出异常：真实投递失败（DB 故障、渠道入队异常等），调用方应重试或标记失败。

        存在的原因：``notify`` 为保护主业务流程会把异常吞成 ``None``，与幂等去重
        的 ``None`` 无法区分。监控告警 outbox 发件器若用 ``notify``，会把投递失败
        的行误标为 ``sent``，告警永久丢失且无任何重试（P0 级静默故障）。
        """
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
        self._notif_repo.session.flush()  # 拿到 notification.id

        user_ids = self._resolve_targets(target_type, target_id)

        if not user_ids and target_type in ("user", "role") and target_id is not None:
            logger.warning(
                "通知目标解析为 0 个用户: type=%s target_type=%s target_id=%s"
                "（检查目标是否存在/角色是否有成员）",
                type, target_type, target_id,
            )

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
            logger.info(
                "渠道选择结果: user_id=%s requested=%s effective=%s"
                " type=%s severity=%s",
                uid, list(channels), effective_channels, type, severity,
            )

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
            pass  # SSE 推送失败不影响通知创建

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
        """获取用户未读通知数。"""
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
        """获取用户通知列表（分页）。

        Returns:
            {"items": [...], "total": N, "unread_count": M}
        """
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
        """标记通知为已读。"""
        if notification_ids:
            count = self._receipt_repo.mark_read_by_ids(user_id, notification_ids)
            self._receipt_repo.session.flush()
            return count
        return self._receipt_repo.mark_read(user_id)

    def delete_read(self, user_id: int) -> int:
        """删除用户已读通知（保留未读）。"""
        count = self._receipt_repo.delete_read(user_id)
        self._receipt_repo.session.flush()
        return count

    def mark_acked(self, user_id: int, notification_id: int) -> bool:
        """确认通知（ack_required 场景）。"""
        receipt = self._receipt_repo.find_by_user_and_notification(user_id, notification_id)
        if not receipt or not receipt.ack_required:
            return False
        receipt.acked_at = datetime.now(timezone.utc)
        self._receipt_repo.session.flush()
        return True


    def get_preferences(self, user_id: int) -> dict:
        """获取用户通知偏好。"""
        user = self._user_repo.find_by_id(user_id)
        if not user:
            return NotificationService._default_prefs()
        return user.notification_prefs or NotificationService._default_prefs()

    def update_preferences(self, user_id: int, prefs: dict) -> dict:
        """更新用户通知偏好（merge 语义）。"""
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
        """返回默认通知偏好。"""
        return {
            "channels": {ChannelType.INBOX: True, ChannelType.EMAIL: True,
                         ChannelType.VOICE: False},
            "subscribed_types": [],
            "quiet_hours": {"enabled": False, "start": "22:00", "end": "08:00"},
        }


    def _resolve_targets(self, target_type: str, target_id) -> list[int]:
        """将 target_type/target_id 解析为 user_id 列表。"""
        session = self._user_repo.session
        if target_type == "user":
            if target_id is None:
                logger.warning("通知目标 target_type=user 但 target_id 为空，跳过投递")
                return []
            return [int(target_id)]
        elif target_type == "role":
            role = session.query(Role).filter_by(name=str(target_id)).first()
            if not role and str(target_id).isdigit():
                role = session.query(Role).get(int(target_id))
            if not role:
                logger.warning(
                    "通知目标角色不存在: target_type=role target_id=%s", target_id
                )
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
            active = session.query(User).filter_by(status=UserStatus.ACTIVE).all()
            return [u.id for u in active]
        else:
            logger.warning("未知 target_type: %s", target_type)
            return []

    @staticmethod
    def _resolve_channels(user: User, requested_channels: tuple[str, ...],
                          notif_type: str, severity: str) -> list[str]:
        """根据用户偏好和通知属性确定实际投递的个人渠道。

        个人渠道：inbox / email
        广播渠道（企微/飞书 Webhook）由 WebhookConfig.applicable_types/applicable_severities 独立控制，
        不受个人偏好影响（当前为群机器人广播，不 @个人用户）。
        inbox 始终不可关闭；email 受用户偏好开关控制。

        注意：本方法是 @staticmethod，无 cls，须写 NotificationService.xxx。
        """
        prefs = user.notification_prefs
        if not prefs:
            return [ch for ch in requested_channels
                    if ch in NotificationService.get_personal_channel_names()]

        channel_prefs = prefs.get("channels", {})

        if NotificationService._in_quiet_hours(prefs) and severity != SeverityLevel.CRITICAL:
            result = [ChannelType.INBOX]
            if (ChannelType.VOICE in requested_channels
                    and channel_prefs.get(ChannelType.VOICE, False)):
                result.append(ChannelType.VOICE)
            return result

        result = [ch for ch in requested_channels
                  if ch in NotificationService.get_personal_channel_names()
                  and (ch == ChannelType.INBOX or channel_prefs.get(ch, True))]

        subscribed = prefs.get("subscribed_types", [])
        if subscribed and notif_type not in subscribed and severity != SeverityLevel.CRITICAL:
            return [ChannelType.INBOX] if ChannelType.INBOX in result else []

        return result

    @staticmethod
    def _in_quiet_hours(prefs: dict) -> bool:
        """检查当前是否在免打扰时段。

        quiet_hours 中的 start/end 是用户本地时间（前端 TimePicker 选择），
        比较时需将 UTC 当前时间转换到应用时区后再取 .time()。
        """
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
        """格式化回执为前端友好的字典。"""
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
    """判断当前是否在 Flask HTTP 请求上下文中。

    后台线程（task_executor / threading.Thread）中没有请求上下文，
    Flask-SQLAlchemy 的 after_request 自动 commit 不会触发，
    因此 notify() 的 flush() 后必须显式 commit。
    """
    try:
        from flask import has_request_context
        return has_request_context()
    except Exception:
        return False
