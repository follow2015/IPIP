# -*- coding: utf-8 -*-
"""
通知渠道抽象基类

将渠道分为两类：
- PersonalChannel：个人渠道（inbox/email），语义上"发给某一个人"，每个 receipt 各发一次
- BroadcastChannel：广播渠道（企微/飞书群机器人），语义上"一条通知全局最多发一次"

群机器人不存在"发给某个用户"的个体差异，因此 BroadcastChannel.send() 只接受 notification，
不接受单个 user/receipt。是否发送完全由 WebhookConfig 的 applicable_types/applicable_severities 决定。
"""
from abc import ABC, abstractmethod

from app.models.notification import Notification, NotificationReceipt
from app.models.user import User


class PersonalChannel(ABC):

    @abstractmethod
    def get_channel_name(self) -> str:
        ...

    @abstractmethod
    def send(self, notification: Notification, receipt: NotificationReceipt, user: User) -> bool:
        ...

    def is_available(self, user: User) -> bool:
        prefs = user.notification_prefs
        if not prefs:
            return True
        channels = prefs.get("channels", {})
        return channels.get(self.get_channel_name(), True)


class BroadcastChannel(ABC):

    @abstractmethod
    def get_channel_name(self) -> str:
        ...

    @abstractmethod
    def send(self, notification: Notification) -> bool:
        ...
