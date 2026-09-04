# -*- coding: utf-8 -*-
"""Embedding function 工厂：默认 bge-small-zh-v1.5 本地中文模型。

配置项（环境变量）：
- RAG_EMBEDDING_PROVIDER: local_bge（默认）| openai | default
- RAG_EMBEDDING_MODEL: bge-small-zh-v1.5（默认）
- RAG_EMBEDDING_DIM: 512（默认，bge-small-zh-v1.5 输出维度）

单例缓存：首次调用加载模型权重（~2-3 秒），后续调用复用。
"""
import os
from typing import Any, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

_ef_cache: dict[str, Any] = {}

_PROVIDER = os.getenv("RAG_EMBEDDING_PROVIDER", "local_bge")
_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
_DIM = int(os.getenv("RAG_EMBEDDING_DIM", "512"))


def get_embedding_function() -> Optional[Any]:
    """返回 chromadb embedding_function，None 表示用 chromadb 默认。

    单例缓存按 provider+model 维度，避免每次 RAGStore() 实例化都重载权重。
    失败时抛异常，由调用方（RAGStore.__init__）决定 fallback 还是抛错。
    """
    cache_key = f"{_PROVIDER}:{_MODEL}"
    if cache_key in _ef_cache:
        return _ef_cache[cache_key]

    if _PROVIDER == "default":
        _ef_cache[cache_key] = None
        return None

    if _PROVIDER == "local_bge":
        try:
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )
        except ImportError as e:
            raise ImportError(
                "SentenceTransformerEmbeddingFunction 不可用，请 pip install sentence-transformers"
            ) from e
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        logger.info("loading embedding model %s (dim=%d, offline)", _MODEL, _DIM)
        ef = SentenceTransformerEmbeddingFunction(model_name=_MODEL)
        _ef_cache[cache_key] = ef
        return ef

    if _PROVIDER == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("RAG_EMBEDDING_PROVIDER=openai 但 OPENAI_API_KEY 未设置")
        try:
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        except ImportError as e:
            raise ImportError("OpenAIEmbeddingFunction 不可用") from e
        ef = OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name=os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small"),
        )
        _ef_cache[cache_key] = ef
        return ef

    raise ValueError(f"未知 RAG_EMBEDDING_PROVIDER: {_PROVIDER}")


def get_embedding_dim() -> int:
    """返回当前 embedding 维度，供重建脚本校验。"""
    return _DIM
