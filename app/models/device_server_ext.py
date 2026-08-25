# -*- coding: utf-8 -*-
"""
服务器扩展表模型（1:1 扩展 devices）

存放服务器/机箱专属字段，按需 JOIN 不影响主表查询性能。
与 devices 表形成 joined-table 继承模式。

注意：此表主键为 device_id（FK→devices.id），不使用 BaseModel 的自增 id。
"""
from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel
from extensions import db


class DeviceServerExt(db.Model):

    __tablename__ = "device_server_ext"
    __table_args__ = (
        Index("idx_server_ext_parent", "parent_device_id"),
        Index("idx_server_ext_chassis", "is_chassis"),
        {"comment": "服务器扩展表(1:1扩展devices,仅服务器/机箱)"},
    )

    device_id = db.Column(
        db.BigInteger, ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True, comment="设备ID(PK+FK→devices.id)"
    )
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = db.Column(
        db.DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间",
    )

    parent_device_id = db.Column(
        db.BigInteger, ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True, comment="父设备ID(机箱→设备)"
    )
    is_chassis = db.Column(
        db.Boolean, nullable=True, default=False, comment="是否为机箱"
    )
    node_position = db.Column(
        db.Integer, nullable=True, comment="节点在机箱中的位置"
    )
    node_row = db.Column(db.Integer, nullable=True, comment="节点行号")
    node_col = db.Column(db.Integer, nullable=True, comment="节点列号")
    total_nodes = db.Column(
        db.Integer, nullable=True, comment="机箱总节点数"
    )
    node_rows = db.Column(db.Integer, nullable=True, comment="节点行数")
    node_cols = db.Column(db.Integer, nullable=True, comment="节点列数")
    node_naming_pattern = db.Column(
        db.String(100), nullable=True, comment="节点命名模式"
    )

    device = relationship(
        "Device",
        foreign_keys=[device_id],
        back_populates="server_ext",
        lazy="select",
        uselist=False,
    )
    parent_device = relationship(
        "Device",
        foreign_keys=[parent_device_id],
        lazy="selectin",
    )

    def to_dict(self, exclude=None, include_relations=False):
        return {
            "device_id": self.device_id,
            "parent_device_id": self.parent_device_id,
            "is_chassis": self.is_chassis,
            "node_position": self.node_position,
            "node_row": self.node_row,
            "node_col": self.node_col,
            "total_nodes": self.total_nodes,
            "node_rows": self.node_rows,
            "node_cols": self.node_cols,
            "node_naming_pattern": self.node_naming_pattern,
            "created_at": BaseModel._serialize_value(self.created_at),
            "updated_at": BaseModel._serialize_value(self.updated_at),
        }

    def __repr__(self):
        return f"<DeviceServerExt device_id={self.device_id}>"
