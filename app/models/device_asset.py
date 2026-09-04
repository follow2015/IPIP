# -*- coding: utf-8 -*-
"""
设备资产台账模型（1:1 扩展 device_manager）

存放采购/资产/保修信息，与硬件规格解耦。
"""

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel, TINYINT
from extensions import db

class DeviceAsset(BaseModel):
    """设备资产台账（1:1 扩展）"""

    __tablename__ = "device_asset"
    __table_args__ = (
        Index("uk_asset_device", "device_id", unique=True),
        Index("uk_asset_number", "asset_number", unique=True),
        Index("idx_asset_warranty_end", "warranty_end"),
        Index("idx_asset_purchase_date", "purchase_date"),
        Index("idx_asset_supplier", "supplier"),
        {"comment": "设备资产台账表"},
    )

    device_id = db.Column(
        db.BigInteger, ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False, comment="关联设备ID"
    )

    asset_number = db.Column(db.String(64), comment="资产编号")

    supplier = db.Column(db.String(100), comment="供应商名称")
    supplier_contact = db.Column(db.String(100), comment="供应商联系人")
    contract_number = db.Column(db.String(100), comment="采购合同编号")
    purchase_date = db.Column(db.Date, comment="采购日期")
    purchase_price = db.Column(db.Numeric(12, 2), comment="采购价格(元)")
    invoice_number = db.Column(db.String(100), comment="发票号码")

    warranty_start = db.Column(db.Date, comment="保修开始日期")
    warranty_end = db.Column(db.Date, comment="保修到期日期")
    warranty_type = db.Column(db.String(50), comment="保修类型")

    online_date = db.Column(db.Date, comment="上线投产日期")
    offline_date = db.Column(db.Date, comment="下线/报废日期")
    lifecycle_years = db.Column(TINYINT(), comment="预计使用年限")

    device = relationship(
        "Device",
        back_populates="asset",
        lazy="select",     # ← 原 "joined"，改为 "select"
    )

    def __repr__(self):
        return f"<DeviceAsset id={self.id}, device_id={self.device_id}>"
