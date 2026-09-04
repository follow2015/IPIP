# -*- coding: utf-8 -*-
"""监控时序小时级预聚合表（device_monitor_timeseries_hourly）

由归档作业 ``flask monitor-archive`` 从 ``device_monitor_probe_events`` 降采样
写入（INSERT ... ON DUPLICATE KEY UPDATE 幂等），保留 90 天。趋势 API 查询
超出事件分区表保留窗口（>90 天）的数据时直接读此表，避免对原始表做运行时
GROUP BY。

metric 取值：
- ``reachable``：该小时可达占比（0~1），其 avg/min/max 相同
- ``latency_ms``：该小时 latency_ms 的 avg/min/max（仅可达且有值样本计入）
"""
from sqlalchemy import Double, func

from extensions import db


class DeviceMonitorTimeseriesHourly(db.Model):
    """监控时序小时级预聚合（device_id, metric, hour_bucket 复合主键）"""

    __tablename__ = "device_monitor_timeseries_hourly"
    __table_args__ = (
        {
            "comment": "监控时序小时级预聚合，事件分区表保留窗口外只保留此表，保留90天",
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
    hour_bucket = db.Column(
        db.DateTime,
        primary_key=True,
        nullable=False,
        comment="整点时间，如 2026-07-31 10:00:00",
    )
    avg_value = db.Column(
        Double,
        nullable=False,
        comment="均值",
    )
    min_value = db.Column(
        Double,
        nullable=False,
        comment="最小值",
    )
    max_value = db.Column(
        Double,
        nullable=False,
        comment="最大值",
    )
    sample_count = db.Column(
        db.Integer,
        nullable=False,
        comment="采样点数",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        comment="首次聚合时间",
    )
