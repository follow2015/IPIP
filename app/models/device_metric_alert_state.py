# -*- coding: utf-8 -*-
"""设备指标告警状态表（device_metric_alert_state）

按「设备 + 指标 + 索引」维度维护指标告警的当前态（是否处于告警中），
供 MetricAlertService 决定「入箱告警」还是「入箱恢复通知」，实现指标告警去重：

- breached=True 且此前非告警态 → 入箱告警，并记录告警态；
- breached=False 且此前为告警态 → 入箱恢复通知，清除告警态；
- 状态不变（持续告警 / 持续正常）→ 不重复入箱。

以此支撑「按指标维度独立告警/恢复」，与设备可达性状态机（单设备单快照）解耦。
"""
from sqlalchemy import Index, UniqueConstraint

from app.models.base import BaseModel, BIGINT_UNSIGNED
from extensions import db


class DeviceMetricAlertState(BaseModel):
    """设备指标告警状态（按 device_id + metric_key + index 维度）"""

    __tablename__ = "device_metric_alert_state"

    id = db.Column(BIGINT_UNSIGNED(), primary_key=True, autoincrement=True, comment="主键ID")
    __table_args__ = (
        UniqueConstraint(
            "device_id", "metric_key", "index_key",
            name="uq_dmas_device_metric_index",
        ),
        Index("ix_dmas_metric_key", "metric_key"),
        {"comment": "设备指标告警状态（按指标维度去重与恢复）"},
    )

    device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="设备ID",
    )
    metric_key = db.Column(
        db.String(64),
        nullable=False,
        comment="指标标识，如 temperature / disk_failure / port_updown / raid_failure",
    )
    index_key = db.Column(
        db.String(64),
        nullable=False,
        default="",
        comment="指标实例索引（端口号 / 传感器名），非索引指标为空串",
    )
    alert_type = db.Column(
        db.String(40),
        nullable=False,
        comment="告警类型（NotificationTypeCode），如 temperature_alert",
    )
    breached = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        comment="当前是否处于告警态",
    )
    severity = db.Column(
        db.String(20),
        nullable=True,
        comment="最近一次告警层级 crit / warn / ok",
    )
    last_value = db.Column(
        db.String(255),
        nullable=True,
        comment="最近一次指标值（快照，供告警/恢复文案）",
    )
