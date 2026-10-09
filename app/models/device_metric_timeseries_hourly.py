# -*- coding: utf-8 -*-
"""设备指标时序 · 小时级预聚合（device_metric_timeseries_hourly）

M1 分层对称化的产物：把 `device_metric_timeseries`（明细）按小时聚合，
保留 90 天。与探测侧的 `device_monitor_timeseries_hourly` 同构，
让"指标侧 98.5% 的存量却没有预聚合层"的不对称成为历史
（明细 22,330,077 行 / 3,744 MB，对探测明细是 68:1）。

由归档作业 `flask monitor-archive` 的 `downsample_to_metric_hourly()` 写入，
`INSERT ... ON DUPLICATE KEY UPDATE` 幂等。

与探测侧 hourly 的四点**刻意**差异（照抄会错）
----------------------------------------------
1. **聚合键必须含 `index_key`**：指标是"每设备每指标**每实例**"一行
   （端口号 ifIndex）。丢掉 index_key 会把 48 个端口的温度平均成一个数 ——
   跨实例平均是**错语义**，不是精度损失。

2. **`state_changes` + `last_value`**：端口状态这类非数值指标，
   `value_num` 是 NULL，AVG/MIN/MAX 全为空。若只看聚合值，
   "一小时内 up→down→up" 降采样后会**静默消失**（只剩一个 up）。
   `state_changes` 记跃变次数、`last_value` 记桶内最后一个原始值，
   让抖动在降采样后仍可被检出。

3. **`min/max/avg` 允许 NULL**：非数值指标整桶 `value_num` 都是 NULL，
   列若为 NOT NULL 就写不进去。

4. **`breach_count` / `worst_severity`**：明细保留期缩短后，
   "这段时间是否告警过"只能靠聚合层回答，故必须落桶内告警计数与最坏级别。
"""
from sqlalchemy import Index, func

from extensions import db


class DeviceMetricTimeseriesHourly(db.Model):
    """指标时序小时级预聚合（device_id, metric_key, index_key, hour_bucket 复合主键）"""

    __tablename__ = "device_metric_timeseries_hourly"
    __table_args__ = (
        Index("ix_dmts_hourly_bucket", "hour_bucket"),
        {"comment": "设备指标时序小时级预聚合（M1 分层对称化，保留90天）"},
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
        comment="指标 key，与明细表同名同义（如 cpu_usage / if_status）",
    )
    index_key = db.Column(
        db.String(128),
        primary_key=True,
        nullable=False,
        server_default="",
        comment="指标实例索引（端口号 ifIndex）；**不可省**，跨实例平均是错语义",
    )
    hour_bucket = db.Column(
        db.DateTime,
        primary_key=True,
        nullable=False,
        comment="小时桶起点（UTC，由 DATE_FORMAT(collected_at,'%Y-%m-%d %H:00:00') 产出）",
    )
    avg_value = db.Column(
        db.Double,
        nullable=True,
        comment="桶内 value_num 均值；非数值指标为 NULL",
    )
    min_value = db.Column(
        db.Double,
        nullable=True,
        comment="桶内 value_num 最小值；非数值指标为 NULL",
    )
    max_value = db.Column(
        db.Double,
        nullable=True,
        comment="桶内 value_num 最大值；非数值指标为 NULL",
    )
    sample_count = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="桶内采样点数（含非数值指标；状态抖动也占一个采样点）",
    )
    sum_sq = db.Column(
        db.Double,
        nullable=True,
        comment="桶内 value_num 的平方和 Σ(x²)（非数值指标为 NULL）",
    )
    numeric_count = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="桶内 value_num 非 NULL 的行数（= AVG 的分母；方差合成必需）",
    )
    last_value = db.Column(
        db.String(255),
        nullable=True,
        comment="桶内时间最晚的原始 value（状态词靠它保真，见模块 docstring 第 2 点）",
    )
    state_changes = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="桶内 value 的跃变次数（相邻采样不同即计 1）；up→down→up 记 2",
    )
    breach_count = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="桶内 breached=1 的采样数（明细缩期后唯一能回答「这段时间是否告警过」的字段）",
    )
    worst_severity = db.Column(
        db.String(20),
        nullable=True,
        comment="桶内最坏告警级别 ok/warn/crit（按 crit > warn > ok 取 max）",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        comment="首次聚合时间",
    )
