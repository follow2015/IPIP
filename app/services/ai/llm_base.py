# -*- coding: utf-8 -*-
"""LLM 客户端抽象基类。

各 provider（OpenAI 兼容/Anthropic/私有网关）实现此接口，
服务层通过 LLMClient 注入，与具体 provider 解耦。
"""
from abc import ABC, abstractmethod


class LLMClient(ABC):
    """LLM 客户端抽象接口。"""

    @abstractmethod
    def is_configured(self) -> bool:
        """是否已配置可用。"""

    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """发起一次对话补全，返回文本内容。

        Raises:
            ExternalServiceError: 任意调用异常统一映射
        """

    @abstractmethod
    def chat_stream(self, system_prompt: str, user_prompt: str):
        """流式对话，yield 逐 token 文本。

        Raises:
            ExternalServiceError: 任意调用异常统一映射
        """
