# -*- coding: utf-8 -*-
"""
交换机扩展表模型（1:1 扩展 devices）

存放交换机专属字段，按需 JOIN 不影响主表查询性能。
与 devices 表形成 joined-table 继承模式。

注意：此表主键为 device_id（FK→devices.id），不使用 BaseModel 的自增 id。
"""
from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel
from extensions import db


class DeviceSwitchExt(db.Model):
    """交换机扩展表（1:1 扩展 devices）

    仅交换机(device_type='switch')使用。
    device_id 为主键兼外键，与 devices 表 1:1 关联。
    """

    __tablename__ = "device_switch_ext"
    __table_args__ = (
        Index("idx_switch_ext_role", "switch_role"),
        Index("idx_switch_ext_uplink", "uplink_device_id"),
        Index("idx_switch_ext_core", "core_device_id"),
        {"comment": "交换机扩展表(1:1扩展devices,仅交换机)"},
    )

    device_id = db.Column(
        db.BigInteger, ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True, comment="设备ID(PK+FK→devices.id)"
    )
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = db.Column(
        db.DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间",
    )

    switch_role = db.Column(
        db.SmallInteger, nullable=True,
        comment="交换机角色: 0=核心, 1=接入, NULL=非交换机"
    )
    layer = db.Column(
        db.SmallInteger, nullable=True, comment="网络层级"
    )
    uplink_device_id = db.Column(
        db.BigInteger, ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True, comment="上行设备ID"
    )
    uplink_port_ids = db.Column(
        db.JSON, nullable=True, comment="本机上行端口ID数组(引用network_ports.id,如[1,2])"
    )
    core_device_id = db.Column(
        db.BigInteger, ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True, comment="核心交换机ID"
    )
    port_num = db.Column(
        db.SmallInteger, nullable=True, comment="端口数量"
    )
    port_sync_enabled = db.Column(
        db.Boolean, nullable=True,
        comment="端口同步开关(NULL=跟随全局,True=强制开,False=强制关)",
    )

    device = relationship(
        "Device",
        foreign_keys=[device_id],
        back_populates="switch_ext",
        lazy="select",
        uselist=False,
    )
    uplink_device = relationship(
        "Device",
        foreign_keys=[uplink_device_id],
        lazy="select",
    )
    core_device = relationship(
        "Device",
        foreign_keys=[core_device_id],
        lazy="select",
    )

    def to_dict(self, exclude=None, include_relations=False):
        """序列化"""
        return {
            "device_id": self.device_id,
            "switch_role": self.switch_role,
            "layer": self.layer,
            "uplink_device_id": self.uplink_device_id,
            "uplink_port_ids": self.uplink_port_ids,
            "core_device_id": self.core_device_id,
            "port_num": self.port_num,
            "port_sync_enabled": self.port_sync_enabled,
            "created_at": BaseModel._serialize_value(self.created_at),
            "updated_at": BaseModel._serialize_value(self.updated_at),
        }

    def __repr__(self):
        return f"<DeviceSwitchExt device_id={self.device_id}>"
