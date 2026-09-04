# -*- coding: utf-8 -*-
"""告警智能解读服务。"""
from typing import Any, Dict

from app.services.ai.llm_factory import create_llm_client
from app.services.ai.llm_base import LLMClient
from app.services.ai.prompt_guard import strip_sensitive_fields
from app.services.ai.prompts.alert_interpret_prompt import SYSTEM, build_user_prompt
from app.services.ai._runtime import make_cache, observe_call, CallTimer
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AlertInterpreter:
    """将结构化告警转为人话解读。"""

    def __init__(self, client: LLMClient = None, cache=None):
        self.client = client or create_llm_client()
        self.cache = cache if cache is not None else make_cache()

    def interpret(self, alert: Dict, user_id: int = 0) -> str:
        safe_alert = strip_sensitive_fields(alert)
        try:
            cache_key = self.cache.make_key(user_id, "alert", safe_alert)
            cached = self.cache.get(cache_key)
        except Exception:  # noqa: BLE001
            cache_key = None
            cached = None
        if cached:
            return cached
        if not self.client.is_configured():
            return "（AI 未配置，无法解读）"
        user_prompt = build_user_prompt(safe_alert)
        status = "ok"
        text = ""
        audit_response: Any = None
        with CallTimer() as t:
            try:
                text = self.client.chat(SYSTEM, user_prompt)
                audit_response = text
            except Exception as e:  # noqa: BLE001
                status = "error"
                audit_response = {"error_type": type(e).__name__}
                logger.error("alert.interpret_failed %s: %s",
                             type(e).__name__, e, exc_info=True)
                raise
            finally:
                observe_call(scenario="alert", user_id=user_id,
                             request=safe_alert, response=audit_response,
                             status=status, duration_ms=t.duration_ms,
                             model=getattr(self.client, "model", None),
                             base_url=getattr(self.client, "base_url", None))
        if cache_key:
            try:
                self.cache.set(cache_key, text, ttl=1800)
            except Exception:  # noqa: BLE001
                pass
        return text
