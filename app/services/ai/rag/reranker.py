# -*- coding: utf-8 -*-
"""本地 rerank（cross-encoder）精排，RAG 精度提升的最后一环。

召回（RRF 融合）只解决"候选对不对"，排序仍基于向量距离/BM25 的启发式近似；
cross-encoder 把 (query, chunk) 成对输入打分，精度远高于双塔式独立编码。

配置项（环境变量）：
- RAG_RERANK_ENABLED: 1 启用（默认 1；模型缺失/加载失败自动降级 RRF，
  无本地模型的部署可显式设 0 关闭，避免反复尝试加载）
- RAG_RERANK_MODEL: 模型名，默认 BAAI/bge-reranker-base（CPU 友好；有 GPU 可换 v2-m3）
- RAG_RERANK_CANDIDATES: 参与重排的候选数上限，默认 30
- RAG_RERANK_MAX_LENGTH: cross-encoder 输入截断长度，默认 512

健壮性：
- 模型加载失败 / 推理异常一律返回 None，由调用方降级为 RRF 顺序；
- 失败后进入 5 分钟冷却窗，期间不再重复尝试加载（避免热路径反复撞模型下载）。
"""
import math
import os
import threading
import time
from typing import Any, List, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

_ENABLED = os.getenv("RAG_RERANK_ENABLED", "1") == "1"
_MODEL = os.getenv("RAG_RERANK_MODEL", "BAAI/bge-reranker-base")
_CANDIDATES = int(os.getenv("RAG_RERANK_CANDIDATES", "30"))
_MAX_LENGTH = int(os.getenv("RAG_RERANK_MAX_LENGTH", "512"))
_FAILURE_WINDOW_SECONDS = 300

_lock = threading.Lock()
_model_cache: dict = {}
_failure_until: float = 0.0


def is_enabled() -> bool:
    """是否启用 rerank（由 RAG_RERANK_ENABLED 控制）。"""
    return _ENABLED


def _sigmoid(x) -> float:
    """数值稳定的 sigmoid，把 cross-encoder logit 归一到 (0,1)。"""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.5
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _load_model():
    """加载 cross-encoder 模型（调用方持有 _lock）。失败抛异常由调用方冷却。"""
    if _MODEL in _model_cache:
        return _model_cache[_MODEL]
    from sentence_transformers import CrossEncoder
    model = CrossEncoder(_MODEL, max_length=_MAX_LENGTH)
    _model_cache[_MODEL] = model
    logger.info("reranker.model.loaded model=%s", _MODEL)
    return model


def _get_model():
    """带失败冷却的模型单例获取；不可用返回 None。"""
    global _failure_until
    now = time.monotonic()
    if now < _failure_until:
        return None
    with _lock:
        if _MODEL in _model_cache:
            return _model_cache[_MODEL]
        if time.monotonic() < _failure_until:  # 双重检查：等待锁期间可能已失败
            return None
        try:
            return _load_model()
        except Exception as e:  # noqa: BLE001
            _failure_until = time.monotonic() + _FAILURE_WINDOW_SECONDS
            logger.warning("reranker.model.load_failed model=%s err=%s（%ds 内不再重试）",
                           _MODEL, e, _FAILURE_WINDOW_SECONDS)
            return None


def rerank(query: str, chunks: List[dict], top_k: int) -> Optional[List[dict]]:
    """对融合后的候选做 cross-encoder 精排，返回前 top_k。

    Args:
        query: 用户原始检索词。
        chunks: RRF 融合后的候选（已按相关度降序，doc_id/text/score 齐备）。
        top_k: 返回条数。实际返回 min(top_k, len(chunks), _CANDIDATES) 条；
            超出上界安全截断，调用方无需预先 clamp。

    Returns:
        精排后的 chunk 列表（score 更新为 logit 的 sigmoid）；任何不可用场景返回
        None，由调用方降级为原 RRF 顺序（绝不抛异常）。
    """
    if not _ENABLED or not chunks:
        return None
    model = _get_model()
    if model is None:
        return None
    candidates = chunks[: min(_CANDIDATES, len(chunks))]
    try:
        logits = model.predict([(query, c["text"]) for c in candidates])
        scored = sorted(
            zip(candidates, logits),
            key=lambda pair: pair[1],
            reverse=True,
        )
        out = []
        for chunk, logit in scored[:top_k]:
            c = dict(chunk)
            c["score"] = _sigmoid(logit)
            c["score_source"] = "rerank"
            out.append(c)
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("reranker.predict_failed err=%s，降级为 RRF 顺序", e)
        return None
