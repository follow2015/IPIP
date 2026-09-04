# -*- coding: utf-8 -*-
"""RAG 入库目录的路径校验（白名单根目录约束）。

放在 services 层而非 api 层：Celery task（`app/tasks/ai_tasks.py`）也需要做同样
的校验作为纵深防御，若校验逻辑留在 api 层会造成 tasks → api 的反向依赖，
违反「任务层不依赖接口层」的分层约束。


路由层（`ai_routes.rag_ingest`）已经校验过一次，但 task 可能在路由之外被触发
（CLI、Flower、被攻破的 broker 投递的消息）。仅依赖调用方校验时，任何一条
绕过路由的入口都能让 `os.walk()` 读取任意目录内容并写入向量库——向量库内容
会被 RAG 检索出来进入 LLM 上下文，属于可读取服务器任意文件的信息泄露路径。
"""
import os as _os

from app.utils.logging import get_logger

logger = get_logger(__name__)


def validate_docs_dir(docs_dir: str) -> str:
    """校验 docs_dir 必须位于 AI_DOCS_ROOT 之下，返回真实绝对路径。

    Args:
        docs_dir: 用户传入的文档目录（相对或绝对路径）。

    Returns:
        校验通过后的真实绝对路径（已 realpath 解析）。

    Raises:
        ValueError: 类型非法、路径越界（含 `../` 穿越）或目录不存在。
    """
    from config import Config

    if not isinstance(docs_dir, str) or not docs_dir:
        raise ValueError("docs_dir 必须为非空字符串")

    root = _os.path.realpath(Config.AI_DOCS_ROOT)
    target = _os.path.realpath(_os.path.join(root, docs_dir))
    if target != root and not target.startswith(root + _os.sep):
        raise ValueError("docs_dir 越界，仅允许在文档根目录之下")
    if not _os.path.isdir(target):
        raise ValueError(f"目录不存在：{docs_dir}")
    return target
