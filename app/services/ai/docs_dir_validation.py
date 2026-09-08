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


def resolve_docs_root() -> str:
    """返回 AI_DOCS_ROOT 的真实绝对路径（不校验存在性）。

    AI_DOCS_ROOT 常被配成相对路径（.env 的 `AI_DOCS_ROOT=docs`）。相对路径依赖
    进程 CWD：后端不以项目根启动时（systemd / 其它目录拉起）会解析到错误位置，
    表现为「目录不存在」或误判越界。故统一按项目根解析，并对外暴露该真实路径
    （前端据此展示"文档根目录"，避免用户猜路径）。
    """
    from config import Config

    raw_root = Config.AI_DOCS_ROOT
    if not _os.path.isabs(raw_root):
        import config as _config

        project_root = _os.path.dirname(_os.path.abspath(_config.__file__))
        raw_root = _os.path.join(project_root, raw_root)
    return _os.path.realpath(raw_root)


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

    root = resolve_docs_root()
    docs_dir = docs_dir.strip()
    if _os.path.isabs(docs_dir):
        target = _os.path.realpath(_os.path.normpath(docs_dir))
    else:
        target = _os.path.realpath(_os.path.join(root, docs_dir))
    if target != root and not target.startswith(root + _os.sep):
        raise ValueError(
            f"docs_dir 越界，仅允许在文档根目录之下：{docs_dir}"
            "（请填相对路径，'.' 表示根目录本身）"
        )
    if not _os.path.isdir(target):
        raise ValueError(f"目录不存在：{docs_dir}（相对文档根目录；'.' 表示根目录本身）")
    return target
