# -*- coding: utf-8 -*-
"""P2-11: 多级升级链步骤

一个 EscalationPolicy 可挂多个 step，按 step_no 顺序执行：
- step 1: wait=30min → 通知 L2 角色
- step 2: wait=60min → 升级 critical + 通知经理
- step 3: wait=120min → 触发 webhook

向后兼容：policy 无 step 时回退到 wait_minutes/escalate_severity 单级模式。
"""
from sqlalchemy import Index, text

from app.models.base import BaseModel
from extensions import db


class MonitorEscalationStep(BaseModel):
    """监控告警升级链步骤（P2-11）"""

    __tablename__ = "monitor_escalation_step"
    __table_args__ = (
        Index("ix_mes_policy", "policy_id"),
        Index("ix_mes_policy_step", "policy_id", "step_no", unique=True),
        {"comment": "监控告警升级链步骤（P2-11，多级升级）"},
    )

    policy_id = db.Column(
        db.Integer,
        db.ForeignKey("monitor_escalation_policy.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属升级策略 ID",
    )
    step_no = db.Column(
        db.Integer,
        nullable=False,
        server_default=text("1"),
        comment="步骤序号（从 1 开始，按序执行）",
    )
    wait_minutes = db.Column(
        db.Integer,
        nullable=False,
        comment="距告警产生后多少分钟触发本步骤",
    )
    escalate_severity = db.Column(
        db.String(16),
        nullable=True,
        comment="本步骤升级到的严重级别（null=不升级级别）",
    )
    escalate_to_role_id = db.Column(
        db.BigInteger,
        db.ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
        comment="本步骤通知的角色 ID",
    )
    escalate_webhook_url = db.Column(
        db.String(512),
        nullable=True,
        comment="本步骤触发的 webhook URL（可选）",
    )
    enabled = db.Column(
        db.Boolean,
        nullable=False,
        server_default=text("1"),
        comment="是否启用本步骤",
    )

    def to_dict(self, exclude: list = None) -> dict:
        data = {
            "id": self.id,
            "policy_id": self.policy_id,
            "step_no": self.step_no,
            "wait_minutes": self.wait_minutes,
            "escalate_severity": self.escalate_severity,
            "escalate_to_role_id": self.escalate_to_role_id,
            "escalate_webhook_url": self.escalate_webhook_url,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
