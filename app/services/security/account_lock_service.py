# -*- coding: utf-8 -*-
"""账号锁定/解锁：对象级防护（禁自锁、禁锁死最后一个可用 admin）+ 审计留痕。

锁定语义与 `status=1`（禁用）**解耦**：禁用是管理动作（走既有启停用接口），
锁定是安全处置，解锁后账号即恢复。

两条对象级防护都是"防把自己关在门外"：
- **禁自锁**：把自己锁掉会立刻失去操作入口（一期没有页面级 break-glass）；
- **禁锁死最后一个可用管理员**：判据是"持 `security:session` 且未锁定、状态正常"，
  而**不是**"用户名是 admin" —— 权限点可以挂在任意角色上。

带外通道：`flask security-unlock <username>`（页面登不进时的 break-glass）。
"""
from __future__ import annotations

from app.exceptions import RecordNotFoundError, ValidationError
from app.models.user import User
from app.persistence.user_repository import UserRepository
from app.services.audit_service import AuditService
from app.utils.logging import get_logger
from app.utils.time_utils import now_utc_naive
from extensions import db

logger = get_logger(__name__)

_SESSION_PERMISSION_CODE = "security:session"


def _unlocked_session_holder_ids() -> set:
    """持 `security:session` 且未锁定、状态正常的用户 id 集合。

    查询收进 `UserRepository`（service 层不直查 `db.session`：
    `tests/test_service_layer_session_budget.py` 的 A 类台账只减不增）。
    """
    return set(UserRepository().list_unlocked_ids_with_permission(_SESSION_PERMISSION_CODE))


def lock_account(user_id: int, reason: str, operator_id: int) -> dict:
    """锁定账号。

    Args:
        user_id: 目标用户 id。
        reason: 锁定原因（必填，落 `users.lock_reason`，截断到列宽 255）。
        operator_id: 操作人 users.id。

    Raises:
        ValidationError: 原因为空 / 自锁 / 锁死最后一个可用管理员。
        RecordNotFoundError: 目标用户不存在。
    """
    if not (reason or "").strip():
        raise ValidationError("锁定原因必填")
    if user_id == operator_id:
        raise ValidationError("不能锁定自己")
    user = db.session.get(User, user_id)
    if user is None:
        raise RecordNotFoundError("users", {"id": user_id})
    holders = _unlocked_session_holder_ids()
    if user_id in holders and len(holders) <= 1:
        raise ValidationError("不能锁定最后一个可用的管理员（否则无人能解锁）")

    user.locked_at = now_utc_naive()
    user.lock_reason = reason.strip()[:255]
    user.locked_by = operator_id
    db.session.commit()

    AuditService().log(user_id=operator_id, action="security.account.lock", resource="user",
                       resource_id=user_id, detail={"reason": user.lock_reason})
    logger.warning("账号已锁定: user_id=%s operator=%s reason=%s",
                   user_id, operator_id, user.lock_reason)
    return {"user_id": user_id, "locked": True}


def unlock_account(user_id: int, operator_id=None) -> dict:
    """解锁账号（幂等：未锁定直接返回 note=not_locked，不写审计）。

    Args:
        user_id: 目标用户 id。
        operator_id: 操作人 users.id；CLI break-glass 通道为 None（无登录态）。

    Raises:
        RecordNotFoundError: 目标用户不存在。
    """
    user = db.session.get(User, user_id)
    if user is None:
        raise RecordNotFoundError("users", {"id": user_id})
    if user.locked_at is None:
        return {"user_id": user_id, "locked": False, "note": "not_locked"}
    user.locked_at = None
    user.lock_reason = None
    user.locked_by = None
    db.session.commit()

    AuditService().log(user_id=operator_id, action="security.account.unlock", resource="user",
                       resource_id=user_id, detail={})
    return {"user_id": user_id, "locked": False}


def is_account_locked(user) -> bool:
    """账号是否处于锁定状态（登录链与业务前置检查共用的唯一判据）。

    只认 `locked_at`：`status=1`（停用）是另一条独立语义，**刻意不在这里合并** ——
    合并会让"停用账号"在日志与页面上被说成"锁定"，排障时误导。
    """
    return getattr(user, "locked_at", None) is not None
