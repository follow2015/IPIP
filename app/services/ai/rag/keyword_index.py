# -*- coding: utf-8 -*-
"""基于 SQLite FTS5 的关键词检索，补足向量检索对精确匹配的召回短板。

tokenchars '-./_' 把连字符/点号/斜杠/下划线划入词内字符，
避免 Err-Disable / Gig0/1 / 12.4 / VLAN_100 被 FTS5 默认分词拆碎。
查询侧统一 phrase 包裹，绕开 - 被解析为 NOT、* 被解析为前缀等操作符陷阱。
"""
import sqlite3
import threading
from typing import Any

from app.services.ai.rag.tokenizer import tokenize


class KeywordIndex:
    _TOKENCHARS = "-./_"
    _CREATE_SQL = (
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5("
        "doc_id UNINDEXED, domain UNINDEXED, text, source UNINDEXED, "
        'tokenize = "unicode61 remove_diacritics 2 tokenchars \'-./_\'")'
    )

    def __init__(self, db_path: str = "instance/rag_fts.db"):
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")  # 并发写安全
        self.conn.execute(self._CREATE_SQL)

    def upsert(self, doc_id: str, domain: str, text: str, source: str):
        tokenized = tokenize(text)  # 预分词
        with self._lock:
            self.conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            self.conn.execute(
                "INSERT INTO chunks(doc_id, domain, text, source) VALUES (?, ?, ?, ?)",
                (doc_id, domain, tokenized, source),
            )
            self.conn.commit()

    def search(self, domain: str, query: str, top_k: int, where: dict = None) -> list[dict]:
        tokenized_q = tokenize(query)  # 查询侧同样预分词
        safe_q = self._escape_query(tokenized_q)
        if not safe_q:
            return []
        if where is not None:
            raise NotImplementedError("metadata 过滤待 Task 7.3 实现")
        with self._lock:
            cur = self.conn.execute(
                "SELECT doc_id, text, source, rank FROM chunks "
                "WHERE domain = ? AND chunks MATCH ? ORDER BY rank LIMIT ?",
                (domain, safe_q, top_k),
            )
            rows = cur.fetchall()
        return [self._row_to_chunk(r, domain, rank=i) for i, r in enumerate(rows)]

    def _escape_query(self, query: str) -> str:
        """FTS5 MATCH 转义：对每个 token 用双引号包裹成 phrase，绕开 - / NOT / * 等操作符解析。
        统一 phrase 包裹最稳，对纯中文 token 无副作用。代价是无法用前缀匹配 err*，
        但运维场景要的是精确匹配错误码，不是前缀模糊，可接受。

        语义变化：FTS5 MATCH 默认 OR 语义（token1 token2 匹配含任一 token 的文档）。
        phrase 包裹后变为 AND 语义（"token1" "token2" 要求所有 token 都匹配）。
        对运维场景这是期望行为：用户输入多词时通常每个词都有信息量
        （设备类型 + 故障现象），AND 语义减少噪音比 OR 更合理。
        若后续需要 OR 语义（如"交换机 端口 闪断"任一命中即可），
        可改为 ' OR '.join(f'"{t}"' for t in tokens)，但需评估噪音引入。"""
        tokens = [t for t in query.split() if t.strip()]
        return " ".join(f'"{t}"' for t in tokens)

    def _row_to_chunk(self, row, domain: str, rank: int = 0) -> dict:
        return {
            "doc_id": row[0],
            "text": row[1],
            "source": row[2],
            "domain": domain,
            "metadata": {},
            "keyword_rank": rank,
            "score": 1.0 / (1.0 + rank),
            "score_source": "keyword_rank",
        }

    def close(self):
        self.conn.close()

    def delete(self, doc_id: str):
        """删除指定文档的 FTS5 索引行。"""
        with self._lock:
            self.conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            self.conn.commit()

    def reset(self):
        """清空整个 FTS5 索引表。"""
        with self._lock:
            self.conn.execute("DELETE FROM chunks")
            self.conn.commit()
