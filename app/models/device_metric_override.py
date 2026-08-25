# -*- coding: utf-8 -*-
"""G4.3: 设备级阈值覆盖

按 (device_id, metric_key) 覆盖 MonitorMetricTemplate 的全局默认阈值，
用于个别设备需要更严格/宽松阈值的场景（如高温机房、关键设备）。
"""
from sqlalchemy import Index, text

from app.models.base import BaseModel
from extensions import db


class DeviceMetricOverride(BaseModel):

    __tablename__ = "device_metric_override"
    __table_args__ = (
        Index(
            "uq_dmo_device_metric",
            "device_id",
            "metric_key",
            unique=True,
        ),
        Index("ix_dmo_device", "device_id"),
        {"comment": "设备级阈值覆盖（G4.3，按 device_id+metric_key 覆盖全局阈值）"},
    )

    device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="设备 ID",
    )
    metric_key = db.Column(
        db.String(64),
        nullable=False,
        comment="指标标识（对应 monitor_metric_templates.metric_key）",
    )
    threshold = db.Column(
        db.JSON,
        nullable=False,
        comment="覆盖阈值 JSON: {warn, crit, min, max, expected}",
    )
    enabled = db.Column(
        db.Boolean,
        nullable=False,
        server_default=text("1"),
        comment="是否启用",
    )
    note = db.Column(
        db.String(255),
        nullable=True,
        comment="覆盖原因/备注",
    )

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> dict:
        data = {
            "id": self.id,
            "device_id": self.device_id,
            "metric_key": self.metric_key,
            "threshold": self.threshold,
            "enabled": self.enabled,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
