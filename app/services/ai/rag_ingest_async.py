# -*- coding: utf-8 -*-
"""RAG 异步入库 + SSE 进度推送。

执行引擎：Celery task `rag_ingest_task`（方案 §Phase 3）。本模块承载
**入库实现本身**（`run_ingest`），由两条执行路径共用：
- Celery 路径：`app/tasks/ai_tasks.py:rag_ingest_task` 委托 `run_ingest`；
- 同步回退路径（`AI_ASYNC_ENABLED=0`）：本模块的线程池委托 `run_ingest`。

单一实现避免两份副本漂移（H2 修复）。

对外接口：
- `ingest_async`：入队入口（路由层调用），生成 task_id 并 `apply_async`；
- `get_progress`：SSE 进度生成器（通用进度端点复用）。

`AI_ASYNC_ENABLED=0` 时回退到进程内 ThreadPoolExecutor（短期兜底，验证稳定后移除）。
"""
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Generator, List, Optional

from flask import current_app

from app.services.ai.docs_dir_validation import validate_docs_dir
from app.services.ai.rag_store import get_rag_store
from app.services.ai import task_state
from app.utils.logging import get_logger

logger = get_logger(__name__)

_SUPPORTED_SUFFIXES = (".md", ".txt")

_executor = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """惰性创建同步回退路径的线程池。"""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=2,
                                               thread_name_prefix="rag-ingest")
    return _executor


def _collect_files(docs_dir: str) -> List[str]:
    """收集目录下所有待入库文档。

    Args:
        docs_dir: 已过白名单校验的目录绝对路径。

    Returns:
        文件路径列表。
    """
    files = []
    for root, _dirs, fnames in os.walk(docs_dir):
        for f in fnames:
            if f.endswith(_SUPPORTED_SUFFIXES):
                files.append(os.path.join(root, f))
    return files


def _save_progress(task_id: str, status: str, progress: int, total: int,
                   result: Any = None, user_id: Optional[int] = None) -> None:
    """写入进度状态。

    Args:
        task_id: 任务 ID。
        status: pending / running / done / error。
        progress/total: 已处理 / 总数。
        result: 结果负载。
        user_id: 发起用户（归属校验用，见 §6.3）。
    """
    task_state.save(task_id, {"status": status, "progress": progress,
                              "total": total, "result": result,
                              "user_id": user_id})


def run_ingest(task_id: str, docs_dir: str, user_id: Optional[int] = None) -> int:
    """执行文档入库（Celery 路径与同步回退路径共用的唯一实现）。

    在 task 内重复校验 docs_dir（H1 修复）：路由层已校验过，但 task 可能被路由
    之外的入口触发（CLI / Flower / 被攻破的 broker）。仅依赖调用方校验时，任
    何绕过路由的入口都能读取任意目录内容——而这些内容会经 RAG 检索进入 LLM
    上下文，构成信息泄露路径。

    Args:
        task_id: 任务 ID（进度键）。
        docs_dir: 待入库文档目录。
        user_id: 发起用户 ID。

    Returns:
        成功入库的文档数。

    Raises:
        ValueError: docs_dir 越界或不存在。
        Exception: 读取 / 入库过程中的异常交由调用方处理。
    """
    safe_dir = validate_docs_dir(docs_dir)

    store = get_rag_store()
    files = _collect_files(safe_dir)
    total = len(files)
    _save_progress(task_id, "running", 0, total, None, user_id)

    texts = []
    for i, path in enumerate(files):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                texts.append(fh.read())
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("rag.async.skip %s %s", path, e)
        _save_progress(task_id, "running", i + 1, total, None, user_id)

    if texts:
        store.ingest(texts)
    _save_progress(task_id, "done", total, total, len(texts), user_id)
    return len(texts)


def _run_ingest_sync(task_id: str, docs_dir: str, user_id: Optional[int] = None) -> None:
    """同步回退路径的入库包装（ThreadPoolExecutor 内执行）。

    线程池内的线程没有 app context，故需显式包裹。异常不 re-raise——线程池
    的 future 无人消费，抛出也无人可处理，仅需落库与记日志。

    Args:
        task_id: 任务 ID。
        docs_dir: 待入库文档目录。
        user_id: 发起用户 ID。
    """
    app = current_app._get_current_object()
    with app.app_context():
        try:
            run_ingest(task_id, docs_dir, user_id)
        except Exception as e:  # noqa: BLE001
            _save_progress(task_id, "error", 0, 0, type(e).__name__, user_id)
            logger.warning("rag.async.failed %s", e)


def ingest_async(docs_dir: str, user_id: Optional[int] = None) -> str:
    """提交异步入库任务，立即返回 task_id。

    v3（方案 §Phase 3）：执行引擎从 ThreadPoolExecutor 切换为 Celery task
    `rag_ingest_task`。`AI_ASYNC_ENABLED=0` 时回退到进程内线程池（短期兜底）。

    入队时写入 user_id，供通用进度端点做任务归属校验（§6.3）。必须在**路由层
    （请求线程）**写入——Celery worker 无 request context，取不到当前用户。

    Args:
        docs_dir: 待入库文档目录（已过 `validate_docs_dir` 白名单校验）。
        user_id: 发起用户 ID（归属校验用）。

    Returns:
        任务 ID，供 /task/progress/<task_id> 订阅进度。
    """
    from config import Config

    task_id = str(uuid.uuid4())
    _save_progress(task_id, "pending", 0, 0, None, user_id)

    if Config.AI_ASYNC_ENABLED:
        try:
            from app.tasks.ai_tasks import rag_ingest_task
            rag_ingest_task.apply_async(
                kwargs={"task_id": task_id, "docs_dir": docs_dir, "user_id": user_id},
                task_id=task_id,
            )
        except Exception as e:  # noqa: BLE001
            _save_progress(task_id, "error", 0, 0, "enqueue_failed", user_id)
            logger.warning("rag.async.enqueue_failed %s", e)
        return task_id

    try:
        _get_executor().submit(_run_ingest_sync, task_id, docs_dir, user_id)
    except RuntimeError as e:
        _save_progress(task_id, "error", 0, 0, "submit_failed", user_id)
        logger.warning("rag.async.submit_failed %s", e)
    return task_id


def get_progress(task_id: str) -> Generator[str, None, None]:
    """SSE 进度生成器。

    ⚠️ P0-7：本生成器为 Flask 同步生成器，跑在 gunicorn sync worker
    （--timeout 120）上时，长任务必然触发 worker 心跳超时被强杀。
    生产部署的进度订阅已迁至 ASGI 网关（realtime_gateway/ai_task_stream.py，
    路由 /sse/ai-task/{task_id}，前端 services/ai.ts 已切换）。本实现保留为
    开发服务器 / gthread 部署的回退路径，以及 ai:admin 跨用户排障入口。
    """
    import json
    import time
    task = task_state.load(task_id)
    if task is None:
        yield f"data: {json.dumps({'type': 'error', 'message': 'task not found'}, ensure_ascii=False)}\n\n"
        return
    start_time = time.monotonic()
    timeout_seconds = 3600  # 1 小时上限
    last_heartbeat = time.monotonic()
    heartbeat_interval = 15  # M7 修复：每 15 秒发 heartbeat 防止长空闲断连
    last_state_key = None
    while True:
        task = task_state.load(task_id) or {}
        payload = {
            "type": "progress",
            "status": task.get("status"),
            "progress": task.get("progress", 0),
            "total": task.get("total", 0),
        }
        state_key = (payload["status"], payload["progress"], payload["total"])
        if state_key != last_state_key:
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            last_state_key = state_key
        if task.get("status") in ("done", "error"):
            yield f"data: {json.dumps({'type': 'done', 'result': task.get('result')}, ensure_ascii=False)}\n\n"
            task_state.delete(task_id)
            return
        if time.monotonic() - start_time > timeout_seconds:
            yield f"data: {json.dumps({'type': 'error', 'message': 'progress timeout'}, ensure_ascii=False)}\n\n"
            task_state.delete(task_id)
            return
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_interval:
            yield ": ping\n\n"
            last_heartbeat = now
        time.sleep(0.5)
