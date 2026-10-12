# -*- coding: utf-8 -*-
"""审计留存检测器：审计日志是否留够 `audit.retention_days` 天。

**判定方向**（容易写反，故写在这里）：留存要求是"日志至少保留 N 天"，所以
**最早记录早于 `now - N` = 覆盖足够 = 不报**；最早记录比它还新 ⇒ 历史没留住 ⇒ 报。
（WBS 示例的 `test_no_finding_when_retention_covered` 与它自己的实现矛盾 ——
用一条当前记录断言"覆盖"，按实现那恰恰是"不足"；已按实现语义改写。）

**系统级 finding 用哨兵 `subject_id=0`**：MySQL/InnoDB 的唯一索引里
`NULL != NULL`、**不参与唯一性判定**。若系统级 rule 存 NULL，每轮扫描都会插进
新的一行 ⇒ findings 表随扫描轮数无界增长、概览的"X/Y 项"计数失真。
哨兵 0 让 `(rule_id, subject_type, subject_id)` 唯一键对系统级也成立
（第二批评审 P1 的阻断项）。

**清理不归安全中心**：`audit.retention_days` 只是**检查参数**（默认 180，
`min=30`，没有"设 0 关闭"这一档 —— 留存不足是合规项，不该被悄悄关掉）。
日志清理由独立运维任务负责；补齐后本项在下轮扫描自然转 resolved。
"""
import datetime as dt

from app.persistence.audit_log_repository import AuditLogRepository
from app.services.security.policy_service import get_value
from app.services.security.scanner import SYSTEM_SUBJECT_ID, Violation, register_check
from app.utils.time_utils import now_utc_naive


@register_check("system.audit_retention", severity="medium", subject_type="system")
def check_audit_retention() -> list:
    """最早审计记录晚于 `now - retention_days` ⇒ 留存不足，报**一条**系统级 finding。"""
    days = get_value("audit.retention_days") or 180
    deadline = now_utc_naive() - dt.timedelta(days=int(days))
    oldest = AuditLogRepository().oldest_created_at()
    if oldest is None or oldest <= deadline:
        return []
    return [
        Violation(
            subject_id=SYSTEM_SUBJECT_ID,  # 哨兵 0，绝不能是 NULL
            detail={"oldest_audit_at": oldest.isoformat(), "required_days": int(days)},
        )
    ]
