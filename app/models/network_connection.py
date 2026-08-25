# -*- coding: utf-8 -*-
"""
网络设备间连接模型（N2N）

将 network_ports 中的 connected_port_id/connected_device_id
迁移到独立连接表，解决 N2N 模式缺少业务字段的问题。
"""
from typing import Any, Dict, Optional

from sqlalchemy import Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db


class NetworkConnection(BaseModel):

    __tablename__ = "network_connections"
    __table_args__ = (
        Index("idx_nc_local_device", "local_device_id"),
        Index("idx_nc_peer_device", "peer_device_id"),
        Index("idx_nc_lag_group", "lag_group_id"),
        Index("idx_nc_vlan_id", "vlan_id"),
        {"comment": "网络设备间连接表(N2N)"},
    )

    local_port_id = db.Column(
        db.BigInteger,
        db.ForeignKey("network_ports.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="本机端口 FK→network_ports.id",
    )
    peer_port_id = db.Column(
        db.BigInteger,
        db.ForeignKey("network_ports.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="对端端口 FK→network_ports.id",
    )

    local_device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="本机设备 FK→devices.id",
    )
    peer_device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="对端设备 FK→devices.id",
    )

    connection_type = db.Column(
        db.String(50), nullable=True,
        comment="连接类型(ethernet/fiber/management/serial/other)",
    )
    vlan_id = db.Column(db.SmallInteger, nullable=True, comment="VLAN标识号(1-4094,逻辑关联vlans.vlan_id,不加FK因N2N连接可能引用采集缓存值)")
    status = db.Column(
        db.String(20), nullable=False, default="active",
        comment="连接状态(active/inactive)",
    )
    notes = db.Column(db.Text, nullable=True, comment="备注")
    bandwidth = db.Column(db.String(20), nullable=True, comment="带宽")
    description = db.Column(db.String(200), nullable=True, comment="描述")
    lag_group_id = db.Column(
        db.BigInteger, db.ForeignKey("link_aggregation_groups.id", ondelete="SET NULL"), nullable=True,
        comment="所属聚合组 FK→link_aggregation_groups",
    )

    local_port = relationship(
        "NetworkPort", foreign_keys=[local_port_id], lazy="joined",
    )
    peer_port = relationship(
        "NetworkPort", foreign_keys=[peer_port_id], lazy="joined",
    )
    local_device = relationship(
        "Device", foreign_keys=[local_device_id], lazy="joined",
    )
    peer_device = relationship(
        "Device", foreign_keys=[peer_device_id], lazy="joined",
    )

    def to_dict(self, include_relations: bool = False,
                perspective_device_id: Optional[int] = None) -> Dict[str, Any]:
        from app.models.network_port import NetworkPort

        flip = (perspective_device_id is not None
                and perspective_device_id == self.peer_device_id)
        my_port   = self.peer_port   if flip else self.local_port
        my_device = self.peer_device if flip else self.local_device
        remote_port   = self.local_port   if flip else self.peer_port
        remote_device = self.local_device if flip else self.peer_device

        derived_status = "active"
        if self.local_port and self.peer_port:
            derived_status = NetworkPort.derive_connection_status(
                local_link_status=self.local_port.link_status,
                peer_link_status=self.peer_port.link_status,
                local_port_name=self.local_port.port_name,
                peer_port_name=self.peer_port.port_name,
            )

        result = {
            "id": self.id,
            "local_port_id": my_port.id if my_port else self.local_port_id,
            "peer_port_id": remote_port.id if remote_port else self.peer_port_id,
            "local_device_id": my_device.id if my_device else self.local_device_id,
            "peer_device_id": remote_device.id if remote_device else self.peer_device_id,
            "link_type": "network_to_network",
            "connection_type": self.connection_type,
            "vlan_id": self.vlan_id,
            "status": derived_status,
            "notes": self.notes,
            "bandwidth": self.bandwidth,
            "description": self.description,
            "lag_group_id": self.lag_group_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if my_port:
            result["port_name"] = my_port.port_name
            result["port_type"] = my_port.port_type
            result["speed"] = my_port.speed
            result["usage_status"] = my_port.usage_status
            result["device_id"] = my_port.device_id

        if my_device:
            result["device_name"] = my_device.device_name

        if remote_port:
            result["peer_port_name"] = remote_port.port_name
            result["peer_port_id"] = remote_port.id
            result["peer_port_type"] = remote_port.port_type
            result["peer_port_speed"] = remote_port.speed
            result["peer_device_id"] = remote_port.device_id

        if remote_device:
            result["peer_device_name"] = remote_device.device_name

        return result

    def __repr__(self) -> str:
        return (
            f"<NetworkConnection {self.id}: "
            f"Port {self.local_port_id} ↔ Port {self.peer_port_id}>"
        )
