# -*- coding: utf-8 -*-
"""安全巡检发现项模型。

一条 rule 对每个 subject 只产生一条 finding（由 `uq_rule_subject` 保证）：
巡检引擎按该键 upsert，重复命中只刷新 `last_seen`，本轮不再违规则置 `resolved`。

**`subject_id` 禁止 NULL**：MySQL/InnoDB 唯一索引中 NULL 不参与唯一性判定
（NULL ≠ NULL），可空会让系统级 finding 每轮扫描新插一行 —— 静默失效。
系统级 finding 一律使用哨兵值 `SYSTEM_SUBJECT_ID`（= 0）。
"""
from sqlalchemy.sql import func

from app.models.base import BaseModel
from extensions import db

SYSTEM_SUBJECT_ID = 0


class SecurityFinding(BaseModel):
    """安全巡检发现项。"""

    __tablename__ = "security_findings"
    __table_args__ = (
        db.UniqueConstraint("rule_id", "subject_type", "subject_id", name="uq_rule_subject"),
        db.Index("idx_finding_status_sev", "status", "severity"),
        {"comment": "安全巡检发现项"},
    )

    rule_id = db.Column(db.String(64), nullable=False, comment="规则ID，如 snmp.v2c_in_use")
    severity = db.Column(db.String(10), nullable=False, comment="critical/high/medium/low")
    subject_type = db.Column(db.String(32), nullable=False, comment="credential/user/system")
    subject_id = db.Column(
        db.BigInteger, nullable=False, server_default="0", comment="主体ID；系统级=0（禁止 NULL）"
    )
    status = db.Column(db.String(16), nullable=False, server_default="open", comment="open/resolved")
    detail = db.Column(db.JSON, nullable=True, comment="结论摘要（禁含口令/community 明文）")
    first_seen = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="首次发现")
    last_seen = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="最近一次仍违规")
    resolved_at = db.Column(db.DateTime, nullable=True, comment="消除时间")

    def __repr__(self) -> str:
        return f"<SecurityFinding {self.rule_id} {self.subject_type}:{self.subject_id} {self.status}>"
