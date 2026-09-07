# -*- coding: utf-8 -*-
"""OpenAI 兼容协议 provider。

兼容通义/DeepSeek/本地 Ollama 等任意 OpenAI 兼容端点（通过 base_url 切换）。
"""
from typing import Optional

from openai import OpenAI, APIConnectionError, APIStatusError, APITimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.services.ai.ai_errors import AINotConfiguredError, AIServiceError
from app.services.ai.circuit_breaker import get_circuit_breaker, AICircuitOpenError
from app.services.ai.llm_base import LLMClient
from app.services.ai.llm_factory import register_provider
from config import Config
from app.utils.logging import get_logger

logger = get_logger(__name__)

_RETRY_DECORATOR = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError)),
    reraise=True,
)


def _provider_name() -> str:
    return Config.AI_PROVIDER or "openai"


@register_provider("openai")
class OpenAIProvider(LLMClient):
    """OpenAI 兼容客户端。"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 model: Optional[str] = None):
        self.api_key = api_key or Config.AI_API_KEY
        self.base_url = base_url or Config.AI_BASE_URL
        self.model = model or Config.AI_MODEL
        self._client: Optional[OpenAI] = None
        self._stream_client: Optional[OpenAI] = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self) -> OpenAI:
        """获取缓存的 OpenAI client（M5 修复：复用连接池）。"""
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                                  timeout=Config.AI_TIMEOUT)
        return self._client

    def _get_stream_client(self) -> OpenAI:
        """获取缓存的流式 OpenAI client（M5 修复）。"""
        if self._stream_client is None:
            self._stream_client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                                         timeout=Config.AI_STREAM_TIMEOUT)
        return self._stream_client

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self.is_configured():
            raise AINotConfiguredError(operation="chat")
        try:
            resp = self._call_with_circuit(system_prompt, user_prompt)
            if not resp.choices:
                return ""
            content = resp.choices[0].message.content
            usage = getattr(resp, "usage", None)
            reasoning = getattr(resp.choices[0].message, "reasoning_content", None)
            finish_reason = getattr(resp.choices[0], "finish_reason", None)
            logger.info(
                "ai.chat.complete model=%s base_url=%s tokens=%s prompt=%s "
                "completion=%s finish=%s content_len=%s reasoning_len=%s",
                self.model, self.base_url,
                getattr(usage, "total_tokens", None) if usage else None,
                getattr(usage, "prompt_tokens", None) if usage else None,
                getattr(usage, "completion_tokens", None) if usage else None,
                finish_reason, len(content or ""), len(reasoning or ""),
            )
            if not content:
                logger.warning(
                    "ai.chat.empty_content model=%s finish=%s completion=%s "
                    "reasoning_len=%s（输出配额可能被思维链占满，建议调大 AI_MAX_TOKENS）",
                    self.model, finish_reason,
                    getattr(usage, "completion_tokens", None) if usage else None,
                    len(reasoning or ""),
                )
                raise AIServiceError(operation="chat")
            return content
        except (APIConnectionError, APITimeoutError) as e:
            logger.error("ai.chat.connection_failed type=%s err=%s",
                         type(e).__name__, e)
            raise AIServiceError(operation="chat")
        except APIStatusError as e:
            logger.error("ai.chat.status_error status=%s err=%s", e.status_code, e)
            raise AIServiceError(operation="chat")
        except AIServiceError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.error("ai.chat.unexpected type=%s err=%s",
                         type(e).__name__, e, exc_info=True)
            raise AIServiceError(operation="chat")

    @_RETRY_DECORATOR
    def _call_sdk(self, system_prompt: str, user_prompt: str):
        client = self._get_client()
        return client.chat.completions.create(
            model=self.model,
            temperature=Config.AI_TEMPERATURE,
            max_tokens=Config.AI_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

    def _call_with_circuit(self, system_prompt: str, user_prompt: str):
        """熔断器包裹的 SDK 调用。"""
        return get_circuit_breaker(_provider_name()).call(
            lambda: self._call_sdk(system_prompt, user_prompt)
        )

    def chat_stream(self, system_prompt: str, user_prompt: str):
        if not self.is_configured():
            raise AINotConfiguredError(operation="chat_stream")
        breaker = get_circuit_breaker(_provider_name())
        if not breaker.allow_request():
            raise AICircuitOpenError(_provider_name())
        try:
            client = self._get_stream_client()
            stream = client.chat.completions.create(
                model=self.model, temperature=Config.AI_TEMPERATURE,
                max_tokens=Config.AI_MAX_TOKENS, stream=True,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            try:
                for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        yield delta
                breaker.record_success()  # 流式完整结束 → 闭合
            finally:
                try:
                    stream.close()
                except Exception:  # noqa: BLE001
                    logger.debug("AI 流式连接关闭异常（忽略）")
        except GeneratorExit:
            breaker.record_success()
            logger.warning("AI 流式输出因客户端断连而中止（已按成功计入熔断）")
            raise
        except (APIConnectionError, APITimeoutError, APIStatusError) as e:
            breaker.record_failure()
            logger.error("ai.chat_stream.upstream_failed type=%s err=%s",
                         type(e).__name__, e)
            raise AIServiceError(operation="chat_stream")
        except Exception as e:  # noqa: BLE001
            breaker.record_failure()
            logger.error("ai.chat_stream.unexpected type=%s err=%s",
                         type(e).__name__, e, exc_info=True)
            raise AIServiceError(operation="chat_stream")
