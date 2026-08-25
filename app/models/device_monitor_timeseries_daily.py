# -*- coding: utf-8 -*-
"""监控时序天级预聚合表（device_monitor_timeseries_daily）

由归档作业 ``flask monitor-archive`` 从 ``device_monitor_timeseries_hourly`` 降采样
写入（INSERT ... ON DUPLICATE KEY UPDATE 幂等），保留 730 天（2 年长期趋势）。

架构3 分层保留策略：
- events (30s 明细): 7 天（降采样后清理）
- hourly (1h): 90 天
- daily  (1d): 730 天

metric 取值与 hourly 一致：reachable / latency_ms。
"""
from sqlalchemy import func

from extensions import db


class DeviceMonitorTimeseriesDaily(db.Model):
    """监控时序天级预聚合（device_id, metric, day_bucket 复合主键）"""

    __tablename__ = "device_monitor_timeseries_daily"
    __table_args__ = (
        {
            "comment": "监控时序天级预聚合，从 hourly 降采样，保留730天（架构3 长期趋势层）",
        },
    )

    device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        comment="关联设备ID",
    )
    metric = db.Column(
        db.String(32),
        primary_key=True,
        nullable=False,
        comment="reachable / latency_ms",
    )
    day_bucket = db.Column(
        db.Date,
        primary_key=True,
        nullable=False,
        comment="日期，如 2026-07-31",
    )
    avg_value = db.Column(
        db.Float,
        nullable=False,
        comment="均值",
    )
    min_value = db.Column(
        db.Float,
        nullable=False,
        comment="最小值",
    )
    max_value = db.Column(
        db.Float,
        nullable=False,
        comment="最大值",
    )
    sample_count = db.Column(
        db.Integer,
        nullable=False,
        comment="采样点数（小时桶数）",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        comment="首次聚合时间",
    )
