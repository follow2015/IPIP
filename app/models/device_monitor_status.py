# -*- coding: utf-8 -*-
"""设备健康监控最新状态快照模型

每设备一行（非时序表），存储可达性状态机所需字段。
凭据协议切换（如 Redfish→IPMI）会覆盖整行，含 extra 形状变化，属预期行为。
"""
from sqlalchemy import Index

from app.models.base import BaseModel
from extensions import db


class DeviceMonitorStatus(BaseModel):
    """设备健康监控最新状态快照（每设备一行，非时序表）"""

    __tablename__ = "device_monitor_status"
    __table_args__ = (
        Index("uk_device_monitor", "device_id", unique=True),
        Index("idx_reachable", "reachable"),
        Index("idx_last_checked", "last_checked_at"),
        {"comment": "设备健康监控最新状态快照（每设备一行，非时序表）"},
    )

    device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联设备ID（每设备一行）",
    )
    protocol = db.Column(
        db.String(20),
        nullable=False,
        comment="snmp/redfish/ipmi；每设备单快照，凭据协议切换会覆盖整行",
    )
    reachable = db.Column(
        db.Boolean,
        nullable=False,
        comment="当前是否可达",
    )
    ever_reachable = db.Column(
        db.Boolean,
        nullable=False,
        server_default="0",
        comment="是否曾成功探测过（首探即不可达也能正确告警）",
    )
    down_alerted = db.Column(
        db.Boolean,
        nullable=False,
        server_default="0",
        comment="当前是否已处于不可达且已告警状态，防止停留期内重复告警",
    )
    down_episode = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="第几次进入不可达周期，写入 idempotency_key",
    )
    last_reachable_at = db.Column(
        db.DateTime,
        nullable=True,
        comment="最后一次可达时间",
    )
    last_unreachable_at = db.Column(
        db.DateTime,
        nullable=True,
        comment="最后一次不可达时间",
    )
    last_checked_at = db.Column(
        db.DateTime,
        nullable=False,
        comment="最后一次探测时间（无论成败）",
    )
    consecutive_failures = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="连续失败次数（抖动抑制/阈值判定）",
    )
    latency_ms = db.Column(
        db.Integer,
        nullable=True,
        comment="本次探测耗时",
    )
    extra = db.Column(
        db.JSON,
        nullable=True,
        comment="协议特有附加信息",
    )
    last_error = db.Column(
        db.Text,
        nullable=True,
        comment="最近一次失败的错误信息",
    )
    monitor_enabled = db.Column(
        db.Boolean,
        nullable=False,
        server_default="1",
        comment="设备级监控开关：0=暂停探测，1=正常探测（无状态行视为默认启用）",
    )
