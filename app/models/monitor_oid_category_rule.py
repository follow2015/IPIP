# -*- coding: utf-8 -*-
"""OID 分类规则表（monitor_oid_category_rules）

MIB 探测时按 OID 前缀自动打 category 标签，前端按 category 推荐勾选。
新增厂商/BMC 版本只需加一条规则，无需改代码。

匹配规则（点分隔符锚定，避免 1.7 误命中 1.70）：
    oid == prefix or oid.startswith(prefix + '.')

vendor_id 用于厂商锚定加速：
- 从 sysObjectID（1.3.6.1.2.1.1.2.0）提取 enterprise 号（如 674=DELL）
- 匹配时先查 vendor_id 相同的规则，再查 vendor_id IS NULL 的通用规则
- prefix 1.3.6.1.4.1.674.* → vendor_id='674'
"""
from sqlalchemy import Index

from extensions import db

from .base import BaseModel


class MonitorOidCategoryRule(BaseModel):

    __tablename__ = "monitor_oid_category_rules"
    __table_args__ = (
        Index("idx_oid_rule_prefix", "prefix"),
        Index("idx_oid_rule_vendor", "vendor_id"),
        {
            "comment": "OID 分类规则，探测时按前缀打 category 标签",
        },
    )

    prefix = db.Column(
        db.String(128),
        nullable=False,
        comment="OID 前缀，点分隔符锚定匹配（oid==prefix 或 oid.startswith(prefix+'.'）",
    )
    category = db.Column(
        db.String(32),
        nullable=False,
        comment="类别标识，如 temperature / fan / if_status",
    )
    label = db.Column(
        db.String(64),
        nullable=True,
        comment="人类可读类别名，如 温度探头",
    )
    device_type = db.Column(
        db.String(16),
        nullable=True,
        comment="适用设备类型 network/server/other；NULL=全适用",
    )
    vendor_id = db.Column(
        db.String(32),
        nullable=True,
        comment="厂商 enterprise 号（如 674=DELL）；NULL=通用规则",
    )
    priority = db.Column(
        db.Integer,
        nullable=False,
        default=10,
        comment="优先级，高优先先匹配；厂商特定规则用 100，通用用 10",
    )
    enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        comment="是否启用",
    )

    def to_dict(self, exclude: list = None, include_relations: bool = False):
        return super().to_dict(exclude=exclude, include_relations=include_relations)
