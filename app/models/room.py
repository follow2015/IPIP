# -*- coding: utf-8 -*-
"""
机房模型模块
"""
from typing import Any, Dict, List, TYPE_CHECKING

from sqlalchemy import Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db
from app.core.enums import RoomStatus

if TYPE_CHECKING:
    from app.models.cabinet import Cabinet


class Room(BaseModel):

    __tablename__ = "rooms"
    __soft_delete__ = True
    __table_args__ = (
        Index("idx_room_deleted_status", "deleted_at", "status"),
        {"comment": "机房信息表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")

    name = db.Column(db.String(255), nullable=False, comment="机房名称")
    status = db.Column(db.Integer, default=RoomStatus.NORMAL.value, nullable=False, comment="状态：0-正常，1-停用 (RoomStatus)")
    location = db.Column(db.String(255), comment="机房位置")
    contact = db.Column(db.String(255), comment="联系人")
    contact_phone = db.Column(db.String(50), comment="联系电话")

    deleted_at = db.Column(db.DateTime, nullable=True, comment="软删除时间(NULL=未删除)")

    cabinets = relationship(
        "Cabinet",
        backref="room",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


    def to_dict(self, exclude: list = None, include_relations: bool = False) -> Dict[str, Any]:
        data = super().to_dict(exclude=exclude)

        if include_relations:
            data["cabinets"] = [cabinet.to_dict() for cabinet in self.cabinets]

        data["cabinet_count"] = len(self.cabinets)

        return data


    @property
    def cabinet_count(self) -> int:
        return len(self.cabinets)

    def get_cabinets(self) -> List["Cabinet"]:
        return list(self.cabinets)

    def __repr__(self) -> str:
        return f"<Room(id={self.id}, name='{self.name}')>"
