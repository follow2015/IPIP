# -*- coding: utf-8 -*-
"""监控事件（incident）

把散落的告警归并为可运营的「事件」，按三级策略聚合：
- L1_rule：同设备 + 同告警类型 + 时间窗内
- L2_topology / L2_manual_rule：依赖关联（下游被抑制告警归入上游事件）
- L3_change：与近期配置变更关联

一条告警属于至多一个事件（outbox.incident_id）；被依赖抑制而未入箱的告警
记在 monitor_suppressed_alert_log，聚合后回填 incident_id 以统计影响面。
"""
from sqlalchemy import BigInteger, DateTime, Index, Integer, String, text

from app.models.base import BaseModel
from extensions import db


class MonitorIncident(BaseModel):
    """监控事件（告警聚合后的运营单元）"""

    __tablename__ = "monitor_incident"
    __table_args__ = (
        Index("ix_incident_key", "incident_key"),
        Index("ix_incident_status", "status"),
        Index("ix_incident_last_alert", "last_alert_at"),
        {"comment": "监控事件（告警聚合后的运营单元）"},
    )

    incident_key = db.Column(
        db.String(191),
        nullable=False,
        comment="归并键，如 device_unreachable:200（比 dedup_key 粗，不含 metric_key/index/action）",
    )
    title = db.Column(
        db.String(255),
        nullable=False,
        comment="事件标题",
    )
    severity = db.Column(
        db.String(20),
        nullable=False,
        comment="info / warning / critical（取事件内最高级别）",
    )
    status = db.Column(
        db.String(16),
        nullable=False,
        server_default="active",
        comment="active / acknowledged / closed",
    )
    reason_code = db.Column(
        db.String(40),
        nullable=True,
        comment="归并原因：L1_rule / L2_topology / L2_manual_rule / L3_change",
    )
    root_device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        comment="根因设备ID（设备删除后置空）",
    )
    alert_count = db.Column(
        db.Integer,
        nullable=False,
        server_default="1",
        comment="累计告警数（入箱的）",
    )
    device_count = db.Column(
        db.Integer,
        nullable=False,
        server_default="1",
        comment="影响设备数（入箱设备 ∪ 被抑制留痕设备，去重）",
    )
    first_alert_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="首条告警时间",
    )
    last_alert_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="末条告警时间（L1 时间窗判定基准）",
    )
    closed_at = db.Column(
        db.DateTime,
        nullable=True,
        comment="关闭时间",
    )

    def to_dict(self, exclude: list = None) -> dict:
        """序列化"""
        data = {
            "id": self.id,
            "incident_key": self.incident_key,
            "title": self.title,
            "severity": self.severity,
            "status": self.status,
            "reason_code": self.reason_code,
            "root_device_id": self.root_device_id,
            "alert_count": self.alert_count,
            "device_count": self.device_count,
            "first_alert_at": self.first_alert_at.isoformat() if self.first_alert_at else None,
            "last_alert_at": self.last_alert_at.isoformat() if self.last_alert_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
