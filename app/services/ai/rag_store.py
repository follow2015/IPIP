# -*- coding: utf-8 -*-
"""本地向量库（chromadb）+ FTS5 关键词索引，RAG 混合检索。"""
import hashlib
import os
import threading
from typing import List

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
try:
    import posthog as _posthog
    _posthog.disabled = True
except ImportError:  # pragma: no cover
    pass

try:
    import chromadb
    _HAS_CHROMA = True
except ImportError:  # pragma: no cover
    _HAS_CHROMA = False

from app.utils.logging import get_logger

logger = get_logger(__name__)

_store_cache: dict = {}
_store_lock = threading.Lock()


def _distance_to_score(distance, rank: int) -> float:
    """把向量距离换算为 0-1 相似度分数。

    chromadb 默认 L2 距离无上界，直接 1-distance 会得到负值，故用
    1/(1+distance) 做单调映射（distance≥0 时落在 (0,1]）。距离缺失时
    退化为名次派生，保证 score 字段始终可用。
    """
    if distance is None:
        return 1.0 / (1.0 + rank)
    try:
        d = float(distance)
    except (TypeError, ValueError):
        return 1.0 / (1.0 + rank)
    if d < 0:
        return 1.0
    return 1.0 / (1.0 + d)


def get_rag_store(persist_dir: str = "instance/chroma", collection: str = "ipip_kb",
                  fts_db: str = "instance/rag_fts.db") -> "RAGStore":
    """获取 RAGStore 实例（按构造参数单例复用）。

    仅缓存实例本身，不对其 search/ingest 调用加锁：各调用方原本就是各自 new 实例
    指向同一份持久化文件，共享单一实例并不会额外引入并发风险，反而避免多客户端
    竞争同一库文件。构造失败（如 embedding 加载失败且 collection 已存在）时
    异常直接抛出且不写入缓存，后续调用可重试。

    Args:
        persist_dir: chromadb 持久化目录。
        collection: collection 名称。
        fts_db: FTS5 关键词索引库路径。

    Returns:
        复用的或新建的 RAGStore 实例。
    """
    key = (persist_dir, collection, fts_db)
    store = _store_cache.get(key)
    if store is not None:
        return store
    with _store_lock:
        store = _store_cache.get(key)
        if store is None:
            store = RAGStore(persist_dir, collection, fts_db)
            _store_cache[key] = store
        return store


class RAGStore:
    def __init__(self, persist_dir: str = "instance/chroma", collection: str = "ipip_kb",
                 fts_db: str = "instance/rag_fts.db"):
        self.available = _HAS_CHROMA
        if not self.available:
            return
        self.client = chromadb.PersistentClient(path=persist_dir,
                                                  settings=chromadb.Settings(anonymized_telemetry=False))

        existing = [c.name for c in self.client.list_collections()]
        collection_exists = collection in existing

        try:
            from app.services.ai.rag.embedding import get_embedding_function
            ef = get_embedding_function()
        except Exception as e:
            if collection_exists:
                raise RuntimeError(
                    f"collection 已存在但 embedding 加载失败，无法降维: {e}"
                ) from e
            else:
                logger.warning("bge embedding 加载失败，fallback 到默认 all-MiniLM-L6-v2: %s", e)
                ef = None
        self.col = self.client.get_or_create_collection(
            collection, embedding_function=ef
        )
        self._ef = ef

        self.kw_index = None
        try:
            from app.services.ai.rag.keyword_index import KeywordIndex
            self.kw_index = KeywordIndex(fts_db)
        except Exception as e:
            logger.warning("FTS5 关键词索引初始化失败，降级为纯向量检索: %s", e)

    def ingest(self, texts: List[str], domain: str = "code_wiki",
               source: str = "docs") -> None:
        if not self.available:
            return
        seen: set[str] = set()
        unique_texts: List[str] = []
        unique_ids: List[str] = []
        for t in texts:
            doc_id = f"doc-{hashlib.md5(t.encode()).hexdigest()[:16]}"
            if doc_id in seen:
                continue
            seen.add(doc_id)
            unique_ids.append(doc_id)
            unique_texts.append(t)
        self.col.upsert(ids=unique_ids, documents=unique_texts)
        if self.kw_index is not None:
            for doc_id, text in zip(unique_ids, unique_texts):
                self.kw_index.upsert(doc_id, domain, text, source)

    def search(self, query: str, top_k: int = 3) -> List[str]:
        """向量检索（保持向后兼容）。混合检索用 hybrid_search。"""
        if not self.available:
            return []
        res = self.col.query(query_texts=[query], n_results=top_k)
        return res["documents"][0] if res.get("documents") else []

    def keyword_search(self, query: str, domain: str = "code_wiki",
                       top_k: int = 5) -> list[dict]:
        """FTS5 关键词检索，返回 RetrievedChunk 结构。"""
        if self.kw_index is None:
            return []
        return self.kw_index.search(domain, query, top_k)

    def hybrid_search(self, query: str, domain: str = "code_wiki",
                      top_k: int = 5) -> list[dict]:
        """混合检索：向量 + 关键词两路并行召回，返回候选集（RRF 融合留到 Task 7.3）。

        当前实现：两路独立召回，合并去重，不融合排序。
        Task 7.3 接入 RRF 后此方法返回融合排序结果。"""
        if not self.available:
            return []
        vec_res = self.col.query(query_texts=[query], n_results=top_k)
        vec_docs = vec_res.get("documents", [[]])[0]
        vec_ids = vec_res.get("ids", [[]])[0]
        vec_dists = (vec_res.get("distances") or [[]])[0]
        vec_chunks = [
            {"doc_id": vec_ids[i] if i < len(vec_ids) else f"vec-{i}",
             "text": doc, "source": "vector", "domain": domain,
             "metadata": {}, "vector_rank": i, "keyword_rank": None,
             "score": _distance_to_score(
                 vec_dists[i] if i < len(vec_dists) else None, i),
             "score_source": "vector_distance"}
            for i, doc in enumerate(vec_docs)
        ]
        kw_chunks = self.keyword_search(query, domain, top_k)
        by_id = {}
        for c in vec_chunks + kw_chunks:
            prev = by_id.get(c["doc_id"])
            if prev is None or (c.get("score") or 0) > (prev.get("score") or 0):
                by_id[c["doc_id"]] = c
        return sorted(by_id.values(), key=lambda c: c.get("score") or 0, reverse=True)


    def ingest_from_docs(self, docs_dir: str, domain: str = "code_wiki") -> int:
        """从目录批量入库 .md/.txt 文档，返回入库数。"""
        if not self.available:
            return 0
        texts: List[str] = []
        for root, _dirs, files in os.walk(docs_dir):
            for fname in files:
                if fname.endswith((".md", ".txt")):
                    path = os.path.join(root, fname)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            texts.append(f.read())
                    except (OSError, UnicodeDecodeError) as e:
                        logger.warning("rag.ingest.skip file=%s err=%s", path, e)
                        continue
        if texts:
            self.ingest(texts, domain=domain, source=docs_dir)
        return len(texts)


    def count(self) -> int:
        """返回向量库中文档总数。"""
        if not self.available:
            return 0
        try:
            return self.col.count()
        except Exception as e:  # noqa: BLE001
            logger.warning("rag.count_failed %s", e)
            return 0

    def list_docs(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """列出知识库文档（分页，返回 doc_id + 片段预览）。"""
        if not self.available:
            return []
        try:
            res = self.col.get(limit=limit, offset=offset)
            ids = res.get("ids", [])
            docs = res.get("documents", [])
            return [
                {"doc_id": ids[i], "preview": (docs[i][:200] if i < len(docs) else "")}
                for i in range(len(ids))
            ]
        except Exception as e:  # noqa: BLE001
            logger.warning("rag.list_docs_failed %s", e)
            return []

    def delete_doc(self, doc_id: str) -> None:
        """删除指定文档（向量库 + FTS5 索引）。"""
        if not self.available:
            return
        self.col.delete(ids=[doc_id])
        if self.kw_index is not None:
            try:
                self.kw_index.delete(doc_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("rag.kw_delete_failed doc=%s %s", doc_id, e)

    def reset(self) -> None:
        """清空知识库（删除 collection + FTS5 索引，下次 ingest 自动重建）。

        I2 修复：reset 后重建 self.col，避免旧实例指向已删除 collection。
        """
        if not self.available:
            return
        with _store_lock:
            try:
                self.client.delete_collection(self.col.name)
            except Exception as e:  # noqa: BLE001
                logger.warning("rag.reset.delete_collection_failed %s", e)
            if self.kw_index is not None:
                try:
                    self.kw_index.reset()
                except Exception as e:  # noqa: BLE001
                    logger.warning("rag.reset.kw_failed %s", e)
            try:
                self.col = self.client.get_or_create_collection(
                    self.col.name if hasattr(self, 'col') else "ipip_kb",
                    embedding_function=getattr(self, '_ef', None),
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("rag.reset.recreate_collection_failed %s", e)
            _store_cache.clear()
