# -*- coding: utf-8 -*-
"""飞书群机器人 Webhook 渠道。

通过群机器人 Webhook URL 发送 Interactive Card 消息。
一条通知全局最多发一次，与命中多少用户无关。

加签要点：**飞书的 sign 放在消息体里**（payload 的 `timestamp` / `sign` 字段），
与钉钉「拼在 URL query」不同；两家算法也不一样（见 `_gen_sign` 与 dingtalk.py）。
"""
import base64
import hashlib
import hmac
import time
from typing import Any, Dict, Optional, Tuple

from app.core.enums import ChannelType
from app.models.notification import Notification
from app.models.webhook_config import WebhookConfig
from app.services.channels.base_webhook_channel import BaseWebhookChannel

SEVERITY_COLOR = {
    "info": "blue",
    "warning": "orange",
    "critical": "red",
}


class FeishuWebhookChannel(BaseWebhookChannel):
    """飞书群机器人 Webhook 渠道。"""

    channel_type = ChannelType.FEISHU
    display_name = "飞书"

    def _build_payload(
        self, notification: Notification
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, str]]]:
        """构造飞书 Interactive Card 消息体。"""
        color = SEVERITY_COLOR.get(notification.severity, "blue")

        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": notification.title},
                    "template": color,
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": notification.content or ""},
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": f"{notification.source_module or '系统'} · {notification.type} · "
                                           f"{notification.created_at.isoformat() if notification.created_at else ''}",
                            }
                        ],
                    },
                ],
            },
        }
        return card, {"Content-Type": "application/json"}

    def _apply_sign(self, cfg: WebhookConfig, payload: Dict[str, Any]) -> str:
        """飞书加签：**写入消息体**，URL 不变。"""
        if cfg.secret:
            timestamp = str(int(time.time()))
            payload["timestamp"] = timestamp
            payload["sign"] = _gen_sign(cfg.secret, timestamp)
        return cfg.url


def _gen_sign(secret: str, timestamp: str) -> str:
    """生成飞书 Webhook 签名。

    飞书官方算法（**与钉钉不同**）::

        string_to_sign = f"{timestamp}\\n{secret}"
        hmac_code = HMAC-SHA256(key=string_to_sign, msg=b"")
        sign = base64.b64encode(hmac_code)

    关键点：**签名字符串整体当 key，message 为空**。
    """
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")
