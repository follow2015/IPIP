# -*- coding: utf-8 -*-
"""AI 审计日志适配层（复用既有 AuditService，不新建表）。

十轮评审重构（D2）：原方案新建 ai_audit_log 表 + 专用仓储，与既有
AuditService + AuditLog 完全重复。本模块为薄适配层，转调既有 AuditService.log，
detail JSON 字段承载 AI 专属字段（scenario/request/response/duration_ms/status/tokens/model/base_url）。
"""
from typing import Any, Optional

from app.services.audit_service import AuditService
from app.services.ai.prompt_guard import strip_sensitive_fields, redact_deep
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AIAuditLogger:
    """AI 审计日志适配层。

    复用既有 AuditService.log(action="ai.<scenario>", resource="ai", detail={...})，
    不新建 ai_audit_log 表。request/response 经 prompt_guard 过滤凭据字段后入 detail。
    """

    def __init__(self, audit_service: Optional[AuditService] = None):
        self._audit = audit_service or AuditService()

    def log(self, user_id: int, scenario: str, request: Any, response: Any,
             duration_ms: int, status: str, tokens: Optional[int] = None,
             model: Optional[str] = None, base_url: Optional[str] = None) -> None:
        """记录一次 AI 调用审计日志。

        Args:
            user_id: 用户 ID
            scenario: 场景（alert/nlq/rag/inspection）
            request: 请求内容（经凭据过滤后入 detail）
            response: 响应内容
            duration_ms: 耗时毫秒
            status: 状态（ok/error）
            tokens: token 数
            model: 模型名
            base_url: LLM 端点 URL
        """
        try:
            safe_req = redact_deep(strip_sensitive_fields(request))
            safe_resp = redact_deep(strip_sensitive_fields(response))
            detail = {
                "scenario": scenario,
                "request": safe_req,
                "response": safe_resp,
                "duration_ms": duration_ms,
                "status": status,
                "tokens": tokens,
                "model": model,
                "base_url": base_url,
            }
            self._audit.log(
                user_id=user_id,
                action=f"ai.{scenario}",
                resource="ai",
                detail=detail,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("ai.audit.log_failed %s", e)
