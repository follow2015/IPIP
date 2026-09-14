# -*- coding: utf-8 -*-
"""钉钉自定义机器人 Webhook 渠道。

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
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote, urlparse

from app.core.enums import ChannelType
from app.models.notification import Notification
from app.models.webhook_config import WebhookConfig
from app.services.channels.base_webhook_channel import SEVERITY_EMOJI, BaseWebhookChannel


class DingTalkWebhookChannel(BaseWebhookChannel):
    """钉钉自定义机器人 Webhook 渠道。"""

    channel_type = ChannelType.DINGTALK
    display_name = "钉钉"

    def _build_payload(
        self, notification: Notification
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, str]]]:
        """构造钉钉 Markdown 消息体。

        钉钉 markdown 子集：支持标题/引用/加粗，**不支持 `<font>` 着色**。
        """
        emoji = SEVERITY_EMOJI.get(notification.severity, "")
        content = (
            f"### {emoji} {notification.title}\n\n"
            f"- **类型**: {notification.type}\n"
            f"- **严重程度**: {notification.severity}\n"
            f"- **来源**: {notification.source_module or '系统'}\n\n"
            f"{notification.content or ''}\n\n"
            f"> {notification.created_at.isoformat() if notification.created_at else ''}"
        )

        return {
            "msgtype": "markdown",
            "markdown": {"title": notification.title, "text": content},
        }, None

    def _apply_sign(self, cfg: WebhookConfig, payload: Dict[str, Any]) -> str:
        """钉钉加签：**拼在 URL query 上，消息体不变**。"""
        if not cfg.secret:
            return cfg.url
        timestamp = str(int(time.time() * 1000))  # 钉钉要求毫秒
        return _append_sign(cfg.url, timestamp, _gen_sign(cfg.secret, timestamp))


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
