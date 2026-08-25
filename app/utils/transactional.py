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
    """用例边界事务装饰器。

    在最外层用例边界（API handler / 后台 worker 入口）统一 commit/rollback。
    Service 层内部只使用 begin_nested() 做内部部分回滚，raise 交由外层统一回滚。

    关键约束:
    - @transactional 只在用例边界使用（API handler 函数、后台 worker 任务入口）
    - Service 层方法只使用 begin_nested() + flush()，绝不调用 commit() 或 rollback()
    - 异常时 @transactional 统一 rollback()，Service 层只需 raise
    - API 层的 try/except 只负责将 BusinessError 转换为 APIResponse.error()，
      不再持有事务控制权

    重入保护:
    - 如果一个 @transactional 函数内部调用了另一个 @transactional 函数，
      内层只执行函数体，不重复 commit/rollback，也不执行回调——全部交给最外层收尾。
    - 通过 g._transactional_depth 计数器实现，非 Flask 上下文场景退化为"每次都是最外层"。

    commit 后回调:
    - 函数体内可通过 on_commit(callback) 注册回调
    - 回调在 db.session.commit() 成功后依次执行
    - 适用于缓存失效、SSE 事件推送等必须在数据持久化后执行的操作
    - 回调执行失败仅记录日志，不影响已提交的事务

    已知例外:
    - AuditService.log() 使用独立 Session(bind=db.engine) 写入并立即 commit，
      不受本装饰器管辖，也不受 transaction_checkpoint 管辖。
      这是有意设计：业务事务回滚时审计记录仍需保留（含 403 权限拒绝场景）。
      详见 app/services/audit_service.py。

    不适用场景:
    - 网络扫描等长流程（跨多 Phase、含阻塞式网络 I/O、需要"部分成功即保留"语义），
      应使用 transaction_checkpoint 代替，将事务边界下沉到 Phase/交换机/批次级别。
    """
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
    """注册 commit 后回调。

    可在 @transactional 函数体或 transaction_checkpoint 上下文内调用，
    注册的回调会在对应事务成功提交后依次执行。

    Args:
        callback: 无参可调用对象，执行失败仅记录日志

    注意:
        - 必须处于 Flask 应用上下文中（@transactional 和 transaction_checkpoint
          的调用方通常已处于 app_context 内，如 API handler 或后台 worker 入口）
        - 回调执行失败不影响已提交的事务
    """
    if has_app_context():
        if not hasattr(g, 'post_commit_callbacks'):
            g.post_commit_callbacks = []
        g.post_commit_callbacks.append(callback)
    else:
        logger.warning("on_commit 在无应用上下文时调用，回调将被丢弃: %s", callback)


def _run_post_commit_callbacks():
    """执行 commit 后回调列表，失败仅记录日志。"""
    if not has_app_context() or not hasattr(g, 'post_commit_callbacks'):
        return
    callbacks = g.post_commit_callbacks
    g.post_commit_callbacks = []  # 清空防止重复执行
    for cb in callbacks:
        try:
            cb()
        except Exception:
            logger.warning("post_commit 回调执行失败", exc_info=True)


@contextmanager
def transaction_checkpoint(db_session, checkpoint_name: str = ""):
    """长流程专用事务检查点。

    在一个逻辑单元（一台交换机 / 一个网段批次 / 一个 Phase）结束时提交，
    异常时只回滚这个单元，不影响此前已提交的单元。

    与 @transactional 的区别:
    - @transactional 包裹整个函数，适用于短事务（API handler）
    - transaction_checkpoint 在循环内部使用，适用于长流程（网络扫描流水线）

    ⚠️ 互斥约束（双向）:
    - transaction_checkpoint 禁止嵌套在 @transactional 内部使用（检测到会抛 RuntimeError）。
    - @transactional 同样禁止嵌套在 transaction_checkpoint 内部使用（检测到会抛 RuntimeError）。
    - 两者共用 g._transactional_depth 计数器实现双向互斥：
      checkpoint 进入时递增、退出时递减，@transactional 检测到 depth > 0 时
      视为非 outermost，不会提前 commit。

    与 begin_nested() 的关系:
    - begin_nested() 保护阶段内部的原子性（子事务）
    - transaction_checkpoint 控制提交粒度（何时持久化并释放锁）
    - 两者互补，可以嵌套使用

    commit 后回调:
    - 检查点内可通过 on_commit(callback) 注册回调
    - 回调在 db_session.commit() 成功后依次执行
    - 每次检查点只执行并清空本次检查点期间注册的回调

    用法:
        for switch in switches:
            with transaction_checkpoint(db_session, f"phase0:{switch.id}"):
                with db_session.begin_nested():
                    port_repo.incremental_update(switch.id, port_rows)
                on_commit(lambda: emit_resource_change(switch.id, "port_sync"))

    Args:
        db_session: SQLAlchemy Session 实例
        checkpoint_name: 检查点名称，用于日志标识
    """
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
    """执行本次检查点期间注册的回调，保留 pre_count 之前的回调给外层。

    Args:
        pre_count: 进入检查点时的回调队列长度
    """
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
    """回滚时丢弃本次检查点期间注册的回调。

    Args:
        pre_count: 进入检查点时的回调队列长度
    """
    if not has_app_context() or not hasattr(g, 'post_commit_callbacks'):
        return
    g.post_commit_callbacks = g.post_commit_callbacks[:pre_count]
