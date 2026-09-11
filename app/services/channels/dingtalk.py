# -*- coding: utf-8 -*-
"""
钉钉自定义机器人 Webhook 渠道

通过群机器人 Webhook URL 发送 Markdown 格式消息，一条通知全局最多发一次，
与命中多少用户无关。

与飞书的同构差异（容易写错的点）：
- **签名拼在 URL 上，不放消息体**：``&timestamp=<毫秒>&sign=<urlencode(签名)>``；
  放进 body 钉钉会直接忽略，表现为"签名错误"且难以排查。
- 时间戳是**毫秒**（飞书是秒）。
- 签名算法与飞书**不同**（照抄飞书必错）：钉钉为
  ``HMAC-SHA256(key=secret, msg=f"{timestamp}\\n{secret}")`` 后 Base64；
  飞书才是 ``HMAC-SHA256(key=f"{timestamp}\\n{secret}", msg="")``。
"""
import base64
import hashlib
import hmac
import time
from urllib.parse import quote, urlparse

from app.utils.logging import get_logger

from app.utils.http_client import post_json

from app.core.enums import ChannelType
from app.services.channels.base import BroadcastChannel, ensure_webhook_success
from app.models.notification import Notification
from app.models.webhook_config import WebhookConfig

logger = get_logger(__name__)

DINGTALK_API_TIMEOUT = 10  # 钉钉 API 请求超时时间（秒）

SEVERITY_EMOJI = {
    "info": "📋",
    "warning": "⚠️",
    "critical": "🔴",
}


class DingTalkWebhookChannel(BroadcastChannel):
    """钉钉自定义机器人 Webhook 渠道"""

    def get_channel_name(self) -> str:
        return ChannelType.DINGTALK

    def send(self, notification: Notification) -> bool:
        """发送通知到所有匹配的钉钉群机器人

        查询所有启用的 dingtalk 类型 WebhookConfig，
        逐条匹配 applicable_types/applicable_severities，匹配的都发，互不影响。
        """
        configs = WebhookConfig.query.filter_by(channel=ChannelType.DINGTALK, enabled=True).all()
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
                logger.exception("钉钉 Webhook 投递失败 config_id=%s name=%s", cfg.id, cfg.name)

        return any_success

    def _post_to_webhook(self, cfg: WebhookConfig, notification: Notification) -> None:
        """发送 Markdown 消息到钉钉自定义机器人"""
        emoji = SEVERITY_EMOJI.get(notification.severity, "")
        content = (
            f"### {emoji} {notification.title}\n\n"
            f"- **类型**: {notification.type}\n"
            f"- **严重程度**: {notification.severity}\n"
            f"- **来源**: {notification.source_module or '系统'}\n\n"
            f"{notification.content or ''}\n\n"
            f"> {notification.created_at.isoformat() if notification.created_at else ''}"
        )

        payload = {
            "msgtype": "markdown",
            "markdown": {"title": notification.title, "text": content},
        }

        url = cfg.url
        if cfg.secret:
            timestamp = str(int(time.time() * 1000))  # 钉钉要求毫秒
            sign = _gen_sign(cfg.secret, timestamp)
            url = _append_sign(url, timestamp, sign)

        resp = post_json(url, payload, timeout=DINGTALK_API_TIMEOUT)
        resp.raise_for_status()
        ensure_webhook_success(resp, "钉钉")
        logger.info("钉钉 Webhook 投递成功 config_id=%s", cfg.id)


def _matches(cfg: WebhookConfig, notification: Notification) -> bool:
    """检查 WebhookConfig 是否匹配当前通知"""
    if cfg.applicable_types and notification.type not in cfg.applicable_types:
        return False
    if cfg.applicable_severities and notification.severity not in cfg.applicable_severities:
        return False
    return True


def _gen_sign(secret: str, timestamp: str) -> str:
    """生成钉钉加签签名。

    钉钉官方算法（**与飞书不同，沿用飞书写法会永远校验失败**）::

        string_to_sign = f"{timestamp}\\n{secret}"
        hmac_code = hmac.new(secret.encode("utf-8"),
                             string_to_sign.encode("utf-8"),
                             digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code)

    关键点：**key 是 secret，message 是 ``timestamp\\nsecret``**。
    """
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def _append_sign(url: str, timestamp: str, sign: str) -> str:
    """把 timestamp/sign 拼到 URL 查询参数上。

    钉钉机器人地址形如 ``https://oapi.dingtalk.com/robot/send?access_token=xxx``，
    已带 query 时用 ``&`` 追加；健壮处理裸 URL（无 query）的情形。
    原始 URL 自身的 query（access_token）原样保留。
    """
    sign_param = f"timestamp={quote(timestamp)}&sign={quote(sign)}"
    sep = "&" if urlparse(url).query else "?"
    return f"{url}{sep}{sign_param}"
