"""VLAN 成员端口关联表 ORM 模型"""
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db


class VLANPortMember(BaseModel):
    __tablename__ = "vlan_port_members"
    __table_args__ = (
        UniqueConstraint("vlan_id", "port_id", name="uk_vpm_vlan_port"),
        Index("idx_vpm_port", "port_id"),
        {"comment": "VLAN成员端口关联表"},
    )

    vlan_id = db.Column(
        db.BigInteger,
        db.ForeignKey("vlans.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK→vlans.id",
    )
    port_id = db.Column(
        db.BigInteger,
        db.ForeignKey("network_ports.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK→network_ports.id",
    )
    port_mode = db.Column(
        db.Enum("access", "trunk", "hybrid"),
        nullable=False,
        default="access",
        comment="端口模式",
    )

    vlan = relationship("VLAN", back_populates="port_members")
    port = relationship("NetworkPort", foreign_keys=[port_id])

    def to_dict(self, exclude=None, include_relations=False):
        result = super().to_dict(exclude=exclude)
        result["port_name"] = self.port.port_name if self.port else None
        return result
