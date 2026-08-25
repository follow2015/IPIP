# -*- coding: utf-8 -*-
"""G4.2: 监控告警升级策略

告警在 N 分钟未确认（acknowledged_at IS NULL）时升级：
- 提升严重级别（warning → critical）
- 通知更高级别用户组（escalate_to_role_id）
- 可选触发外部 webhook（escalate_webhook_url）

由 outbox_sender 周期扫描未确认告警 + 到期升级。
"""
from sqlalchemy import Index, text

from app.models.base import BaseModel
from extensions import db


class MonitorEscalationPolicy(BaseModel):
    """监控告警升级策略"""

    __tablename__ = "monitor_escalation_policy"
    __table_args__ = (
        Index("ix_mep_enabled", "enabled"),
        Index("ix_mep_alert_type", "alert_type"),
        {"comment": "监控告警升级策略（G4.2，未确认告警到期升级）"},
    )

    name = db.Column(
        db.String(128),
        nullable=False,
        comment="策略名称",
    )
    alert_type = db.Column(
        db.String(64),
        nullable=True,
        comment="匹配告警类型（null=全部）",
    )
    severity = db.Column(
        db.String(16),
        nullable=True,
        comment="匹配告警级别（null=全部）",
    )
    wait_minutes = db.Column(
        db.Integer,
        nullable=False,
        comment="未确认等待分钟数，超过即升级",
    )
    escalate_severity = db.Column(
        db.String(16),
        nullable=True,
        comment="升级后严重级别（如 critical），null=不升级级别",
    )
    escalate_to_role_id = db.Column(
        db.BigInteger,
        db.ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
        comment="升级后通知的角色 ID",
    )
    escalate_webhook_url = db.Column(
        db.String(512),
        nullable=True,
        comment="升级触发的 webhook URL（可选）",
    )
    repeat_minutes = db.Column(
        db.Integer,
        nullable=False,
        server_default=text("0"),
        comment="重复升级间隔分钟（0=只升一次）",
    )
    enabled = db.Column(
        db.Boolean,
        nullable=False,
        server_default=text("1"),
        comment="是否启用",
    )

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "wait_minutes": self.wait_minutes,
            "escalate_severity": self.escalate_severity,
            "escalate_to_role_id": self.escalate_to_role_id,
            "escalate_webhook_url": self.escalate_webhook_url,
            "repeat_minutes": self.repeat_minutes,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
