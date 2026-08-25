# -*- coding: utf-8 -*-
"""
企业微信群机器人 Webhook 渠道

通过群机器人 Webhook URL 发送 Markdown 格式消息。
一条通知全局最多发一次，与命中多少用户无关。
"""
from app.utils.logging import get_logger

import requests

from app.core.enums import ChannelType
from app.services.channels.base import BroadcastChannel
from app.models.notification import Notification
from app.models.webhook_config import WebhookConfig

logger = get_logger(__name__)

WECHAT_WORK_API_TIMEOUT = 10

SEVERITY_EMOJI = {
    "info": "📋",
    "warning": "⚠️",
    "critical": "🔴",
}


class WeChatWorkWebhookChannel(BroadcastChannel):

    def get_channel_name(self) -> str:
        return ChannelType.WECHAT_WORK

    def send(self, notification: Notification) -> bool:
        configs = WebhookConfig.query.filter_by(channel=ChannelType.WECHAT_WORK, enabled=True).all()
        if not configs:
            return False

        any_success = False
        for cfg in configs:
            if not _matches(cfg, notification):
                continue
            try:
                self._post_to_webhook(cfg, notification)
                any_success = True
            except Exception:
                logger.exception("企微 Webhook 投递失败 config_id=%s name=%s", cfg.id, cfg.name)

        return any_success

    def _post_to_webhook(self, cfg: WebhookConfig, notification: Notification) -> None:
        emoji = SEVERITY_EMOJI.get(notification.severity, "")
        content = (
            f"## {emoji} {notification.title}\n"
            f"> **类型**: {notification.type}\n"
            f"> **严重程度**: {notification.severity}\n"
            f"> **来源**: {notification.source_module or '系统'}\n"
            f"\n"
            f"{notification.content or ''}\n"
            f"\n"
            f'<font color="comment">{notification.created_at.isoformat() if notification.created_at else ""}</font>'
        )

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }

        resp = requests.post(cfg.url, json=payload, timeout=WECHAT_WORK_API_TIMEOUT, allow_redirects=False)
        resp.raise_for_status()
        logger.info("企微 Webhook 投递成功 config_id=%s", cfg.id)


def _matches(cfg: WebhookConfig, notification: Notification) -> bool:
    if cfg.applicable_types and notification.type not in cfg.applicable_types:
        return False
    if cfg.applicable_severities and notification.severity not in cfg.applicable_severities:
        return False
    return True
