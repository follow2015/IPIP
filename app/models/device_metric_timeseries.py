# -*- coding: utf-8 -*-
"""设备指标值历史时序（分区表）

每次采集写入一行（一个 device_id + metric_key + index_key + collected_at 一行），
与 device_metric_latest upsert 在同一事务内原子提交（见 monitor_worker._check_one_device），
供前端指标趋势图 / 历史明细查询。

分区：按日 RANGE 分区（TO_DAYS(collected_at)），保留 90 天原始数据；分区定义
由迁移 add_metric_timeseries.py 在 MySQL 上创建，SQLite 测试经 create_all
建普通表（无分区）。分区键 collected_at 必须包含在主键中，故用复合主键
(id, collected_at)，不能继承强制单列自增主键的 BaseModel。

与 device_monitor_probe_events 的区别：
- probe_events 存探测可达性/延迟（每设备每探测一行）
- 本表存业务指标值（cpu/温度/内存/端口状态等，每设备每指标每 index 每采集一行）
"""
from sqlalchemy import Index, func

from extensions import db


class DeviceMetricTimeseries(db.Model):

    __tablename__ = "device_metric_timeseries"
    __table_args__ = (
        Index("ix_dmts_device_metric_collected", "device_id", "metric_key", "collected_at"),
        Index("ix_dmts_collected", "collected_at"),
        {
            "comment": "设备指标值历史时序分区表（每次采集每指标一行，供趋势图，保留90天）",
        },
    )

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键ID（复合主键第一部分，配合分区键 collected_at）",
    )
    device_id = db.Column(
        db.BigInteger,
        nullable=False,
        comment="关联设备ID（分区表不支持外键，设备删除由应用层负责清理）",
    )
    metric_key = db.Column(
        db.String(64),
        nullable=False,
        comment="指标 key，如 cpu_usage / temperature / if_status",
    )
    index_key = db.Column(
        db.String(128),
        nullable=False,
        server_default="",
        comment="指标实例索引，如端口号 ifIndex；无索引时为空串",
    )
    value = db.Column(
        db.String(255),
        nullable=True,
        comment="指标值（字符串存储，前端按 metric_type 解析为数值/状态）",
    )
    severity = db.Column(
        db.String(20),
        nullable=True,
        comment="告警级别 ok/warn/crit（阈值判定结果）",
    )
    breached = db.Column(
        db.Boolean,
        nullable=False,
        server_default="0",
        comment="本次采集是否触发阈值告警",
    )
    collected_at = db.Column(
        db.DateTime,
        nullable=False,
        comment="采集时间（=趋势横轴，分区键）",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        comment="写入时间",
    )

    def to_dict(self, exclude: list = None) -> dict:
        data = {
            "id": self.id,
            "device_id": self.device_id,
            "metric_key": self.metric_key,
            "index_key": self.index_key,
            "value": self.value,
            "severity": self.severity,
            "breached": self.breached,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
