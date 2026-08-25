# -*- coding: utf-8 -*-
"""监控指标模板表（monitor_metric_templates）

驱动 SNMP/IPMI 指标采集的配置单数据源。运维可在管理界面在线新增/调整指标
与阈值（CRUD API），worker 指标采集循环按模板驱动，无需改代码即可扩展指标。

阈值分层（全局 → 设备/端口覆盖）：
- 本表默认阈值（global 层）；
- ``device_metric_overrides`` 按 (device_id, metric_key) 覆盖设备级阈值；
- 端口级阈值通过 ``index_kind=ifIndex`` 订阅（预留，端口流量走 Zabbix 图形）。

metric_type：
- gauge：瞬时值（温度、负载），直接比较阈值
- counter：累加计数（端口字节数），需差值/速率后比较
- state：状态枚举（端口 up/down、传感器状态），按期望值比较
- event：事件型（RAID/硬盘故障），出现即告警
"""
from sqlalchemy import Index

from app.models.base import BaseModel
from extensions import db


class MonitorMetricTemplate(BaseModel):

    __tablename__ = "monitor_metric_templates"
    __table_args__ = (
        Index("uq_metric_tpl_devtype_metric_vendor", "device_type", "metric_key", "vendor", unique=True),
        {
            "comment": "监控指标模板，驱动 SNMP/IPMI 指标采集",
        },
    )

    metric_key = db.Column(
        db.String(64),
        nullable=False,
        comment="指标标识，与 monitor_oid_category_rules.category 对齐："
        "temperature / fan / if_status / cpu_usage / power_supply / memory / "
        "disk_failure / raid_failure",
    )
    category = db.Column(
        db.String(32),
        nullable=True,
        comment="OID 分类标识，关联 monitor_oid_category_rules.category；"
        "MIB 扫描导入时自动填充，用于桥接 OID 规则与指标模板",
    )
    display_name = db.Column(
        db.String(64),
        nullable=True,
        comment="中文显示名（运维视角），表格优先展示；为空时回退 metric_key",
    )
    device_type = db.Column(
        db.String(16),
        nullable=False,
        comment="适用设备类型 network / server / other",
    )
    source = db.Column(
        db.String(16),
        nullable=False,
        default="snmp",
        comment="采集来源 snmp / ipmi / zabbix",
    )
    vendor = db.Column(
        db.String(32),
        nullable=True,
        comment="厂家约束（enterprise 号），如 2011=华为 / 25506=H3C / 9=思科；"
        "声明时仅匹配同厂商设备，模板组校验时与 device_type + source 共同约束",
    )
    mib = db.Column(
        db.String(64),
        nullable=True,
        comment="MIB 名称，如 IF-MIB / ENTITY-SENSOR-MIB；IPMI/Zabbix 来源置空",
    )
    oid_symbol = db.Column(
        db.String(128),
        nullable=True,
        comment="MIB 符号名，如 ifOperStatus / entPhySensorValue；IPMI/Zabbix 来源置空",
    )
    oid = db.Column(
        db.String(128),
        nullable=True,
        comment="完整数字 OID，如 1.3.6.1.2.1.2.2.1.7；与 oid_symbol 互补，"
        "MIB 扫描导入时承接数字 OID",
    )
    zabbix_item_key = db.Column(
        db.String(128),
        nullable=True,
        comment="Zabbix item key，如 system.cpu.util / vm.memory.size[pavailable]；"
        "source=zabbix 时必填，其他来源置空",
    )
    index_kind = db.Column(
        db.String(32),
        nullable=True,
        comment="索引维度：ifIndex（按端口）/ 无索引（NULL）",
    )
    metric_type = db.Column(
        db.String(16),
        nullable=False,
        default="gauge",
        comment="gauge / counter / state / event",
    )
    unit = db.Column(
        db.String(16),
        nullable=True,
        comment="单位，如 Celsius / bps / %",
    )
    poll_interval = db.Column(
        db.Integer,
        nullable=False,
        default=60,
        comment="采集频率（秒），默认与统一轮询频率一致",
    )
    threshold = db.Column(
        db.JSON,
        nullable=True,
        comment="告警阈值（JSON）",
    )
    severity_default = db.Column(
        db.String(16),
        nullable=True,
        comment="默认告警级别 warn / crit，未配置阈值时回退使用",
    )
    enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        comment="是否启用",
    )
    description = db.Column(
        db.String(255),
        nullable=True,
        comment="指标说明（运维视角）",
    )
    runbook_url = db.Column(
        db.String(512),
        nullable=True,
        comment="处置预案 URL（内部 wiki / 文档链接），告警详情展示",
    )
    runbook_title = db.Column(
        db.String(128),
        nullable=True,
        comment="处置预案标题（runbook_url 的显示文本）",
    )
