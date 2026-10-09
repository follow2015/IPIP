# -*- coding: utf-8 -*-
"""trace_id：把一次用户操作在 Web / Celery / SSE 三处的日志串起来

Flask 早就有 request_id（每请求一个 uuid，写进 X-Request-ID 响应头），但它
**不出进程**：`apply_async` 只传业务参数，worker 侧日志与 Web 侧日志没有任何共同
字段。用户报"任务卡住了"，只能靠时间戳 + user_id 在两份日志里人工对齐。

本模块把 request_id 提升为 trace_id（同一个值，不新增第二套 ID）：

  - Web 侧：`before_request` 里 trace_id = 上游 `X-Trace-ID`（若有）or request_id
  - 入队：`apply_async(headers={"trace_id": …})`，worker 侧取回
  - worker 侧：`bind_trace_id()` 写进 contextvar，该 task 内日志自动带上
  - SSE 侧：trace_id 随 task_state 下发，前端拿到的进度帧能对应到后端日志

用 contextvar 而不是模块级全局变量：Celery worker 在进程内并发跑多个 task，
全局变量会把 A 任务的 trace_id 贴到 B 任务的日志上 —— 那比没有更糟，因为它
会让人以为串起来了。
"""
from contextvars import ContextVar
from typing import Optional

from flask import g, has_request_context

TRACE_HEADER = "X-Trace-ID"
CELERY_TRACE_HEADER = "trace_id"

_trace_id_var: ContextVar[Optional[str]] = ContextVar("ipip_trace_id", default=None)


def bind_trace_id(trace_id: Optional[str]) -> Optional[str]:
    """把 trace_id 绑到当前上下文（Celery task 入口用），返回实际绑定的值。"""
    value = trace_id or None
    _trace_id_var.set(value)
    return value


def current_trace_id() -> Optional[str]:
    """取当前 trace_id：Flask 请求上下文优先，其次 Celery / 手动绑定。"""
    if has_request_context():
        value = getattr(g, "trace_id", None)
        if value:
            return value
    return _trace_id_var.get()


def trace_id_from_celery_headers(headers) -> Optional[str]:
    """从 Celery 的 `self.request.headers` 里取 trace_id。

    eager 模式（`task_always_eager`）下 headers 可能为 None / 非 dict，
    一律按"没带"处理 —— 缺 trace_id 只是少一个关联字段，不该让任务失败。
    """
    if not isinstance(headers, dict):
        return None
    return headers.get(CELERY_TRACE_HEADER) or None


def bind_trace_id_from_task(task) -> Optional[str]:
    """Celery task 入口：取 headers 里的 trace_id 并绑定，返回其值。"""
    headers = getattr(getattr(task, "request", None), "headers", None)
    return bind_trace_id(trace_id_from_celery_headers(headers))
