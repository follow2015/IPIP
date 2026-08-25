# -*- coding: utf-8 -*-
"""
全局任务执行器（CR-07）

替代裸 Thread(target=..., daemon=True)，提供：
- 全局线程池限制并发数，防止恶意请求触发大量线程
- 任务 ID 返回给前端，支持查询/取消
- 统一的异常日志和 app context 管理

使用方式：
    from app.utils.concurrency.task_executor import task_executor

    task_id = task_executor.submit("scan_room", my_func, arg1, arg2)
    # task_id 可返回给前端，用于查询进度或取消
"""
from app.utils.logging import get_logger
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

logger = get_logger(__name__)

DEFAULT_TASK_TIMEOUT = 0  # 任务结果获取默认超时时间（秒，0=不等待）


class TaskInfo:
    """任务元信息"""

    def __init__(self, task_id: str, task_type: str, created_at: float):
        self.task_id = task_id
        self.task_type = task_type
        self.created_at = created_at
        self.future: Optional[Future] = None

    def to_dict(self) -> dict:
        """序列化为字典"""
        status = "running"
        if self.future:
            if self.future.done():
                try:
                    self.future.result(timeout=DEFAULT_TASK_TIMEOUT)
                    status = "completed"
                except Exception:
                    status = "failed"
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": status,
            "created_at": self.created_at,
        }


class TaskExecutor:
    """全局任务执行器

    使用 ThreadPoolExecutor 管理后台任务，限制最大并发数。
    """

    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="bg_task",
        )
        self._tasks: Dict[str, TaskInfo] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        task_type: str,
        fn: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """提交后台任务

        Args:
            task_type: 任务类型（如 scan_room / collect_info / scan_network）
            fn: 要执行的函数
            *args, **kwargs: 传递给 fn 的参数

        Returns:
            str: 任务 ID，可返回给前端用于查询/取消
        """
        task_id = f"{task_type}_{uuid.uuid4().hex[:8]}"
        info = TaskInfo(
            task_id=task_id,
            task_type=task_type,
            created_at=time.time(),
        )

        def _wrapped():
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.error("后台任务 %s 执行失败: %s", task_id, e, exc_info=True)
                try:
                    from app.services.switch_events import _redis_publish_global
                    import json as _json
                    _redis_publish_global(_json.dumps({
                        "event_type": "task_failed",
                        "payload": {
                            "task_id": task_id,
                            "task_type": task_type,
                            "error": str(e)[:200],
                        },
                        "ts": int(time.time() * 1000),
                    }, ensure_ascii=False))
                except Exception:
                    pass  # SSE 推送失败不影响异常传播
                raise

        future = self._executor.submit(_wrapped)
        info.future = future

        with self._lock:
            self._tasks[task_id] = info

        def _cleanup(f: Future):
            def _do():
                time.sleep(300)
                with self._lock:
                    self._tasks.pop(task_id, None)
            threading.Thread(target=_do, daemon=True).start()

        future.add_done_callback(_cleanup)

        logger.info("提交后台任务: task_id=%s, type=%s", task_id, task_type)
        return task_id

    def cancel(self, task_id: str) -> bool:
        """取消任务

        Args:
            task_id: 任务 ID

        Returns:
            bool: 是否成功取消（未开始的任务才能取消）
        """
        with self._lock:
            info = self._tasks.get(task_id)
        if not info or not info.future:
            return False
        return info.future.cancel()

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, task_type: Optional[str] = None) -> list[dict]:
        """列出所有任务（可选按类型过滤）"""
        with self._lock:
            tasks = list(self._tasks.values())
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]
        return [t.to_dict() for t in tasks]

    def shutdown(self, wait: bool = True):
        """关闭执行器"""
        self._executor.shutdown(wait=wait)


task_executor = TaskExecutor(max_workers=4)
