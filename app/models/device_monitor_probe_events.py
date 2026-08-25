# -*- coding: utf-8 -*-
"""设备探测历史时序（分区表，替代 device_monitor_probe_history）

每次探测写入一行，与状态 upsert + 告警发件箱在同一事务内原子提交
（见 ``MonitorService.apply_result``），供前端趋势图 / 历史明细查询。

分区：按日 RANGE 分区（TO_DAYS(probed_at)），保留 90 天原始数据；分区定义
由迁移 add_monitor_timeseries.py 在 MySQL 上创建，SQLite 测试经 create_all
建普通表（无分区）。分区键 probed_at 必须包含在主键中，故用复合主键
(id, probed_at)，不能继承强制单列自增主键的 BaseModel。
"""
from sqlalchemy import Index, func

from extensions import db


class DeviceMonitorProbeEvents(db.Model):

    __tablename__ = "device_monitor_probe_events"
    __table_args__ = (
        Index("ix_dmpe_device_probed", "device_id", "probed_at"),
        Index("ix_dmpe_probed", "probed_at"),
        {
            "comment": "设备探测历史时序分区表（每次探测一行，供趋势图/历史明细，保留90天）",
        },
    )

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键ID（复合主键第一部分，配合分区键 probed_at）",
    )
    device_id = db.Column(
        db.BigInteger,
        nullable=False,
        comment="关联设备ID（分区表不支持外键，设备删除由应用层负责清理，见 MEMORY）",
    )
    protocol = db.Column(
        db.String(20),
        nullable=False,
        comment="snmp/redfish/ipmi/zabbix",
    )
    reachable = db.Column(
        db.Boolean,
        nullable=False,
        comment="本次是否可达",
    )
    latency_ms = db.Column(
        db.Integer,
        nullable=True,
        comment="本次探测耗时（毫秒）",
    )
    consecutive_failures = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="探测时连续失败次数（抖动抑制/阈值判定）",
    )
    episode = db.Column(
        db.Integer,
        nullable=False,
        server_default="0",
        comment="不可达周期序号（每进入一次不可达 +1）",
    )
    is_alert = db.Column(
        db.Boolean,
        nullable=False,
        server_default="0",
        comment="本次探测是否触发告警（不可达/恢复）",
    )
    error = db.Column(
        db.Text,
        nullable=True,
        comment="不可达时的错误码/信息",
    )
    extra = db.Column(
        db.JSON,
        nullable=True,
        comment="协议特有附加信息（精简快照）",
    )
    probed_at = db.Column(
        db.DateTime,
        nullable=False,
        comment="探测时间（=趋势横轴，分区键）",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        comment="写入时间",
    )

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> dict:
        data = {
            "id": self.id,
            "device_id": self.device_id,
            "protocol": self.protocol,
            "reachable": self.reachable,
            "latency_ms": self.latency_ms,
            "consecutive_failures": self.consecutive_failures,
            "episode": self.episode,
            "is_alert": self.is_alert,
            "error": self.error,
            "extra": self.extra,
            "probed_at": self.probed_at.isoformat() if self.probed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
