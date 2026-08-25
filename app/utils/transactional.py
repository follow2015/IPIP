# -*- coding: utf-8 -*-
"""用例边界事务装饰器 + 长流程检查点

在最外层用例边界（API handler / 后台 worker 入口）统一 commit/rollback。
Service 层内部只做 savepoint + flush，绝不 commit。

使用方式:
    @transactional
    def create_device():
        # API handler 逻辑
        ...

    # 长流程（如网络扫描）内部，按阶段/单元提交：
    with transaction_checkpoint(db_session, "phase0:switch_42"):
        info_service.collect_port_info(42)

    # commit 后回调（缓存失效、SSE 事件等）：
    on_commit(lambda: emit_event("room", "create", ids=[room.id]))
"""
from contextlib import contextmanager
from functools import wraps

from flask import g, has_app_context

from extensions import db
from app.utils.logging import get_logger

logger = get_logger(__name__)


def transactional(fn):
    @wraps(fn)
    def wrap(*args, **kwargs):
        ctx_available = has_app_context()

        if ctx_available and not hasattr(g, 'post_commit_callbacks'):
            g.post_commit_callbacks = []

        is_outermost = not (ctx_available and getattr(g, '_transactional_depth', 0) > 0)
        if ctx_available:
            g._transactional_depth = getattr(g, '_transactional_depth', 0) + 1

        try:
            result = fn(*args, **kwargs)
            if is_outermost:
                db.session.commit()
                _run_post_commit_callbacks()
            return result
        except Exception:
            if is_outermost:
                db.session.rollback()
            raise
        finally:
            if ctx_available:
                g._transactional_depth -= 1

    return wrap


def on_commit(callback):
    if has_app_context():
        if not hasattr(g, 'post_commit_callbacks'):
            g.post_commit_callbacks = []
        g.post_commit_callbacks.append(callback)
    else:
        logger.warning("on_commit 在无应用上下文时调用，回调将被丢弃: %s", callback)


def _run_post_commit_callbacks():
    if not has_app_context() or not hasattr(g, 'post_commit_callbacks'):
        return
    callbacks = g.post_commit_callbacks
    g.post_commit_callbacks = []
    for cb in callbacks:
        try:
            cb()
        except Exception:
            logger.warning("post_commit 回调执行失败", exc_info=True)


@contextmanager
def transaction_checkpoint(db_session, checkpoint_name: str = ""):
    if has_app_context() and getattr(g, '_transactional_depth', 0) > 0:
        raise RuntimeError(
            f"transaction_checkpoint('{checkpoint_name}') 禁止在 @transactional 内部使用。"
            f"真实 commit() 会破坏外层事务的原子性。"
            f"请将长流程逻辑移到 @transactional 之外，或改用 begin_nested()。"
        )

    ctx_available = has_app_context()
    if ctx_available:
        g._transactional_depth = getattr(g, '_transactional_depth', 0) + 1

    pre_count = 0
    if ctx_available and hasattr(g, 'post_commit_callbacks'):
        pre_count = len(g.post_commit_callbacks)

    try:
        yield
        db_session.commit()
        _run_checkpoint_callbacks(pre_count)
    except Exception:
        db_session.rollback()
        logger.warning("扫描检查点回滚: %s", checkpoint_name, exc_info=True)
        _discard_checkpoint_callbacks(pre_count)
        raise
    finally:
        if ctx_available:
            g._transactional_depth -= 1


def _run_checkpoint_callbacks(pre_count: int):
    if not has_app_context() or not hasattr(g, 'post_commit_callbacks'):
        return
    callbacks = g.post_commit_callbacks
    own_callbacks = callbacks[pre_count:]
    g.post_commit_callbacks = callbacks[:pre_count]
    for cb in own_callbacks:
        try:
            cb()
        except Exception:
            logger.warning("checkpoint post_commit 回调执行失败", exc_info=True)


def _discard_checkpoint_callbacks(pre_count: int):
    if not has_app_context() or not hasattr(g, 'post_commit_callbacks'):
        return
    g.post_commit_callbacks = g.post_commit_callbacks[:pre_count]
