# -*- coding: utf-8 -*-
"""
设备硬件规格模型（1:1 扩展 device_manager）

存放 CPU/内存/OS/IPMI 等硬件信息，按需 JOIN 不影响主表查询性能。
"""
from typing import Optional

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import relationship

from app.models.base import BaseModel, TINYINT
from extensions import db


class DeviceHardware(BaseModel):
    """设备硬件规格（1:1 扩展）"""

    __tablename__ = "device_hardware"
    __table_args__ = (
        Index("uk_hardware_device", "device_id", unique=True),
        Index("idx_hardware_os", "os_version"),
        Index("idx_hardware_memory_gb", "memory_size_gb"),
        {"comment": "设备硬件规格表"},
    )

    device_id = db.Column(
        db.BigInteger, ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False, comment="关联设备ID"
    )

    cpu = db.Column(db.String(100), comment="CPU型号")
    cpu_way = db.Column(TINYINT(), comment="CPU路数")
    cpu_cores = db.Column(db.SmallInteger, comment="单颗CPU核心数")
    memory = db.Column(db.String(100), comment="内存配置描述")
    memory_size_gb = db.Column(db.Integer, comment="内存总容量(GB)")
    memory_dimm_count = db.Column(db.SmallInteger, comment="内存条数")

    gpu = db.Column(db.String(200), comment="GPU配置描述")
    gpu_count = db.Column(db.SmallInteger, comment="GPU数量")
    gpu_template_id = db.Column(db.BigInteger, db.ForeignKey('component_templates.id',
                        ondelete='SET NULL'), nullable=True, index=True,
                        comment='GPU模板ID')

    storage_summary = db.Column(db.String(200), comment="存储配置摘要")

    os_version = db.Column(db.String(255), comment="操作系统版本")

    ipmi_address = db.Column(db.String(50), comment="IPMI/BMC IP地址")
    ipmi_username = db.Column(db.String(64), comment="IPMI用户名")
    ipmi_password = db.Column(db.String(255), comment="IPMI密码")

    ip_address = db.Column(JSON, comment="IP地址列表(手动录入,与ip_addresses表无关联)")

    device_config = db.Column(JSON, comment="扩展配置")

    cpu_template_id    = db.Column(db.BigInteger, db.ForeignKey('component_templates.id',
                            ondelete='SET NULL'), nullable=True, index=True,
                            comment='CPU模板ID')
    memory_template_id = db.Column(db.BigInteger, db.ForeignKey('component_templates.id',
                            ondelete='SET NULL'), nullable=True, index=True,
                            comment='内存模板ID')

    device = relationship(
        "Device",
        back_populates="hardware",
        lazy="select",     # ← 原 "joined"，改为 "select"
    )

    cpu_template    = relationship('ComponentTemplate',
                        foreign_keys=[cpu_template_id], lazy='select')
    memory_template = relationship('ComponentTemplate',
                        foreign_keys=[memory_template_id], lazy='select')
    gpu_template    = relationship('ComponentTemplate',
                        foreign_keys=[gpu_template_id], lazy='select')

    def get_ip_list(self) -> str:
        """获取IP地址列表（逗号分隔）"""
        if not self.ip_address:
            return ""
        if isinstance(self.ip_address, list):
            return ",".join(
                ip.get("ip", "") if isinstance(ip, dict) else str(ip)
                for ip in self.ip_address
            )
        return str(self.ip_address)

    def set_ip_list(self, ip_string: str) -> None:
        """从逗号分隔字符串设置IP地址列表"""
        if not ip_string:
            self.ip_address = None
            return
        ips = [ip.strip() for ip in ip_string.split(",") if ip.strip()]
        self.ip_address = [{"ip": ip, "is_primary": (i == 0)} for i, ip in enumerate(ips)]

    def get_primary_ip(self) -> Optional[str]:
        """获取主IP地址"""
        if not self.ip_address:
            return None
        if isinstance(self.ip_address, list):
            for ip_data in self.ip_address:
                if isinstance(ip_data, dict) and ip_data.get("is_primary"):
                    return ip_data.get("ip")
            first = self.ip_address[0] if self.ip_address else None
            if isinstance(first, dict):
                return first.get("ip")
            return str(first) if first else None
        return None

    def __repr__(self):
        return f"<DeviceHardware id={self.id}, device_id={self.device_id}>"
