# -*- coding: utf-8 -*-
"""密码类检测器：有效期过期 / 从未改密。

**LDAP 用户整体豁免本地密码策略**（`auth_source != 'local'`）：口令由目录服务管，
不落在 `password_changed_at` 上；让它们参与本地有效期判定只会产生误报。

**两条规则为什么分开**：`password_changed_at IS NULL` **不是"过期"**，是"策略启用
前从未记录"（迁移 0030 刻意不回填）。混在一起判定等于给全部存量账号判一次过期，
而一期的定位是「默认值 = 现状，升级零行为变化」—— 故 NULL 只出 low 级提示，
且**不参与任何强制点**（见设计文档 §10 R1）。

**为什么不直接 `User.query.filter(...)`**（与 WBS 示例不同，落地偏差）：本仓
`tests/test_service_layer_session_budget.py` 的 C 类台账（`Model.query` /
`cls.query`）预算为 **0** 且只减不增，新增即判红 —— Task 5 的 `policy_service`
就踩过，最终收进 `security_policy_repository` 才转绿。故两个查询都进了
`UserRepository`（ADR-002：Service 层不自行直查模型）。
"""
import datetime as dt

from app.persistence.user_repository import UserRepository
from app.services.security.policy_service import get_value
from app.services.security.scanner import Violation, register_check
from app.utils.time_utils import now_utc_naive


@register_check("user.password_expired", severity="medium", subject_type="user")
def check_password_expired() -> list:
    """本地账号密码超过 `password.max_age_days` 天未改（0 = 不过期 ⇒ 不检测）。"""
    max_age = get_value("password.max_age_days")
    if not max_age or max_age <= 0:
        return []
    deadline = now_utc_naive() - dt.timedelta(days=int(max_age))
    rows = UserRepository().list_local_password_changed_before(deadline)
    return [
        Violation(
            subject_id=user.id,
            detail={
                "username": user.username,
                "changed_at": user.password_changed_at.isoformat(),
                "max_age_days": int(max_age),
            },
        )
        for user in rows
    ]


@register_check("user.password_never_changed", severity="low", subject_type="user")
def check_password_never_changed() -> list:
    """本地账号无改密时间记录（存量语义：仅提示，不拒登）。"""
    rows = UserRepository().list_local_without_password_changed_at()
    return [Violation(subject_id=user.id, detail={"username": user.username})
            for user in rows]
