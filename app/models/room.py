# -*- coding: utf-8 -*-
"""
机房模型模块
"""
from typing import Any, Dict, List, TYPE_CHECKING

from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db
from app.core.enums import RoomStatus

if TYPE_CHECKING:
    from app.models.cabinet import Cabinet


class Room(BaseModel):
    """机房模型

    管理机房的基本信息，包括名称、位置、联系人等。
    一个机房可以包含多个机柜。
    删除即物理删除（依赖检查由 RoomService.delete 把关）；
    软删除仅保留给设备（DeviceRecycleBin 回收站）。
    """

    __tablename__ = "rooms"
    __table_args__ = (
        {"comment": "机房信息表"},
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, comment="主键ID")

    name = db.Column(db.String(255), nullable=False, comment="机房名称")
    status = db.Column(db.Integer, default=RoomStatus.NORMAL.value, nullable=False, comment="状态：0-正常，1-停用 (RoomStatus)")
    location = db.Column(db.String(255), comment="机房位置")
    contact = db.Column(db.String(255), comment="联系人")
    contact_phone = db.Column(db.String(50), comment="联系电话")

    cabinets = relationship(
        "Cabinet",
        backref="room",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


    def to_dict(self, exclude: list = None, include_relations: bool = False) -> Dict[str, Any]:
        """转换为字典

        Args:
            exclude: 要排除的字段列表
            include_relations: 是否包含关联对象

        Returns:
            Dict: 机房数据字典
        """
        data = super().to_dict(exclude=exclude)

        if include_relations:
            data["cabinets"] = [cabinet.to_dict() for cabinet in self.cabinets]

        data["cabinet_count"] = len(self.cabinets)

        return data


    @property
    def cabinet_count(self) -> int:
        """机房内的机柜数量（使用已加载的 relationship）"""
        return len(self.cabinets)

    def get_cabinets(self) -> List["Cabinet"]:
        """返回机房内的所有机柜（使用已加载的 relationship）"""
        return list(self.cabinets)

    def __repr__(self) -> str:
        return f"<Room(id={self.id}, name='{self.name}')>"
