# -*- coding: utf-8 -*-
"""
站内信渠道

Inbox 渠道的"发送"实际上是 DB 写入（已在 NotificationService._notify_inner 中完成），
此处的 send() 仅做确认标记。
"""
from app.core.enums import ChannelType
from app.services.channels.base import PersonalChannel
from app.models.notification import Notification, NotificationReceipt
from app.models.user import User


class InboxChannel(PersonalChannel):

    def get_channel_name(self) -> str:
        return ChannelType.INBOX

    def send(self, notification: Notification, receipt: NotificationReceipt, user: User) -> bool:
        return True
