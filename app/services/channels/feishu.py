# -*- coding: utf-8 -*-
"""
飞书群机器人 Webhook 渠道

通过群机器人 Webhook URL 发送 Interactive Card 消息。
一条通知全局最多发一次，与命中多少用户无关。
"""
import hashlib
import hmac
from app.utils.logging import get_logger
import time

from app.utils.http_client import post_json

from app.core.enums import ChannelType
from app.services.channels.base import BroadcastChannel, ensure_webhook_success
from app.models.notification import Notification
from app.models.webhook_config import WebhookConfig

logger = get_logger(__name__)

FEISHU_API_TIMEOUT = 10  # 飞书 API 请求超时时间（秒）

SEVERITY_COLOR = {
    "info": "blue",
    "warning": "orange",
    "critical": "red",
}


class FeishuWebhookChannel(BroadcastChannel):
    """飞书群机器人 Webhook 渠道"""

    def get_channel_name(self) -> str:
        return ChannelType.FEISHU

    def send(self, notification: Notification) -> bool:
        """发送通知到所有匹配的飞书群机器人

        查询所有启用的 feishu 类型 WebhookConfig，
        逐条匹配 applicable_types/applicable_severities，匹配的都发，互不影响。
        """
        configs = WebhookConfig.query.filter_by(channel=ChannelType.FEISHU, enabled=True).all()
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
                logger.exception("飞书 Webhook 投递失败 config_id=%s name=%s", cfg.id, cfg.name)

        return any_success

    def _post_to_webhook(self, cfg: WebhookConfig, notification: Notification) -> None:
        """发送 Interactive Card 消息到飞书群机器人"""
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

        headers = {"Content-Type": "application/json"}
        url = cfg.url

        if cfg.secret:
            timestamp = str(int(time.time()))
            sign = _gen_sign(cfg.secret, timestamp)
            card["timestamp"] = timestamp
            card["sign"] = sign

        resp = post_json(url, card, headers=headers, timeout=FEISHU_API_TIMEOUT)
        resp.raise_for_status()
        ensure_webhook_success(resp, "飞书")
        logger.info("飞书 Webhook 投递成功 config_id=%s", cfg.id)


def _matches(cfg: WebhookConfig, notification: Notification) -> bool:
    """检查 WebhookConfig 是否匹配当前通知"""
    if cfg.applicable_types and notification.type not in cfg.applicable_types:
        return False
    if cfg.applicable_severities and notification.severity not in cfg.applicable_severities:
        return False
    return True


def _gen_sign(secret: str, timestamp: str) -> str:
    """生成飞书 Webhook 签名"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    import base64
    return base64.b64encode(hmac_code).decode("utf-8")
