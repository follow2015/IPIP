# -*- coding: utf-8 -*-
"""P2-13: SLA/SLO 监控目标定义

定义设备/设备组的可用率 SLA 目标，基于 device_monitor_timeseries_hourly
的 reachable 聚合计算实际达成度。
"""
from sqlalchemy import BigInteger, Index, String, Text, text
from sqlalchemy.sql import func

from app.models.base import BaseModel
from extensions import db


class MonitorSlaTarget(BaseModel):
    """SLA/SLO 监控目标"""

    __tablename__ = "monitor_sla_target"
    __table_args__ = (
        Index("ix_mst_enabled", "enabled"),
        {"comment": "SLA/SLO 监控目标（P2-13，基于可达率聚合计算达成度）"},
    )

    name = db.Column(
        db.String(128),
        nullable=False,
        comment="SLA 目标名称",
    )
    target_device_ids = db.Column(
        db.JSON,
        nullable=False,
        comment="目标设备 ID 列表",
    )
    target_ratio = db.Column(
        db.Float,
        nullable=False,
        comment="可用率目标（0~1，如 0.99=99%）",
    )
    window_days = db.Column(
        db.Integer,
        nullable=False,
        server_default=text("30"),
        comment="评估窗口（天）",
    )
    description = db.Column(
        db.String(255),
        nullable=True,
        comment="SLA 描述",
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
            "target_device_ids": self.target_device_ids,
            "target_ratio": self.target_ratio,
            "window_days": self.window_days,
            "description": self.description,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
