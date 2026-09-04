# -*- coding: utf-8 -*-
"""G4.1: 监控告警静默规则

在指定时间窗口内对匹配的设备/告警类型静默（不入箱、不推送），
用于计划内维护、已知问题处理等场景避免告警噪声。
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, text

from app.models.base import BaseModel, BIGINT_UNSIGNED
from extensions import db


class MonitorSilenceRule(BaseModel):
    """监控告警静默规则"""

    __tablename__ = "monitor_silence_rule"

    id = db.Column(BIGINT_UNSIGNED(), primary_key=True, autoincrement=True, comment="主键ID")
    __table_args__ = (
        Index("ix_msr_enabled", "enabled"),
        Index("ix_msr_silence_until", "silence_until"),
        {"comment": "监控告警静默规则（G4.1，时间窗口内匹配告警不入箱）"},
    )

    name = db.Column(
        db.String(128),
        nullable=False,
        comment="规则名称",
    )
    device_ids = db.Column(
        db.JSON,
        nullable=True,
        comment="静默设备 ID 列表（null=全部设备）",
    )
    alert_types = db.Column(
        db.JSON,
        nullable=True,
        comment="静默告警类型列表（null=全部类型）",
    )
    silence_from = db.Column(
        db.DateTime,
        nullable=False,
        comment="静默开始时间",
    )
    silence_until = db.Column(
        db.DateTime,
        nullable=False,
        comment="静默结束时间",
    )
    reason = db.Column(
        db.String(255),
        nullable=True,
        comment="静默原因",
    )
    created_by = db.Column(
        db.String(64),
        nullable=True,
        comment="创建人用户名",
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
            "device_ids": self.device_ids,
            "alert_types": self.alert_types,
            "silence_from": self.silence_from.isoformat() if self.silence_from else None,
            "silence_until": self.silence_until.isoformat() if self.silence_until else None,
            "reason": self.reason,
            "created_by": self.created_by,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
