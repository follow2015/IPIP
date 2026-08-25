# -*- coding: utf-8 -*-
"""虚拟机房 Repository"""
from app.utils.logging import get_logger
from typing import List, Optional

from sqlalchemy.orm import joinedload

from app.models.virtual_room import VirtualRoom, VirtualRoomMember
from app.persistence.base import SQLAlchemyRepository
from app.models.device import Device
from app.models.cabinet import Cabinet
from extensions import db

logger = get_logger(__name__)


class VirtualRoomRepository(SQLAlchemyRepository):
    """虚拟机房数据访问层"""

    def __init__(self, session=None):
        super().__init__(VirtualRoom, session or db.session)

    def find_with_members(self, virtual_room_id: int) -> Optional[VirtualRoom]:
        """查询虚拟机房详情（含成员列表 + 预加载防 N+1）

        members 使用 lazy="dynamic"，需手动查询并预加载关联。
        """
        vr = self.session.query(VirtualRoom).filter(VirtualRoom.id == virtual_room_id).first()
        if not vr:
            return None
        members = (
            self.session.query(VirtualRoomMember)
            .filter(VirtualRoomMember.virtual_room_id == virtual_room_id)
            .options(
                joinedload(VirtualRoomMember.device)
                .joinedload(Device.cabinet)
                .joinedload(Cabinet.room)
            )
            .all()
        )
        vr._preloaded_members = members
        return vr

    def get_member_device_ids(self, virtual_room_id: int) -> List[int]:
        """获取虚拟机房内所有交换机 device_id"""
        rows = (
            self.session.query(VirtualRoomMember.device_id)
            .filter(VirtualRoomMember.virtual_room_id == virtual_room_id)
            .all()
        )
        return [r[0] for r in rows]

    def set_members(self, virtual_room_id: int, device_ids: List[int]) -> None:
        """全量替换虚拟机房成员"""
        self.session.query(VirtualRoomMember).filter(
            VirtualRoomMember.virtual_room_id == virtual_room_id
        ).delete(synchronize_session=False)
        for did in device_ids:
            self.session.add(
                VirtualRoomMember(virtual_room_id=virtual_room_id, device_id=did)
            )
        self.session.flush()

    def get_covered_room_ids(self, virtual_room_id: int) -> set[int]:
        """获取虚拟机房涉及的机房ID集合"""
        rows = (
            self.session.query(Cabinet.room_id)
            .join(Device, Device.cabinet_id == Cabinet.id)
            .join(VirtualRoomMember, VirtualRoomMember.device_id == Device.id)
            .filter(
                VirtualRoomMember.virtual_room_id == virtual_room_id,
                Cabinet.deleted_at.is_(None),
            )
            .distinct()
            .all()
        )
        return {r[0] for r in rows if r[0] is not None}

    def find_by_device_id(self, device_id: int) -> List[VirtualRoom]:
        """查询包含指定交换机的所有虚拟机房"""
        return (
            self.session.query(VirtualRoom)
            .join(VirtualRoomMember, VirtualRoomMember.virtual_room_id == VirtualRoom.id)
            .filter(VirtualRoomMember.device_id == device_id)
            .all()
        )

    def update_last_scan(self, virtual_room_id: int, scope: str) -> None:
        """更新虚拟机房的最后扫描时间和范围

        Args:
            virtual_room_id: 虚拟机房ID
            scope: 扫描范围标识（如 "vr:123"）
        """
        from sqlalchemy import func
        vr = self.session.query(VirtualRoom).filter(VirtualRoom.id == virtual_room_id).first()
        if vr:
            vr.last_scan_at = func.now()
            vr.last_scan_scope = scope
            self.session.flush()
