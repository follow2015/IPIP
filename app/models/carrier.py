# -*- coding: utf-8 -*-
"""
运营商模型模块

承载线路的出租方主体：报障联系方式、资质、默认 SLA。
是"按运营商归集线路批量报障"的天然分组维度（设计文档 §3.1）。

**不是** IP 段的"ISP"标签：那个是地址归属的属性字符串，这里是独立的合作主体实体。
"""
from sqlalchemy import Index, UniqueConstraint

from app.models.base import BaseModel, MEDIUMTEXT
from app.core.enums import CarrierStatus
from extensions import db


class Carrier(BaseModel):
    """运营商。

    启用软删除。唯一键采用**占位列分离**方案（设计文档 §3.2 / 评审 B-3）：
    `uk_carrier_name` 建在 `(name, deleted_token)` 上，软删时只写 `deleted_token`，
    `name` **保持原值**——既释放了业务号供复用，又保住"软删后仍可按原名追溯"。

    早期方案是"软删时把 name 改写成带后缀的占位值"，已废弃：`name` 为 String(100)，
    占位值最长 `100 + 20 + 9 = 129` 字符必然溢出，严格模式 ERROR 1406、非严格模式
    静默截断并与真实名称撞键。
    """

    __tablename__ = "carriers"
    __soft_delete__ = True
    __table_args__ = (
        UniqueConstraint("name", "deleted_token", name="uk_carrier_name"),
        Index("idx_carrier_type", "carrier_type"),
        Index("idx_carrier_status", "status"),
        {"comment": "运营商表"},
    )

    name = db.Column(db.String(100), nullable=False, comment="运营商全称")
    deleted_token = db.Column(
        db.String(64), nullable=False, default="", server_default="",
        comment="软删占位标记（活跃行为空串；与 name 组成复合唯一键）",
    )
    short_name = db.Column(db.String(50), nullable=True, comment="简称（列表/下拉展示用）")
    carrier_type = db.Column(
        db.String(20), nullable=True,
        comment="类型：basic(基础运营商) / isp(二级) / idc(机房方) / agent(代理商)",
    )
    status = db.Column(
        db.String(20), nullable=False, default=CarrierStatus.ACTIVE.value,
        server_default=CarrierStatus.ACTIVE.value,
        comment="状态：active / inactive",
    )

    contact_person = db.Column(db.String(100), nullable=True, comment="业务联系人")
    contact_phone = db.Column(db.String(50), nullable=True, comment="联系电话")
    hotline = db.Column(db.String(50), nullable=True, comment="7x24 报障热线")
    email = db.Column(db.String(100), nullable=True, comment="邮箱")
    default_sla_level = db.Column(db.String(20), nullable=True, comment="默认 SLA，新建线路时预填")
    qualification_no = db.Column(db.String(100), nullable=True, comment="资质/营业执照号")
    notes = db.Column(MEDIUMTEXT, nullable=True, comment="备注")

    deleted_at = db.Column(db.DateTime, nullable=True, comment="软删除时间")

    def __repr__(self) -> str:
        return f"<Carrier(id={self.id}, name='{self.name}', type='{self.carrier_type}')>"
