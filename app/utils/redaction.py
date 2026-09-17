# -*- coding: utf-8 -*-
"""日志脱敏：抹掉文本中的凭证形态（webhook URL / URL userinfo / 云厂商 AK / Bearer）。

**为什么住在 utils 层**：`redact_credentials` 是**日志安全**设施，不止 webhook 渠道要用——
`app/utils/redis_client.py` 记 REDIS_URL 时同样要抹掉密码。而分层守卫（
`tests/test_architecture_layering.py`）禁止 utils 反向依赖 services，故本设施下沉至此，
由 services 层**向下**引用；`app/services/channels/base_webhook_channel.py` 保留同名再导出，
既有调用点与测试不受影响。

**两条相互拉扯的口径**（改动模式时务必同时满足，`tests/test_redaction.py` 两侧都钉了断言）：
1. 凭证一律抹除，宁可误抹也不漏抹（漏抹 = 凭证进日志聚合系统）；
2. 但不得把普通错误文案也打码（脱敏过度会让日志丧失排障价值）。
"""
import re


_CREDENTIAL_PATTERNS = (
    re.compile(r"(access_token=)[^&\s'\"]+", re.IGNORECASE),
    re.compile(r"([?&]key=)[^&\s'\"]+", re.IGNORECASE),
    re.compile(r"([?&]sign=)[^&\s'\"]+", re.IGNORECASE),
    re.compile(r"(/hook/)[0-9a-zA-Z-]{8,}"),
    re.compile(r"(hooks\.slack\.com/services/)[A-Za-z0-9/_-]+"),
    re.compile(r"([a-zA-Z0-9-]{1,63}\.webhook\.office\.com/webhookb?\d*/)[A-Za-z0-9@/_.-]+", re.IGNORECASE),
    re.compile(r"(://)[^/\s:@]*:[^/\s@]+@"),
    re.compile(r"(\bAKIA)[0-9A-Z]{16}\b"),                  # AWS Access Key ID
    re.compile(r"(\bLTAI)[A-Za-z0-9]{12,30}\b"),            # 阿里云 AccessKeyId
    re.compile(r"(\bAKID)[A-Za-z0-9]{16,40}\b"),            # 腾讯云 SecretId
    re.compile(r"(\bBearer\s+)[A-Za-z0-9\-._~+/]{20,}=*"),
)


def redact_credentials(text: str) -> str:
    """抹掉文本中的 webhook 凭证，供日志安全输出。

    为什么必须做：凭证在 URL 上，而 `requests.raise_for_status()` 的异常消息
    含完整 URL —— 原样进日志等于把"能向群里发消息的凭证"写进日志聚合系统
    （日志的留存期与可见面通常远大于进程内存里的那条配置）。

    Args:
        text: 任意可能含凭证的文本（通常是异常消息）。

    Returns:
        str: 凭证值被替换为 `***` 的文本。
    """
    for pattern in _CREDENTIAL_PATTERNS:
        text = pattern.sub(r"\1***", text)
    return text
