# -*- coding: utf-8 -*-
"""厂商品牌表（monitor_vendor_brands）

存储 SNMP enterprise 号 → 品牌名称映射，支持自建/启用/排序。
OID 分类规则的 vendor_id 字段引用本表的 enterprise_no（外键语义，不强制 FK）。

数据来源：IANA Private Enterprise Numbers (PEN)
https://www.iana.org/assignments/enterprise-numbers
"""
from sqlalchemy import Index

from extensions import db

from .base import BaseModel


class MonitorVendorBrand(BaseModel):
    """厂商品牌（enterprise 号 → 品牌名称）"""

    __tablename__ = "monitor_vendor_brands"
    __table_args__ = (
        Index("idx_vendor_brand_enterprise", "enterprise_no"),
        Index("idx_vendor_brand_device_type", "device_type"),
        {
            "comment": "厂商品牌，enterprise 号 → 品牌名称映射",
        },
    )

    enterprise_no = db.Column(
        db.String(32),
        nullable=False,
        comment="SNMP enterprise 号（如 674=DELL），对应 OID 规则的 vendor_id",
    )
    brand_name = db.Column(
        db.String(64),
        nullable=False,
        comment="品牌全称（英文），如 Dell EMC / Cisco",
    )
    label = db.Column(
        db.String(64),
        nullable=False,
        comment="显示名称（含设备类别后缀），如 DELL（服务器） / Cisco（网络）",
    )
    device_type = db.Column(
        db.String(16),
        nullable=False,
        comment="适用设备类型 network/server/storage/other",
    )
    enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        comment="是否启用",
    )
    sort_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        comment="排序权重，小的在前",
    )

    def to_dict(self, exclude: list = None, include_relations: bool = False):
        return super().to_dict(exclude=exclude, include_relations=include_relations)
