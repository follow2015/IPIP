# -*- coding: utf-8 -*-
"""RAG 知识库问答。"""
from typing import Any

from app.services.ai.llm_factory import create_llm_client
from app.services.ai.llm_base import LLMClient
from app.services.ai.prompt_guard import sanitize_user_input
from app.services.ai.rag_store import RAGStore, get_rag_store
from app.services.ai._runtime import observe_call, CallTimer
from app.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM = "你是 ipip 运维知识助手，仅依据下方【参考资料】回答，不得编造。"


class RAGService:
    """RAG 知识库问答服务层封装（检索 + 组装参考资料 + 调 LLM）。

    接线状态（d1 修正：原 docstring 称"预留未接线/全仓仅测试引用"，早已不实）：
    - HTTP 端点 `POST /rag/qa`（ai_routes.py）构造本类执行问答；
    - `rag.retrieve` capability（capabilities/builtin.py）走 RAGStore 检索供
      技能 YAML 编排使用——与本类是**两条并行入口**，不是替代关系。

    store 缺省时复用 `get_rag_store` 单例（A5）：每请求 new RAGStore() 会重建
    chromadb PersistentClient 并重新加载 embedding 权重，秒级阻塞。
    """

    def __init__(self, store: RAGStore = None, client: LLMClient = None):
        self.store = store or get_rag_store()
        self.client = client or create_llm_client()

    def ask(self, question: str, user_id: int = 0) -> str:
        if not self.client.is_configured():
            return "（AI 未配置）"
        safe_q = sanitize_user_input(question)
        refs = self.store.search(safe_q)
        context = "\n".join(f"- {r}" for r in refs) or "（无参考资料）"
        user = f"【参考资料】\n{context}\n\n【问题】{safe_q}"
        status = "ok"
        answer = ""
        audit_response: Any = None
        with CallTimer() as t:
            try:
                answer = self.client.chat(SYSTEM, user)
                audit_response = answer
            except Exception as e:  # noqa: BLE001
                status = "error"
                audit_response = {"error_type": type(e).__name__}
                logger.error("rag.ask_failed %s: %s", type(e).__name__, e, exc_info=True)
                raise
            finally:
                observe_call(scenario="rag", user_id=user_id,
                             request=safe_q, response=audit_response,
                             status=status, duration_ms=t.duration_ms,
                             model=getattr(self.client, "model", None),
                             base_url=getattr(self.client, "base_url", None))
        return answer
