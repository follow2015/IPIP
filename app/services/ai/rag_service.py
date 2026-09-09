# -*- coding: utf-8 -*-
"""RAG 知识库问答。"""
from typing import Any, Dict, List

from app.services.ai.llm_factory import create_llm_client
from app.services.ai.llm_base import LLMClient
from app.services.ai.prompt_guard import sanitize_user_input
from app.services.ai.rag_store import RAGStore, get_rag_store
from app.services.ai._runtime import bind_scenario, observe_call, CallTimer
from app.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM = "你是 ipip 运维知识助手，仅依据下方【参考资料】回答，不得编造。"

LOCAL_MODE_NOTICE = "【本地检索模式】以下结果仅来自本地知识库检索，没有 LLM 模型参与生成。"
LOCAL_MODE_REASON = {
    "not_configured": "原因：AI 未配置（尚未完成模型配置）。",
    "service_error": "原因：AI 模型服务不可用（连接失败 / 超时 / 限流等）。",
}


class RAGService:
    """RAG 知识库问答服务层封装（检索 + 组装参考资料 + 调 LLM）。

    接线状态（d1 修正：原 docstring 称"预留未接线/全仓仅测试引用"，早已不实）：
    - HTTP 端点 `POST /rag/qa`（ai_routes.py）构造本类执行问答；
    - `rag.retrieve` capability（capabilities/builtin.py）走 RAGStore 检索供
      技能 YAML 编排使用——与本类是**两条并行入口**，不是替代关系。

    store 缺省时复用 `get_rag_store` 单例（A5）：每请求 new RAGStore() 会重建
    chromadb PersistentClient 并重新加载 embedding 权重，秒级阻塞。

    降级约定（与其他 AI 能力不同）：本服务**不因 LLM 不可用而报错**。
    资料全在本地，LLM 缺失只影响"总结归纳"，不影响"查到资料"，
    故 LLM 不可用 → 返回本地命中原文（degraded=True）而非抛异常。
    """

    _MAX_REF_CHARS = 3000
    _MAX_CONTEXT_CHARS = 8000

    def __init__(self, store: RAGStore = None, client: LLMClient = None):
        self.store = store or get_rag_store()
        self.client = client or create_llm_client()

    def ask(self, question: str, user_id: int = 0) -> Dict[str, Any]:
        """知识库问答。

        Returns:
            {"answer": str, "degraded": bool, "references": list[dict]}
            - LLM 可用：answer 为模型生成内容，degraded=False，references 为空；
            - LLM 不可用（未配置 / 服务错误）：降级为本地检索模式，
              answer 为命中原文片段并在顶部标注"仅本地检索、无 LLM 参与"，
              degraded=True，references 为结构化命中列表。
        """
        safe_q = sanitize_user_input(question)
        refs = self._retrieve(safe_q)

        if not self.client.is_configured():
            logger.info("rag.local_mode reason=not_configured q_len=%d", len(safe_q))
            return self._local_result(refs, reason="not_configured")

        context = self._build_context(refs)
        user = f"【参考资料】\n{context}\n\n【问题】{safe_q}"
        status = "ok"
        answer = ""
        audit_response: Any = None
        with bind_scenario("rag"), CallTimer() as t:
            try:
                answer = self.client.chat(SYSTEM, user)
                audit_response = answer
            except Exception as e:  # noqa: BLE001
                status = "degraded"
                audit_response = {"error_type": type(e).__name__}
                logger.error("rag.ask_failed %s: %s", type(e).__name__, e, exc_info=True)
                return self._local_result(refs, reason="service_error")
            finally:
                observe_call(scenario="rag", user_id=user_id,
                             request=safe_q, response=audit_response,
                             status=status, duration_ms=t.elapsed_ms(),
                             model=getattr(self.client, "model", None),
                             base_url=getattr(self.client, "base_url", None))
        return {"answer": answer, "degraded": False, "references": []}

    def _retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """本地混合检索；失败逐层降级（hybrid → 向量 → 空）。"""
        chunks = None
        try:
            chunks = self.store.hybrid_search(query, top_k=top_k)
        except Exception as e:  # noqa: BLE001
            logger.warning("rag.hybrid_search_failed %s: %s", type(e).__name__, e)

        if isinstance(chunks, list) and chunks:
            return [
                {"doc_id": c.get("doc_id"), "text": c.get("text", ""),
                 "score": c.get("score")}
                for c in chunks if isinstance(c, dict)
            ]

        try:
            docs = self.store.search(query) or []
        except Exception as e:  # noqa: BLE001
            logger.warning("rag.search_failed %s: %s", type(e).__name__, e)
            return []
        return [{"doc_id": None, "text": d, "score": None}
                for d in docs if isinstance(d, str)]

    @classmethod
    def _build_context(cls, refs: List[Dict[str, Any]]) -> str:
        """组装喂给 LLM 的参考资料（限长）。

        旧库为整文入库（单篇可达数万字符），不加限制会把 prompt 撑到几十 k
        tokens；叠加思考型模型把输出配额耗在思维链上，最终会返回空答案。
        """
        parts: List[str] = []
        total = 0
        for r in refs:
            text = r.get("text", "") or ""
            if len(text) > cls._MAX_REF_CHARS:
                text = text[:cls._MAX_REF_CHARS] + "…（片段已截断）"
            if total + len(text) > cls._MAX_CONTEXT_CHARS:
                break
            parts.append(text)
            total += len(text)
        return "\n".join(f"- {t}" for t in parts) or "（无参考资料）"

    @classmethod
    def _local_result(cls, refs: List[Dict[str, Any]], reason: str) -> Dict[str, Any]:
        """组装本地检索模式的结果（带"无 LLM 参与"提示）。"""
        notice = LOCAL_MODE_NOTICE + LOCAL_MODE_REASON.get(reason, "")
        if not refs:
            return {
                "answer": notice + "\n\n未检索到相关内容（知识库可能为空或尚未入库）。",
                "degraded": True,
                "references": [],
            }
        lines = [notice, "", f"命中 {len(refs)} 条相关片段（按相关度排序）："]
        references = []
        for i, r in enumerate(refs, 1):
            text = r.get("text", "") or ""
            if len(text) > cls._MAX_REF_CHARS:
                text = text[:cls._MAX_REF_CHARS] + "…（片段已截断，完整内容见知识库管理）"
            lines.append(f"\n[{i}] {r.get('doc_id') or '-'}\n{text}")
            references.append({"doc_id": r.get("doc_id"), "text": text,
                               "score": r.get("score")})
        return {
            "answer": "\n".join(lines),
            "degraded": True,
            "references": references,
        }
