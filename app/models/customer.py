# -*- coding: utf-8 -*-
"""
客户模型模块
"""
from typing import Any, Dict

from sqlalchemy import Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel, MEDIUMTEXT
from extensions import db
from app.core.enums import CustomerStatus


class Customer(BaseModel):
    """客户模型

    管理客户的基本信息，包括名称、联系人、联系方式等。
    一个客户可以拥有多个机柜和设备。
    """

    __tablename__ = "customers"
    __soft_delete__ = True  # 启用软删除，客户注销改为设置 deleted_at
    __table_args__ = (
        {"comment": "客户信息表"},
    )

    customer_name = db.Column(
        db.String(255), unique=True, nullable=False, comment="客户名称"
    )
    customer_status = db.Column(db.SmallInteger, nullable=False, default=CustomerStatus.ACTIVE.value, comment="客户状态(0-活跃 1-停用 2-待审核 3-终止) (CustomerStatus)")
    
    contact_person = db.Column(db.String(50), nullable=True, comment="联系人")
    contact_phone = db.Column(db.String(20), nullable=True, comment="联系电话")
    email = db.Column(db.String(100), nullable=True, comment="联系邮箱")
    address = db.Column(db.String(200), nullable=True, comment="客户地址")
    notes = db.Column(MEDIUMTEXT, nullable=True, comment="备注信息")
    
    deleted_at = db.Column(db.DateTime, nullable=True, comment="软删除时间(NULL=未删除)")
    
    devices = relationship("Device", back_populates="customer", lazy="select")

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> Dict[str, Any]:
        """转换为字典

        Args:
            exclude: 要排除的字段列表
            include_relations: 是否包含关联对象

        Returns:
            Dict: 客户数据字典
        """
        data = super().to_dict(exclude=exclude, include_relations=include_relations)

        if include_relations:
            data["cabinets"] = [cabinet.to_dict() for cabinet in self.cabinets]
            data["devices"] = [device.to_dict() for device in self.devices]

        return data

    def __repr__(self) -> str:
        """返回客户的字符串表示"""
        return f"<Customer(id={self.id}, name='{self.customer_name}')>"
