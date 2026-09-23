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

PING_QUALITY_EXTRA_KEYS = ("loss_pct", "jitter_ms", "samples")


def _as_float(raw):
    """容错取浮点：非数值/布尔/缺值一律 None（**绝不回落 0**）。"""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def ping_quality_from_extra(extra) -> dict:
    """从 ``extra``（JSON 列）提取 ping 质量三值。

    返回 ``{"loss_pct": float|None, "jitter_ms": float|None, "samples": int|None}``。

    三条刻意的行为，都不是随手写的：

    - 非 ping 行（``extra`` 为 None 或不含这些键）→ 三个 ``None``，**不是 0**。
      0 的语义是"测到了、而且一个都没丢"；``None`` 是"这一轮没做质量采样"。
      把后者写成前者就是**假绿灯** —— 丢包率 0% 和"根本没测"在界面上长得一样，
      而前者会让人放心、后者才是需要处理的（配置没开 / 解析失败）。
    - ``extra`` 不是 dict（历史脏数据、被手工改成数组）→ 同样返回 None 而不抛异常：
      这是**读**路径，一条脏行不该让整个历史页 500。
    - 数值以字符串落在 JSON 里（``"0.5"``）照样解析 —— 兼容不同写入方。
    """
    if not isinstance(extra, dict):
        return {"loss_pct": None, "jitter_ms": None, "samples": None}
    samples = _as_float(extra.get("samples"))
    return {
        "loss_pct": _as_float(extra.get("loss_pct")),
        "jitter_ms": _as_float(extra.get("jitter_ms")),
        "samples": None if samples is None else int(samples),
    }


class DeviceMonitorProbeEvents(db.Model):
    """设备探测历史时序（每次探测一行，分区表）"""

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
        """序列化。``loss_pct`` / ``jitter_ms`` / ``samples`` 由 ``extra`` **提升**而来。

        为什么不留给消费方自己读 ``extra``：``extra`` 是自由 JSON，键名写错时
        消费方只会拿到 ``undefined`` —— 没有类型检查、没有门禁能拦，正是"只写不读"
        能长期潜伏的形态。提升成契约字段后，名字被 ``openapi.json`` →
        ``api-generated.ts`` 固定下来，写错会在 ``make check-openapi`` + ``tsc`` 变红。

        [WARN] 序列化有**两处**（本方法与
        ``monitor_timeseries_repository._row_to_dict``）。两处都必须带这三个字段，
        且都必须走 ``ping_quality_from_extra``（唯一的提取实现）——否则派生逻辑会分叉。
        """
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
            **ping_quality_from_extra(self.extra),
            "probed_at": self.probed_at.isoformat() if self.probed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data
