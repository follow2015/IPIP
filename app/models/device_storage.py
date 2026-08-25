# -*- coding: utf-8 -*-
"""
设备存储模型

定义设备硬盘/存储信息。
"""
from typing import Any, Dict

from sqlalchemy import Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db


class DeviceStorage(BaseModel):
    """设备存储模型

    表示设备的硬盘/存储配置信息。每条记录对应一块物理硬盘（count 固定为 1）。
    批量统计时在 Repository 层通过 GROUP BY 聚合展示。
    """

    __tablename__ = "device_storage"
    __table_args__ = (
        Index("idx_storage_device_type", "device_id", "storage_type"),  # 按设备+存储类型聚合查询
        {"comment": "设备存储表"},
    )

    device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="设备ID",
    )
    storage_type = db.Column(db.String(50), nullable=False, comment="存储类型（HDD/SSD/NVMe等）")
    capacity = db.Column(db.String(50), nullable=False, comment="容量（如 2TB, 500GB）")
    capacity_gb = db.Column(db.Integer, comment="容量数值(GB)")
    interface_type = db.Column(db.String(50), nullable=True, comment="接口类型（SATA/SAS/NVMe等）")
    slot_number = db.Column(db.SmallInteger, comment="硬盘槽位号")
    manufacturer = db.Column(db.String(100), nullable=True, comment="制造商")
    model = db.Column(db.String(100), nullable=True, comment="型号")
    template_id = db.Column(db.BigInteger, db.ForeignKey('component_templates.id',
                      ondelete='SET NULL'), nullable=True, index=True,
                      comment='硬盘模板ID')
    serial_number = db.Column(
        db.String(100), nullable=True, unique=True, index=True, comment="序列号（全局唯一）"
    )
    firmware = db.Column(db.String(50), nullable=True, comment="固件版本")
    status = db.Column(db.String(20), nullable=False, default="normal", comment="运行状态: normal/warning/error/offline")

    device = relationship(
        "Device",
        foreign_keys=[device_id],
        back_populates="storage_devices",
        lazy="joined",
    )

    template    = relationship('ComponentTemplate', foreign_keys=[template_id], lazy='select')

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "device_id": self.device_id,
            "storage_type": self.storage_type,
            "capacity": self.capacity,
            "capacity_gb": self.capacity_gb,
            "interface_type": self.interface_type,
            "slot_number": self.slot_number,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "template_id": self.template_id,
            "serial_number": self.serial_number,
            "firmware": self.firmware,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<DeviceStorage {self.id}: {self.storage_type} {self.capacity}>"
