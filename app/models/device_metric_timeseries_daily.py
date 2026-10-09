# -*- coding: utf-8 -*-
"""设备指标时序 · 天级预聚合（device_metric_timeseries_daily）

M1 分层对称化的第二层：从 `device_metric_timeseries_hourly` 降采样，
保留 730 天（2 年长期趋势）。与探测侧 `device_monitor_timeseries_daily` 同构。

由归档作业 `flask monitor-archive` 的 `downsample_to_metric_daily()` 写入，
`INSERT ... ON DUPLICATE KEY UPDATE` 幂等。

与 hourly 表**同构**（同样的 12 列语义），只有两点差异：

- 时间桶是 `day_bucket DATE` 而非 `hour_bucket DATETIME`；
- `state_changes` 是**天内的跃变次数**，由 hourly 的 `state_changes` 求和得到
  —— 注意这**不是**"按天重算相邻采样"，跨小时边界的那一次跃变在 hourly 层
  已被计入，逐层求和即可，不重复也不遗漏。

**为什么 daily 的源表是 hourly 而不是明细**：明细保留 7~14 天，早已越过
daily 要覆盖的 730 天窗口。逐层降采样是分层保留的既定形态（探测侧亦然），
且 hourly 表**有外键**（设备删除 CASCADE 回收）⇒ 孤儿行在上一层就被挡掉了，
daily 侧不需要再 JOIN devices（对应 A1 那条守卫只管"分区明细 → hourly"）。
"""
from sqlalchemy import Index, func

from extensions import db


class DeviceMetricTimeseriesDaily(db.Model):
    """指标时序天级预聚合（device_id, metric_key, index_key, day_bucket 复合主键）"""

    __tablename__ = "device_metric_timeseries_daily"
    __table_args__ = (
        Index("ix_dmts_daily_bucket", "day_bucket"),
        {"comment": "设备指标时序天级预聚合（M1 分层对称化，保留730天长期趋势）"},
    )

    device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        comment="关联设备ID",
    )
    metric_key = db.Column(
        db.String(64),
        primary_key=True,
        nullable=False,
        comment="指标 key，与明细表同名同义",
    )
    index_key = db.Column(
        db.String(128),
        primary_key=True,
        nullable=False,
        server_default="",
        comment="指标实例索引（端口号 ifIndex）；**不可省**，跨实例平均是错语义",
    )
    day_bucket = db.Column(
        db.Date,
        primary_key=True,
        nullable=False,
        comment="日期桶（UTC，由 DATE(hour_bucket) 产出）",
    )
    avg_value = db.Column(
        db.Double,
        nullable=True,
        comment="当天各小时桶 avg_value 的均值；非数值指标为 NULL",
    )
    min_value = db.Column(
        db.Double,
        nullable=True,
        comment="当天各小时桶 min_value 的最小值",
    )
    max_value = db.Column(
        db.Double,
        nullable=True,
        comment="当天各小时桶 max_value 的最大值",
    )
    sample_count = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="当天覆盖的小时桶数",
    )
    sum_sq = db.Column(
        db.Double,
        nullable=True,
        comment="当天各小时桶 sum_sq 之和（非数值指标为 NULL）",
    )
    numeric_count = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="当天各小时桶 numeric_count 之和",
    )
    last_value = db.Column(
        db.String(255),
        nullable=True,
        comment="当天最后一个小时桶的 last_value（状态词保真）",
    )
    state_changes = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="当天各小时桶 state_changes 之和（跨小时边界的那次已被 hourly 计入）",
    )
    breach_count = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="当天各小时桶 breach_count 之和",
    )
    worst_severity = db.Column(
        db.String(20),
        nullable=True,
        comment="当天最坏告警级别 ok/warn/crit",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        comment="首次聚合时间",
    )
