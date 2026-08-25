# -*- coding: utf-8 -*-
"""监控指标模板组表（monitor_metric_template_groups）

运维可自定义指标分组，将多个指标模板勾选入组，前端「监控数据」页按组展示卡片。
不勾选组的模板按默认匹配规则（metric_key → 前端 METRIC_GROUPS）展示。

校验规则（service 层强制）：
- 同组模板的 device_type + source 必须一致（不同设备类型/来源不能同组）；
- 组级 vendor 若声明，则入组模板的 vendor 需匹配（不同厂家不能同组）；
- 组名 (name, device_type, source) 唯一。
"""
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT as MYSQL_BIGINT

from app.models.base import BaseModel
from extensions import db

_UNSIGNED_BIGINT = MYSQL_BIGINT(unsigned=True)


class MonitorMetricTemplateGroup(BaseModel):
    """监控指标模板组（运维自定义分组）"""

    __tablename__ = "monitor_metric_template_groups"
    __table_args__ = (
        UniqueConstraint(
            "name", "device_type", "source",
            name="uq_mmtg_name_devtype_source",
        ),
        Index("ix_mmtg_devtype_source", "device_type", "source"),
        {"comment": "监控指标模板组（运维自定义分组，约束同 device_type+source）"},
    )

    name = db.Column(
        db.String(64),
        nullable=False,
        comment="组名（运维可读），如 '华为网络设备核心指标'",
    )
    device_type = db.Column(
        db.String(16),
        nullable=False,
        comment="适用设备类型 network / server / other；组内模板必须一致",
    )
    source = db.Column(
        db.String(16),
        nullable=False,
        comment="采集来源 snmp / ipmi / zabbix；组内模板必须一致",
    )
    vendor = db.Column(
        db.String(32),
        nullable=True,
        comment="厂家约束（可空）；声明时组内模板 vendor 需匹配",
    )
    display_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        comment="展示排序（升序），同 device_type+source 内排序",
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
        comment="组说明",
    )

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> dict:
        result = super().to_dict(exclude=exclude, include_relations=include_relations)
        return result


class MonitorMetricTemplateGroupItem(BaseModel):
    """模板组-模板关联（多对多，勾选指标入组）"""

    __tablename__ = "monitor_metric_template_group_items"
    __table_args__ = (
        UniqueConstraint(
            "group_id", "template_id",
            name="uq_mmtgi_group_template",
        ),
        Index("ix_mmtgi_group_id", "group_id"),
        {"comment": "模板组-模板关联（勾选指标入组）"},
    )

    group_id = db.Column(
        db.BigInteger,
        db.ForeignKey("monitor_metric_template_groups.id", ondelete="CASCADE"),
        nullable=False,
        comment="组ID",
    )
    template_id = db.Column(
        _UNSIGNED_BIGINT,
        db.ForeignKey("monitor_metric_templates.id", ondelete="CASCADE"),
        nullable=False,
        comment="模板ID",
    )
