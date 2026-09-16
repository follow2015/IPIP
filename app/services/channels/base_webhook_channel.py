# -*- coding: utf-8 -*-
"""群机器人（Webhook）广播渠道基类。

背景（整改 T2.3）
----------------
`feishu` / `dingtalk` / `wechat_work` 三家渠道原本各自复制了一份
`send()` 与 `_matches()`（**逐字相同**），`_post_to_webhook` 的骨架也相同。
真实差异只有三处：

1. **payload 构造**：飞书 Interactive Card / 钉钉与企微 Markdown，模板各不相同；
2. **加签方式**：飞书把 `timestamp`/`sign` 放进**消息体**；钉钉拼在 **URL query**；
   企微无签名（三家写反都会表现为「签名错误」且很难排查）；
3. 渠道标识 / 中文名。

因此基类只固化两条流水线，其余留给子类：
- `send()`：查询启用配置 → 逐条匹配 → 发送 → **异常隔离**
- `_post_to_webhook()`：构造 → 加签 → POST → HTTP 校验 → 业务码校验 → 日志

两处必须遵守的约定（改了会静默丢告警）
------------------------------------
- **业务码校验走 `ensure_webhook_success`**：企微/飞书在「关键词不匹配、签名错误、
  机器人被移除」时返回 **HTTP 200 + 非零业务码**，只看 HTTP 状态会把失败误记成功。
- **单条配置失败必须隔离**：一条坏配置抛异常不得阻断其余配置的投递。

第三条：**异常消息必须先脱敏再进日志**（`redact_credentials`）
-----------------------------------------------------------
三家的凭证都长在 **URL 上**（钉钉 `access_token`、企微 `key`、飞书 `/hook/<uuid>`），
而 `requests` 的 `HTTPError` 消息会带上完整 URL：

    400 Client Error: None for url: https://oapi.dingtalk.com/robot/send?access_token=xxx&...

`send()` 用 `logger.exception`（连 traceback 一起打），URL 里的凭证就会进日志聚合。
因此 `_post_to_webhook` 在失败时**先脱敏再上抛**，并用 `from None` 抑制链式原始异常
（否则 traceback 仍会把未脱敏的消息带出来）。

`post_json` 的前两个参数须为**位置参数**（既有测试按 `call_args.args[1]` 取
payload）。
"""
import re
from abc import abstractmethod
from typing import Any, Dict, Optional, Tuple

from app.models.notification import Notification
from app.models.webhook_config import WebhookConfig
from app.services.channels.base import BroadcastChannel, ensure_webhook_success
from app.utils.http_client import post_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

SEVERITY_EMOJI = {
    "info": "📋",
    "warning": "⚠️",
    "critical": "🔴",
}

DEFAULT_WEBHOOK_TIMEOUT = 10

from app.utils.redaction import _CREDENTIAL_PATTERNS, redact_credentials  # noqa: F401


def _matches(cfg: WebhookConfig, notification: Notification) -> bool:
    """检查 WebhookConfig 是否匹配当前通知。

    `applicable_types` / `applicable_severities` 为空 = 不做该维度过滤。
    """
    if cfg.applicable_types and notification.type not in cfg.applicable_types:
        return False
    if cfg.applicable_severities and notification.severity not in cfg.applicable_severities:
        return False
    return True


class BaseWebhookChannel(BroadcastChannel):
    """群机器人广播渠道基类。

    子类必须定义 `channel_type` / `display_name` 并实现 `_build_payload()`；
    可选覆盖 `timeout` 与 `_apply_sign()`。
    """

    channel_type: str = ""
    display_name: str = ""
    timeout: int = DEFAULT_WEBHOOK_TIMEOUT

    def __init_subclass__(cls, **kwargs):
        """子类定义即校验必填类属性，**不等到运行时才静默失效**。

        为什么必须做：`send()` 用 `channel_type` 查配置，若子类漏填/拼错，
        查询条件变成 `channel=""` → 必然空结果 → 返回 `False`，**全程无任何
        日志**——渠道"装好了但永不发消息"，正是审计里反复出现的静默失败模式。
        """
        super().__init_subclass__(**kwargs)
        missing = [
            name for name in ("channel_type", "display_name")
            if not getattr(cls, name, "")
        ]
        if missing:
            raise TypeError(
                f"webhook 渠道子类 {cls.__name__} 未定义必填类属性: {', '.join(missing)}"
                f"（漏填会导致渠道静默失效：按空 channel 查询配置，返回 False 且无日志）"
            )

    def get_channel_name(self) -> str:
        return self.channel_type

    def send(self, notification: Notification) -> bool:
        """发送通知到所有匹配的群机器人（一条通知全局最多发一次）。

        Returns:
            bool: 是否至少有一条配置投递成功。
        """
        configs = WebhookConfig.query.filter_by(channel=self.channel_type, enabled=True).all()
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
                logger.exception(
                    "%s Webhook 投递失败 config_id=%s name=%s",
                    self.display_name, cfg.id, cfg.name,
                )

        return any_success

    def _post_to_webhook(self, cfg: WebhookConfig, notification: Notification) -> None:
        """构造 payload → 加签 → POST → HTTP 校验 → 业务码校验。

        失败时**脱敏后上抛**（见 `redact_credentials`）：异常消息含完整 URL，
        而 URL 上挂着渠道凭证；由 `send()` 统一 `logger.exception` 记日志。
        """
        payload, headers = self._build_payload(notification)
        url = self._apply_sign(cfg, payload)

        try:
            resp = post_json(url, payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            ensure_webhook_success(resp, self.display_name)
        except Exception as exc:
            detail = redact_credentials(f"{type(exc).__name__}: {exc}")
            raise RuntimeError(detail) from None  # from None：否则 traceback 会把未脱敏的原始消息带出来
        logger.info("%s Webhook 投递成功 config_id=%s", self.display_name, cfg.id)

    @abstractmethod
    def _build_payload(
        self, notification: Notification
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, str]]]:
        """构造请求体与额外请求头。

        Returns:
            (payload, headers)：headers 为 None 时表示无需额外请求头。
        """
        ...

    def _apply_sign(self, cfg: WebhookConfig, payload: Dict[str, Any]) -> str:
        """加签钩子：返回最终请求 URL；**允许就地修改 payload**。

        默认不签名（企微）。飞书把签名写进 payload；钉钉拼到 URL query 上。
        """
        return cfg.url
