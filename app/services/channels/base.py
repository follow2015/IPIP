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
from app.utils.logging import get_logger

logger = get_logger(__name__)


def ensure_webhook_success(resp, channel_name: str) -> None:
    """N3：校验 webhook 业务的返回码——HTTP 200 不等于投递成功。

    企微返回 `errcode`、飞书返回 `code`；关键词不匹配、签名错误、机器人被
    移除等场景均返回 **HTTP 200 + 非零业务码**。仅凭 HTTP 状态码会把这些
    失败误记为成功，导致广播告警静默丢失且无任何重试。

    Args:
        resp: requests 响应对象。
        channel_name: 渠道名，仅用于错误信息可读。

    Raises:
        RuntimeError: 业务码非 0（由调用方的 try/except 记为投递失败）。
    """
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return  # 非 JSON 响应（如网关 HTML 拦截页）：以 HTTP 状态为准
    if not isinstance(body, dict):
        return
    code = body.get("errcode", body.get("code"))
    if code is None:
        return
    try:
        failed = int(code) != 0
    except (TypeError, ValueError):
        return
    if failed:
        msg = body.get("errmsg") or body.get("msg") or ""
        raise RuntimeError(f"{channel_name} Webhook 业务失败 code={code} {msg}".strip())


class PersonalChannel(ABC):
    """个人渠道抽象基类

    对应 inbox / email 等语义上"发给某一个人"的渠道。
    每个用户的 receipt 各自独立投递，受用户 notification_prefs 偏好控制。
    """

    @abstractmethod
    def get_channel_name(self) -> str:
        """返回渠道标识（如 'inbox', 'email'）"""
        ...

    @abstractmethod
    def send(self, notification: Notification, receipt: NotificationReceipt, user: User) -> bool:
        """发送通知到该渠道

        Args:
            notification: 通知主体
            receipt: 投递回执
            user: 目标用户

        Returns:
            bool: 发送是否成功
        """
        ...

    def is_available(self, user: User) -> bool:
        """检查该渠道对用户是否可用（偏好 + 配置）

        默认实现：检查 user.notification_prefs.channels[self.get_channel_name()]
        子类可覆盖以增加额外检查（如 SMTP 配置是否完整、用户是否有邮箱）。
        """
        prefs = user.notification_prefs
        if not prefs:
            return True  # 无偏好设置 = 全部渠道可用
        channels = prefs.get("channels", {})
        return channels.get(self.get_channel_name(), True)


class BroadcastChannel(ABC):
    """广播渠道抽象基类

    对应企微/飞书群机器人等"一条通知全局最多发一次"的渠道。
    不关心命中了多少用户，是否发送完全由 WebhookConfig 的
    applicable_types/applicable_severities 决定，不受任何个人偏好影响。
    """

    @abstractmethod
    def get_channel_name(self) -> str:
        """返回渠道标识（如 'wechat_work', 'feishu'）"""
        ...

    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """发送通知到该渠道（全局最多发一次）

        内部查询所有启用的 WebhookConfig，逐条匹配 applicable_types/applicable_severities，
        匹配的都发，互不影响（一条失败不影响另一条）。

        Args:
            notification: 通知主体

        Returns:
            bool: 是否至少有一条配置发送成功
        """
        ...
