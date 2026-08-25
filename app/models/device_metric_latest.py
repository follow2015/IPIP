# -*- coding: utf-8 -*-
"""设备指标当前值表（device_metric_latest）

每次采集后 upsert，存储指标最近一次采集值（含正常值），供前端「监控数据」页
展示所有采集到的指标当前值（不只告警）。

与 device_metric_alert_state 区别：
- alert_state：只存告警态（breached=True 时才写），用于告警去重/恢复；
- latest：存所有采集到的指标当前值（含正常），用于展示。

唯一约束：(device_id, metric_key, index_key) 唯一，每次采集 upsert。
"""
from sqlalchemy import Index, UniqueConstraint

from app.models.base import BaseModel
from extensions import db


class DeviceMetricLatest(BaseModel):
    """设备指标当前值（按 device_id + metric_key + index_key 维度）"""

    __tablename__ = "device_metric_latest"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "metric_key", "index_key",
            name="uq_dml_device_metric_index",
        ),
        Index("ix_dml_device_id", "device_id"),
        Index("ix_dml_metric_key", "metric_key"),
        {"comment": "设备指标当前值（每次采集 upsert，含正常值）"},
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
        comment="指标标识，如 cpu_usage / temperature / zabbix_cpu_usage",
    )
    index_key = db.Column(
        db.String(128),
        nullable=False,
        default="",
        comment="指标实例索引（端口号 / 传感器名 / CPU slot 名），非索引指标为空串",
    )
    value = db.Column(
        db.String(255),
        nullable=True,
        comment="最近一次指标值（字符串快照，前端按 metric_type 解析展示）",
    )
    severity = db.Column(
        db.String(20),
        nullable=True,
        comment="最近一次告警层级 crit / warn / ok（未超阈值为 ok）",
    )
    breached = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        comment="最近一次是否超阈值",
    )
    collected_at = db.Column(
        db.DateTime,
        nullable=False,
        comment="最近一次采集时间",
    )
