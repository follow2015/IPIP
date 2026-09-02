# -*- coding: utf-8 -*-
"""被依赖抑制告警留痕（事件聚合 Task 0）

背景：上游设备故障时，下游设备的同类型告警会被 AlertDependencyService 抑制，
**不入 outbox**。outbox 是发件箱，语义是「待投递的告警」，把这些记录塞进去
会污染前端告警列表（表现为告警数量不降反增）。

但这些被抑制的告警正是「这起事故影响了多少台设备」的唯一数据来源 ——
一次核心交换机宕机波及 30 台下游，若不留痕，事件里只会剩孤零零 1 条根因告警，
影响面完全丢失。而「影响面」恰是事件中心相对告警列表的核心增值。

故独立建表存放，只用于统计，不参与投递、不出现在告警列表。
"""
from sqlalchemy import BigInteger, DateTime, Index, String, text

from app.models.base import BaseModel
from extensions import db


class MonitorSuppressedAlertLog(BaseModel):
    """被依赖抑制而未入箱的告警留痕"""

    __tablename__ = "monitor_suppressed_alert_log"
    __table_args__ = (
        Index("ix_msal_incident", "incident_id"),
        Index("ix_msal_upstream", "upstream_device_id"),
        Index("ix_msal_created_at", "created_at"),
        {"comment": "被依赖抑制告警留痕（事件影响面统计，不参与投递）"},
    )

    device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        comment="被抑制告警的设备ID（设备删除后置空，留痕行保留）",
    )
    alert_type = db.Column(
        db.String(40),
        nullable=False,
        comment="告警类型（device_unreachable / cpu_high 等）",
    )
    severity = db.Column(
        db.String(20),
        nullable=False,
        comment="info / warning / critical",
    )
    reason_code = db.Column(
        db.String(40),
        nullable=False,
        comment="抑制来源编码：L2_manual_rule / L2_topology",
    )
    upstream_device_id = db.Column(
        db.BigInteger,
        nullable=True,
        comment="命中的上游设备ID（根因侧，用于归属事件）",
    )
    incident_id = db.Column(
        db.BigInteger,
        nullable=True,
        comment="归属事件ID（L2 聚合后回填；NULL 表示尚未归属）",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="留痕时间",
    )

    def to_dict(self, exclude: list = None) -> dict:
        """序列化"""
        data = {
            "id": self.id,
            "device_id": self.device_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "reason_code": self.reason_code,
            "upstream_device_id": self.upstream_device_id,
            "incident_id": self.incident_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
