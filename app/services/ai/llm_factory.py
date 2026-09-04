# -*- coding: utf-8 -*-
"""LLM provider 工厂注册中心。

新增 provider 只需：
1. 在 app/services/ai/providers/ 新建文件
2. 实现 LLMClient 接口
3. 用 @register_provider("xxx") 装饰
4. config.py 设 AI_PROVIDER="xxx"

注册时机：模块顶层 import providers 包，确保 @register_provider 装饰器在
import llm_factory 时即执行注册，_REGISTRY 立即非空，不依赖"谁先调用了
create_llm_client"这种隐式时序（六轮评审修复）。

Client 单例复用（连接池）：按 (provider, api_key, base_url, model, timeout)
维度缓存实例，配置变更时键变化自动失效新建，避免高并发下重复建连耗尽连接池。
"""
from typing import Dict, Type, Tuple

from app.services.ai.llm_base import LLMClient
from config import Config
from app.utils.logging import get_logger

logger = get_logger(__name__)

_REGISTRY: Dict[str, Type[LLMClient]] = {}

_CLIENT_CACHE: Dict[Tuple, LLMClient] = {}


def register_provider(name: str):
    """装饰器：注册 LLM provider 到工厂。"""
    def decorator(cls: Type[LLMClient]) -> Type[LLMClient]:
        if name in _REGISTRY:
            logger.warning("llm.provider.reregister name=%s old=%s new=%s",
                           name, _REGISTRY[name].__name__, cls.__name__)
        _REGISTRY[name] = cls
        return cls
    return decorator


from app.services.ai import providers  # noqa: F401,E402


def list_providers() -> list:
    """返回已注册 provider 名列表（供配置校验等使用）。"""
    return list(_REGISTRY.keys())


def _client_cache_key(provider_name: str) -> Tuple:
    """构造单例缓存键。配置变更时键变化 → 自动失效新建。"""
    return (
        provider_name,
        Config.AI_API_KEY,
        Config.AI_BASE_URL,
        Config.AI_MODEL,
        Config.AI_TIMEOUT,
    )


def create_llm_client() -> LLMClient:
    """根据 Config.AI_PROVIDER 创建/复用 LLM 客户端实例。

    单例缓存按 (provider, api_key, base_url, model, timeout) 维度，
    配置变更时键变化自动新建，既复用连接池又避免用到旧凭据/旧端点。
    """
    provider_name = Config.AI_PROVIDER
    if provider_name not in _REGISTRY:
        raise ValueError(
            f"未注册的 AI_PROVIDER={provider_name!r}，已注册: {list(_REGISTRY.keys())}"
        )
    key = _client_cache_key(provider_name)
    client = _CLIENT_CACHE.get(key)
    if client is not None:
        return client
    cls = _REGISTRY[provider_name]
    client = cls()
    _CLIENT_CACHE[key] = client
    logger.info("llm.factory.create provider=%s cls=%s (cached)", provider_name, cls.__name__)
    return client


def invalidate_client_cache() -> None:
    """清空 client 单例缓存。配置变更后调用，强制下次 create_llm_client 新建。"""
    _CLIENT_CACHE.clear()
