
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

    def __init__(self, session=None):
        super().__init__(VirtualRoom, session or db.session)

    def find_with_members(self, virtual_room_id: int) -> Optional[VirtualRoom]:
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
        rows = (
            self.session.query(VirtualRoomMember.device_id)
            .filter(VirtualRoomMember.virtual_room_id == virtual_room_id)
            .all()
        )
        return [r[0] for r in rows]

    def set_members(self, virtual_room_id: int, device_ids: List[int]) -> None:
        self.session.query(VirtualRoomMember).filter(
            VirtualRoomMember.virtual_room_id == virtual_room_id
        ).delete(synchronize_session=False)
        for did in device_ids:
            self.session.add(
                VirtualRoomMember(virtual_room_id=virtual_room_id, device_id=did)
            )
        self.session.flush()

    def get_covered_room_ids(self, virtual_room_id: int) -> set[int]:
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
        return (
            self.session.query(VirtualRoom)
            .join(VirtualRoomMember, VirtualRoomMember.virtual_room_id == VirtualRoom.id)
            .filter(VirtualRoomMember.device_id == device_id)
            .all()
        )

    def update_last_scan(self, virtual_room_id: int, scope: str) -> None:
        from sqlalchemy import func
        vr = self.session.query(VirtualRoom).filter(VirtualRoom.id == virtual_room_id).first()
        if vr:
            vr.last_scan_at = func.now()
            vr.last_scan_scope = scope
            self.session.flush()
