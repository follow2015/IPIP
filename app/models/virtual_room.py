
"""虚拟机房模型

虚拟机房是用户自由组合交换机形成的逻辑扫描单元，
用于跨机房二层/三层网络场景下的联合扫描。
"""
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel
from extensions import db


class VirtualRoom(BaseModel):
    __tablename__ = "virtual_rooms"
    __table_args__ = (
        Index("idx_virtual_room_name", "name"),
        Index("uq_virtual_room_name", "name", unique=True),
        {"comment": "虚拟机房（逻辑扫描单元）"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")
    name = db.Column(db.String(255), nullable=False, unique=True, comment="虚拟机房名称")
    description = db.Column(db.String(500), comment="描述")
    last_scan_at = db.Column(db.DateTime, nullable=True, comment="最近扫描完成时间")
    last_scan_scope = db.Column(db.String(32), nullable=True, comment="最近扫描 scope 标识")

    members = relationship(
        "VirtualRoomMember",
        back_populates="virtual_room",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def to_dict(self, exclude=None, include_relations=False):
        data = super().to_dict(exclude=exclude)
        data["member_count"] = self.members.count()
        if include_relations:
            members_list = getattr(self, '_preloaded_members', None) or self.members.all()
            data["members"] = [m.to_dict() for m in members_list]
        return data


class VirtualRoomMember(db.Model):
    __tablename__ = "virtual_room_members"
    __table_args__ = (
        UniqueConstraint("virtual_room_id", "device_id", name="uq_vr_member"),
        Index("idx_vrm_device", "device_id"),
        {"comment": "虚拟机房成员（交换机）关联表"},
    )

    virtual_room_id = db.Column(
        db.Integer,
        db.ForeignKey("virtual_rooms.id", ondelete="CASCADE"),
        primary_key=True,
        comment="虚拟机房ID",
    )
    device_id = db.Column(
        db.BigInteger,
        db.ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True,
        comment="交换机设备ID",
    )
    joined_at = db.Column(
        db.DateTime, nullable=False, server_default=func.now(), comment="加入时间"
    )

    virtual_room = relationship("VirtualRoom", back_populates="members", lazy="joined")
    device = relationship("Device", lazy="select")

    def to_dict(self, exclude=None):
        data = {
            "virtual_room_id": self.virtual_room_id,
            "device_id": self.device_id,
            "joined_at": BaseModel._serialize_value(self.joined_at),
        }
        if self.device:
            dev = self.device
            data["device_name"] = dev.device_name
            data["room_id"] = dev.cabinet.room_id if dev.cabinet else None
            data["room_name"] = dev.cabinet.room.name if dev.cabinet and dev.cabinet.room else None
            if dev.switch_credential:
                data["ip"] = dev.switch_credential.ip
        return data
