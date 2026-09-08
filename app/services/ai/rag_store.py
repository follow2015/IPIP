# -*- coding: utf-8 -*-
"""本地向量库（chromadb）+ FTS5 关键词索引，RAG 混合检索。"""
import hashlib
import os
import threading
from typing import List, Optional

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
try:
    import posthog as _posthog
    _posthog.disabled = True
    _posthog.capture = lambda *args, **kwargs: None  # type: ignore[assignment]
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


_CHUNK_CHARS = int(os.getenv("RAG_CHUNK_CHARS", "800"))
_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "80"))

_POOL = int(os.getenv("RAG_CANDIDATE_POOL", "20"))
_RRF_K = 60


def _split_blocks(text: str) -> list:
    """把单个文档切成检索块。

    策略：字符窗口 + 优先在换行符处断块（段落边界更自然），
    相邻块保留 overlap 字符重叠，缓解跨块语义割裂。

    Args:
        text: 原始文档全文。

    Returns:
        文本块列表；短文本（≤ 单块上限）原样返回单块。
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= _CHUNK_CHARS:
        return [text]
    blocks: list = []
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_CHARS, len(text))
        if end < len(text):
            cut = text.rfind("\n", start, end)
            if cut != -1 and cut > start + _CHUNK_CHARS // 2:
                end = cut
        block = text[start:end].strip()
        if block:
            blocks.append(block)
        if end >= len(text):
            break
        start = max(end - _CHUNK_OVERLAP, start + 1)  # 保证推进，防死循环
    return blocks


def _chunk_doc_id(domain: str, source: str, block: str) -> str:
    """块级 doc_id：与切分顺序无关（内容稳定则幂等）。

    前缀 c- 与旧版"整文 md5"id 区分，避免新旧粒度在同一 collection 混存冲突。
    同一块内容重复出现（文件间重复段落）自然去重合并。
    """
    return "c-" + hashlib.md5(f"{domain}\x00{source}\x00{block}".encode()).hexdigest()[:16]


def _rrf_fuse(vec_chunks: list, kw_chunks: list) -> list:
    """RRF（Reciprocal Rank Fusion）融合两路召回，按融合分降序返回。

    对每个 doc 累加其在各路的名次贡献 1/(K+rank+1)（rank 从 0 起），
    只命中一路时仅计一路贡献。输出 score 重派生为 1/(1+排名) 以保持
    0-1 量纲（confidence.rag_relevance 依赖 Top-1 score，不能给原始 RRF 小值）。

    Args:
        vec_chunks: 向量路召回（按相似度降序）。
        kw_chunks: 关键词路召回（按 bm25 名次升序）。

    Returns:
        融合排序后的 chunk 列表，各带 vector_rank/keyword_rank/score/score_source。
    """
    merged: dict = {}
    for rank0, c in enumerate(vec_chunks):
        e = merged.setdefault(c["doc_id"], {"chunk": c, "vec_rank": None, "kw_rank": None})
        e["vec_rank"] = rank0
    for rank0, c in enumerate(kw_chunks):
        e = merged.setdefault(c["doc_id"], {"chunk": c, "vec_rank": None, "kw_rank": None})
        e["kw_rank"] = rank0

    scored = []
    for did, e in merged.items():
        s = 0.0
        if e["vec_rank"] is not None:
            s += 1.0 / (_RRF_K + e["vec_rank"] + 1)
        if e["kw_rank"] is not None:
            s += 1.0 / (_RRF_K + e["kw_rank"] + 1)
        chunk = dict(e["chunk"])
        chunk["vector_rank"] = e["vec_rank"]
        chunk["keyword_rank"] = e["kw_rank"]
        scored.append((s, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for i, (_rrf, chunk) in enumerate(scored):
        chunk = dict(chunk)
        chunk["score"] = 1.0 / (1.0 + i)
        chunk["score_source"] = "rrf_rank"
        out.append(chunk)
    return out


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

        self._meta_ready: Optional[bool] = None

    def ingest(self, texts: List[str], domain: str = "code_wiki",
               source: str = "docs") -> None:
        """入库文档（自动分块，块为检索单元）。

        每个文本切成长度受限的块；向量库与 FTS5 都以块粒度写入，metadata
        携带 domain/source 供检索按域过滤。块级 doc_id 与顺序无关，内容
        稳定则重复 ingest 幂等（upsert）。

        同批重复块会被丢弃（见下方 D1 说明），因此幂等性不受影响。
        """
        if not self.available:
            return
        blocks: List[str] = []
        ids: List[str] = []
        metas: List[dict] = []
        seen_ids: set = set()
        for t in texts:
            for block in _split_blocks(t):
                doc_id = _chunk_doc_id(domain, source, block)
                if doc_id in seen_ids:
                    continue
                seen_ids.add(doc_id)
                blocks.append(block)
                ids.append(doc_id)
                metas.append({"domain": domain, "source": source})
        if not ids:
            return
        self.col.upsert(ids=ids, documents=blocks, metadatas=metas)
        if self.kw_index is not None:
            for doc_id, block in zip(ids, blocks):
                try:
                    self.kw_index.upsert(doc_id, domain, block, source)
                except Exception as e:  # noqa: BLE001
                    logger.warning("rag.kw_upsert_failed doc=%s %s", doc_id, e)
        self._meta_ready = True

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
        """混合检索：向量 + 关键词两路召回 → RRF 融合 → 可选本地 rerank 精排。

        检索单元为块。返回结果按相关度降序（供 confidence 取 Top-1 score）。
        score 统一归一在 (0,1]：
        - 未启用 rerank：RRF 名次派生 1/(1+rank)；
        - 启用 rerank：cross-encoder logit 的 sigmoid。
        """
        if not self.available:
            return []
        pool_k = max(top_k, _POOL)

        where = None
        meta_ready = self._get_meta_ready()
        if meta_ready:
            where = {"domain": domain}
        elif self.col.count() > 0:
            logger.warning(
                "rag.collection 缺少 domain metadata（旧库格式），向量路无法按域过滤。"
                "建议 reset() 重建后重新 ingest。"
            )

        query_kwargs = {"query_texts": [query], "n_results": pool_k}
        if where is not None:
            query_kwargs["where"] = where
        try:
            vec_res = self.col.query(**query_kwargs)
        except Exception as e:  # noqa: BLE001
            logger.warning("rag.vec_query_failed where=%s err=%s，降级为不过滤", where, e)
            vec_res = self.col.query(query_texts=[query], n_results=pool_k)
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
        kw_chunks = self.keyword_search(query, domain, pool_k)
        fused = _rrf_fuse(vec_chunks, kw_chunks)
        if not fused:
            return []
        try:
            from app.services.ai.rag import reranker
            if reranker.is_enabled():
                reranked = reranker.rerank(query, fused, top_k)
                return reranked if reranked is not None else fused[:top_k]
        except Exception as e:  # noqa: BLE001
            logger.warning("rag.rerank_unavailable %s", e)
        return fused[:top_k]

    def _get_meta_ready(self) -> bool:
        """查询集合是否含 domain metadata（惰性探测并缓存）。

        探测用 col.get(limit=1)：空集合或全无 metadata 时返回 False；
        ingest 写入后置 True；reset 重建后置 None 待下次探测。
        """
        if self._meta_ready is None:
            try:
                res = self.col.get(limit=1)
                metas = res.get("metadatas") or []
                self._meta_ready = bool(
                    metas and isinstance(metas[0], dict) and "domain" in metas[0])
            except Exception as e:  # noqa: BLE001
                logger.warning("rag.meta_probe_failed %s", e)
                self._meta_ready = False
        return self._meta_ready


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
            self._meta_ready = None
            _store_cache.clear()
