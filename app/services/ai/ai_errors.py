# -*- coding: utf-8 -*-
"""AI 对外错误语义统一。

前端只需要区分两类 AI 故障，其余细节（上游 URL、响应体、堆栈、内部路径）
一律只写服务端日志，不随 API 响应外泄（`handle_api_exception` 会把
`message` 原样透传给前端）：

1. **未配置**：模型凭据 / 端点缺失 → `AINotConfiguredError`
   （提示"AI 未配置，请先完成模型配置后重试"）；
2. **服务错误**：连接失败、读超时、限流（429）、配额耗尽、鉴权失败、
   上游 5xx、熔断打开等 → `AIServiceError`（统一提示"AI 服务错误"）。

分类只在 provider 层做一次，业务层不再各自拼错误文案。
"""
from typing import Optional

from app.exceptions.system import ExternalServiceError

AI_NOT_CONFIGURED_MESSAGE = "AI 未配置，请先完成模型配置后重试"
AI_SERVICE_ERROR_MESSAGE = "AI 服务错误，请稍后重试或联系管理员"

_HTTP_UNAVAILABLE = 503


class AINotConfiguredError(ExternalServiceError):
    """AI 未配置（缺少 API Key / 端点）。"""

    def __init__(self, operation: Optional[str] = None):
        super().__init__(
            service_name="ai",
            operation=operation or "chat",
            message=AI_NOT_CONFIGURED_MESSAGE,
        )
        self.status_code = _HTTP_UNAVAILABLE
        self.code = "AI_NOT_CONFIGURED"


class AIServiceError(ExternalServiceError):
    """AI 服务不可用（连接失败 / 超时 / 限流 / 配额 / 5xx / 熔断）。"""

    def __init__(self, operation: Optional[str] = None):
        super().__init__(
            service_name="ai",
            operation=operation or "chat",
            message=AI_SERVICE_ERROR_MESSAGE,
        )
        self.status_code = _HTTP_UNAVAILABLE
        self.code = "AI_SERVICE_ERROR"
