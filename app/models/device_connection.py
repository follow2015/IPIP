# -*- coding: utf-8 -*-
"""
设备连接模型（D2N）

定义设备（服务器）与交换机端口的连接关系。
网络设备间互联（N2N）由 NetworkConnection 模型负责。
"""
from typing import Any, Dict

from sqlalchemy import Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db


class DeviceConnection(BaseModel):
    """设备连接模型（D2N）

    表示设备（服务器）与交换机端口的连接关系。
    通过device_nics_port_id关联到device_nics_port表,统一管理端口信息。
    N2N连接由 NetworkConnection（network_connections表）负责，本表不再承担。
    """

    __tablename__ = "device_connections"
    __table_args__ = (
        Index("idx_device_nics_port", "device_nics_port_id"),
        Index("idx_dc_vlan_id", "vlan_id"),
        Index("idx_dc_device_switch", "device_id", "switch_device_id"),  # D2N连接按设备+交换机联合筛选
        {"comment": "设备连接表(D2N)"},
    )

    device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="设备ID（服务器）",
    )
    switch_device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="交换机设备ID",
    )
    switch_port_id = db.Column(
        db.BigInteger,
        db.ForeignKey("network_ports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="交换机端口ID(兼容旧数据)",
    )

    device_nics_port_id = db.Column(
        db.BigInteger,
        db.ForeignKey("device_nics_port.id", ondelete="CASCADE"),
        nullable=True,
        comment="设备网卡端口ID(关联device_nics_port表)"
    )

    connection_type = db.Column(db.String(50), nullable=True, comment="连接类型")
    vlan_id = db.Column(db.Integer, nullable=True, comment="VLAN ID(逻辑关联vlans.vlan_id,不加FK因D2N连接可能引用采集缓存值)")
    status = db.Column(db.String(20), nullable=True, default="active", comment="连接状态(active/inactive)")
    notes = db.Column(db.Text, nullable=True, comment="备注")

    bandwidth = db.Column(db.String(20), nullable=True, comment="带宽")
    description = db.Column(db.String(200), nullable=True, comment="描述")
    lag_group_id = db.Column(db.BigInteger, db.ForeignKey("link_aggregation_groups.id", ondelete="SET NULL"), nullable=True, comment="所属聚合组 FK→link_aggregation_groups")
    port_role = db.Column(
        db.Enum('standalone', 'primary', 'backup', 'member', name='port_role_enum'),
        nullable=False, default='standalone', comment="连接角色"
    )
    redundancy_mode = db.Column(
        db.Enum('none', 'active-standby', 'active-active', name='redundancy_mode_enum'),
        nullable=False, default='none', comment="冗余模式"
    )
    vlan_mode = db.Column(
        db.Enum('access', 'trunk', 'hybrid', name='vlan_mode_enum'),
        nullable=False, default='access', comment="VLAN模式"
    )
    native_vlan = db.Column(db.SmallInteger, nullable=True, comment="Native VLAN(trunk口用)")

    device = relationship(
        "Device",
        foreign_keys=[device_id],
        back_populates="connections",
        lazy="joined",
    )
    switch_device = relationship(
        "Device",
        foreign_keys=[switch_device_id],
        back_populates="switch_connections",
        lazy="joined",
    )
    switch_port = relationship(
        "NetworkPort",
        foreign_keys=[switch_port_id],
        back_populates="connection",
        lazy="joined",
    )
    
    nics_port = relationship(
        "DeviceNicsPort",
        foreign_keys=[device_nics_port_id],
        back_populates="source_connections",
        lazy="joined"
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        连接状态推导规则（D2N）：
        - 仅检查交换机端口（switch_port）的 link_status
        - 逻辑端口不参与推导
        - 物理端口 link_status 非 up → inactive
        """
        from app.models.network_port import NetworkPort

        derived_status = self.status or "active"
        if self.switch_port:
            if not NetworkPort.is_logical_port(self.switch_port.port_name):
                if (self.switch_port.link_status or "").lower() != "up":
                    derived_status = "inactive"

        result: Dict[str, Any] = {
            "id": self.id,
            "device_id": self.device_id,
            "switch_device_id": self.switch_device_id,
            "switch_port_id": self.switch_port_id,
            "device_nics_port_id": self.device_nics_port_id,
            "link_type": "device_to_network",
            "connection_type": self.connection_type,
            "vlan_id": self.vlan_id,
            "status": derived_status,
            "notes": self.notes,
            "bandwidth": self.bandwidth,
            "description": self.description,
            "lag_group_id": self.lag_group_id,
            "port_role": self.port_role or "standalone",
            "redundancy_mode": self.redundancy_mode or "none",
            "vlan_mode": self.vlan_mode or "access",
            "native_vlan": self.native_vlan,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if self.device:
            result["device_name"] = self.device.device_name

        if self.switch_device:
            result["switch_name"] = self.switch_device.device_name

        if self.nics_port:
            result["source_nic_number"] = self.nics_port.nic_number
            result["source_port_number"] = self.nics_port.port_number
            result["source_port_display"] = self.nics_port.display_name
            result["device_nics_port_name"] = self.nics_port.display_name  # 添加此字段供前端使用
            result["port_type"] = self.nics_port.port_type
            result["port_speed"] = self.nics_port.port_speed

        if self.switch_port:
            result["switch_port_name"] = self.switch_port.port_name
            result["port_name"] = self.switch_port.port_name

        return result

    def __repr__(self) -> str:
        return (
            f"<DeviceConnection {self.id}: "
            f"Device {self.device_id} -> Switch {self.switch_device_id}>"
        )
