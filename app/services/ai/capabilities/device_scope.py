# -*- coding: utf-8 -*-
"""A9 修复：capability 层的设备数据域校验。


路由直参路径的 C2 校验（`app/api/ai/ai_routes._check_device_access`）只覆盖
「用户直接在 URL/body 里给 device_id」的场景。**agentic 与技能引擎路径下，
device_id 是 LLM 决策出来的**：持 `ai:agentic` 的用户可让 `ssh.diagnostic_show`
或 `devices.get_by_id` 触达数据域外的任意设备——C2 完全不在调用链上。


capability 的函数签名统一是 `fn(args)`，没有 user_id 形参（改签名要动全部
能力与技能 YAML）。故身份经 **contextvar** 传递：`WorkflowEngine.run` 在执行
技能前后 bind/reset，capability 内通过 `_resolve_user_id()` 读取。

选 contextvar 而非线程局部/全局：Celery worker 内每个任务在同一线程执行，
而 gunicorn 可能用协程，contextvar 在两种模型下都正确绑定且不跨请求泄漏。


- `False`（默认）：data_scope 服务故障时放行，适用只读查询；
- `True`：服务故障时拒绝，适用向真实设备下发命令的设备操作类能力——
  鉴权服务不可用不能成为绕过数据域的通道。
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

_current_user_var: ContextVar[Optional[int]] = ContextVar(
    "ai_capability_user", default=None
)


def bind_user(user_id: Optional[int]):
    """把当前用户绑定到 contextvar，返回 reset 用的 token。"""
    return _current_user_var.set(user_id)


def reset_user(token) -> None:
    """还原 contextvar 到 bind_user 之前的值。"""
    _current_user_var.reset(token)


@contextmanager
def bound_user(user_id: Optional[int]) -> Iterator[None]:
    """在上下文中绑定当前用户（异常路径亦保证还原）。"""
    token = bind_user(user_id)
    try:
        yield
    finally:
        reset_user(token)


def _resolve_user_id() -> Optional[int]:
    """读取当前绑定的用户 id（未绑定返回 None）。"""
    return _current_user_var.get()


def check_device_access(device_id: int, *, fail_closed: bool = False) -> "tuple[bool, str]":
    """校验当前用户是否有权访问指定设备（语义与 C2 helper 对齐）。

    Args:
        device_id: 目标设备 ID。
        fail_closed: data_scope 服务故障时的降级语义。
            False（默认）= 放行，适用只读查询；
            True = 拒绝，适用设备操作类能力（会触达真实设备）。

    Returns:
        (True, "") 有权限；(False, reason) 无权限/服务故障拒绝。
    """
    user_id = _resolve_user_id()
    if not user_id:
        return False, "无法识别当前用户"
    try:
        from app.services.monitoring.data_scope_service import get_visible_device_ids
        visible = get_visible_device_ids(user_id)
        if visible is None:
            return True, ""  # data_scope=all 或超管
        if device_id in visible:
            return True, ""
        return False, f"无权访问设备 {device_id}（数据域隔离）"
    except Exception:  # noqa: BLE001
        logger.warning(
            "ai.capability.device_scope_check_failed user=%s device=%s fail_closed=%s",
            user_id, device_id, fail_closed,
        )
        if fail_closed:
            return False, "设备权限服务暂不可用，已拒绝该操作"
        return True, ""
