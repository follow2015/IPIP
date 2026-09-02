# -*- coding: utf-8 -*-
"""设备指标基线表（device_metric_baseline）

设计文档第四节：按小时×星期分桶消除周期性。
(device_id, metric_key, index_key, hour_of_day, day_of_week) → mean, stddev, sample_count
定时任务按近 28 天同维度样本计算滑动基线。

样本 < 7 天：baseline_status = "insufficient_samples"
样本 7-28 天：baseline_status = "degraded"（仅全局均值±σ，不分组到 hour_of_day）
样本 ≥ 28 天：baseline_status = "normal"（按 hour×weekday 分桶）
"""
from sqlalchemy import ForeignKey, Index, Integer, SmallInteger, String
from sqlalchemy.dialects.mysql import DECIMAL

from app.models.base import BaseModel
from extensions import db


class DeviceMetricBaseline(BaseModel):
    """设备指标基线（按 hour_of_day × day_of_week 分桶）。"""

    __tablename__ = "device_metric_baseline"
    __table_args__ = (
        Index("uq_dmb_device_metric_hour_dow",
              "device_id", "metric_key", "index_key", "hour_of_day", "day_of_week",
              unique=True),
        Index("ix_dmb_device_metric", "device_id", "metric_key"),
        {"comment": "设备指标基线（按小时×星期分桶，滑动28天）"},
    )

    device_id = db.Column(
        db.BigInteger,
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="设备ID",
    )
    metric_key = db.Column(
        String(64),
        nullable=False,
        comment="指标标识，如 cpu_usage",
    )
    index_key = db.Column(
        String(128),
        nullable=False,
        default="",
        comment="指标实例索引（端口号等），无索引时为空串",
    )
    hour_of_day = db.Column(
        SmallInteger,
        nullable=False,
        comment="小时（0-23），降级基线时固定为 -1 表示不分桶",
    )
    day_of_week = db.Column(
        SmallInteger,
        nullable=False,
        comment="星期（0=周一...6=周日），降级基线时固定为 -1 表示不分桶",
    )
    mean = db.Column(
        DECIMAL(20, 6),
        nullable=False,
        comment="均值",
    )
    stddev = db.Column(
        DECIMAL(20, 6),
        nullable=False,
        default=0,
        comment="标准差",
    )
    sample_count = db.Column(
        Integer,
        nullable=False,
        default=0,
        comment="样本数（参与计算的采集点数）",
    )
    baseline_status = db.Column(
        String(30),
        nullable=False,
        default="normal",
        comment="normal/degraded/insufficient_samples",
    )
