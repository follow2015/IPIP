"""VLAN模型"""
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.dialects.mysql import SMALLINT
from sqlalchemy.orm import relationship

from app.models.base import BaseModel, TINYINT
from extensions import db
from app.core.enums import VLANStatus


class VLAN(BaseModel):
    """VLAN资源（设备维度）

    V2.0: 增加 device_id + member_ports 字段，
    支持按交换机维度存储VLAN成员端口列表，避免每次点击详情都SSH获取。
    唯一约束改为 (device_id, vlan_id)，允许同一机房不同设备拥有相同VLAN ID。
    """
    __tablename__ = "vlans"
    __table_args__ = (
        UniqueConstraint("device_id", "vlan_id", name="uq_vlan_device"),
        Index("idx_vlan_status", "status"),
        Index("idx_vlan_device_status", "device_id", "status"),  # 前缀覆盖 idx_vlan_device
        Index("idx_vlan_room_status", "room_id", "status"),      # 前缀覆盖 idx_vlan_room
        {"comment": "VLAN资源（设备维度）"},
    )

    vlan_id = db.Column(SMALLINT(unsigned=True), nullable=False, comment="VLAN ID (1-4094)")
    name = db.Column(db.String(64), nullable=False, comment="VLAN名称")
    purpose = db.Column(db.String(255), comment="用途说明")
    subnet_id = db.Column(db.BigInteger, db.ForeignKey("ip_networks.id"), comment="关联网段ID FK→ip_networks")
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), comment="所属机房ID")
    status = db.Column(TINYINT(), nullable=False, default=VLANStatus.ACTIVE.value, comment="VLAN状态: 1=活跃 0=停用 (VLANStatus)")
    device_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False, comment="所属交换机设备ID")

    room = relationship("Room", foreign_keys=[room_id], lazy="joined")
    device = relationship("Device", foreign_keys=[device_id], lazy="joined")
    port_members = relationship(
        "VLANPortMember",
        back_populates="vlan",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def to_dict(self, exclude=None, include_relations=False):
        """序列化，包含关联的device_name和room_name"""
        result = super().to_dict(exclude=exclude)
        result['room_name'] = self.room.name if self.room else None
        result['device_name'] = self.device.device_name if self.device else None
        if hasattr(self, 'port_members') and self.port_members:
            result['member_ports'] = [m.port.port_name for m in self.port_members if m.port]
        else:
            result['member_ports'] = []
        return result
