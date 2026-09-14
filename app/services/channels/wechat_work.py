# -*- coding: utf-8 -*-
"""企业微信群机器人 Webhook 渠道。

通过群机器人 Webhook URL 发送 Markdown 格式消息。
一条通知全局最多发一次，与命中多少用户无关。

企微群机器人**不支持加签**（无 secret 环节），也**无消息体模板差异**，
因此只实现 `_build_payload()`；超时/异常隔离/业务码校验全部由基类承担。
"""
from typing import Any, Dict, Optional, Tuple

from app.core.enums import ChannelType
from app.models.notification import Notification
from app.services.channels.base_webhook_channel import SEVERITY_EMOJI, BaseWebhookChannel


class WeChatWorkWebhookChannel(BaseWebhookChannel):
    """企业微信群机器人 Webhook 渠道。"""

    channel_type = ChannelType.WECHAT_WORK
    display_name = "企微"

    def _build_payload(
        self, notification: Notification
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, str]]]:
        """构造企微 Markdown 消息体（支持 `<font color>` 着色）。"""
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

        return {"msgtype": "markdown", "markdown": {"content": content}}, None
