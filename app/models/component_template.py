# -*- coding: utf-8 -*-
"""
配件模板模型

预定义 CPU/内存/硬盘/网卡等配件的型号规格，
设备创建时选择模板而非手动输入，提升录入效率和数据一致性。
"""
from typing import Any, Dict

from app.models.base import BaseModel
from extensions import db


class ComponentTemplate(BaseModel):
    """配件模板模型

    按类别预定义常用配件规格，设备创建时通过下拉选择引用。
    支持 CPU/内存/硬盘/网卡/GPU 五大类别，spec JSON 存储类别特有属性。
    """
    __tablename__ = "component_templates"

    category = db.Column(
        db.String(20), nullable=False, index=True,
        comment="配件类别: cpu/memory/disk/nic/gpu"
    )
    scope = db.Column(
        db.Enum('global', 'customer'), nullable=False, default='global', index=True,
        comment="模板作用域: global=公共模板, customer=客户专属模板"
    )
    customer_id = db.Column(db.BigInteger, db.ForeignKey('customers.id',
                        ondelete='SET NULL'), nullable=True, index=True,
                        comment='客户ID，scope=customer时必填')
    brand = db.Column(db.String(100), nullable=True, comment="品牌")
    model = db.Column(db.String(100), nullable=False, comment="型号")
    spec = db.Column(db.JSON, nullable=True, comment="规格详情(JSON)")
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True, comment="是否启用")
    sort_order = db.Column(db.SmallInteger, nullable=False, default=0, comment="排序权重(小=靠前)")
    remark = db.Column(db.String(200), nullable=True, comment="备注")

    customer = db.relationship('Customer', foreign_keys=[customer_id], lazy='select')

    __table_args__ = (
        db.UniqueConstraint("category", "customer_id", "model", name="uq_ct_category_customer_model"),
        {"comment": "配件模板(预定义CPU/内存/硬盘/网卡规格)"},
    )

    def validate_scope_customer(self) -> None:
        """验证 scope='customer' 时 customer_id 不为空。

        MySQL 不允许在 CHECK 约束中引用 FK 列的 referential action，
        因此在 ORM 层做验证。
        """
        if self.scope == 'customer' and self.customer_id is None:
            from app.exceptions.validation import ValidationError
            raise ValidationError("客户专属模板(scope='customer')必须指定 customer_id")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "category": self.category,
            "scope": self.scope,
            "brand": self.brand,
            "model": self.model,
            "spec": self.spec,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "remark": self.remark,
            "customer_id": self.customer_id,
            "customer_name": self.customer.customer_name if self.customer else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<ComponentTemplate {self.id}: [{self.category}] {self.brand} {self.model}>"
