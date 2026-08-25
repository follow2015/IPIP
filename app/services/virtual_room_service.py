
"""虚拟机房服务模块"""
from app.utils.logging import get_logger
from typing import Dict, List, Optional, Tuple

from app.exceptions.validation import ValidationError
from app.persistence.virtual_room_repository import VirtualRoomRepository
from app.models.virtual_room import VirtualRoom
from app.services.switch_events import emit_resource_change_global

logger = get_logger(__name__)


class VirtualRoomService:

    def __init__(self, repo: VirtualRoomRepository):
        self.repo = repo

    def get_all(self) -> List[VirtualRoom]:
        return self.repo.find_all(order_by="name")

    def get_by_id(self, virtual_room_id: int) -> Optional[VirtualRoom]:
        return self.repo.find_with_members(virtual_room_id)

    def get_paginated(
        self, page: int = 1, per_page: int = 20, **filters
    ) -> Tuple[List[dict], int]:
        result = self.repo.paginate(
            page=page, page_size=per_page, filters=filters, order_by="name"
        )
        items = [item.to_dict(include_relations=False) for item in result.get("data", [])]
        return items, result.get("total_count", 0)

    def create(self, data: Dict) -> VirtualRoom:
        name = data.get("name", "").strip()
        if not name:
            raise ValidationError("虚拟机房名称不能为空")

        existing = self.repo.find_one({"name": name})
        if existing:
            raise ValidationError(f"虚拟机房 '{name}' 已存在")

        device_ids = data.get("device_ids", [])

        vr = self.repo.create({"name": name, "description": data.get("description", "")})
        if device_ids:
            self.repo.set_members(vr.id, device_ids)
        emit_resource_change_global("virtual_room", "create", ids=[vr.id])
        return self.repo.find_with_members(vr.id)

    def update(self, virtual_room_id: int, data: Dict) -> VirtualRoom:
        vr = self.repo.find_with_members(virtual_room_id)
        if not vr:
            raise ValidationError("虚拟机房不存在")

        name = data.get("name")
        if name is not None:
            name = name.strip()
            if not name:
                raise ValidationError("虚拟机房名称不能为空")
            existing = self.repo.find_one({"name": name})
            if existing and existing.id != virtual_room_id:
                raise ValidationError(f"虚拟机房 '{name}' 已存在")

        update_data = {}
        if name is not None:
            update_data["name"] = name
        if "description" in data:
            update_data["description"] = data["description"]

        if update_data:
            self.repo.update(virtual_room_id, update_data)
        emit_resource_change_global("virtual_room", "update", ids=[virtual_room_id])
        return self.repo.find_with_members(virtual_room_id)

    def update_members(self, virtual_room_id: int, device_ids: List[int]) -> VirtualRoom:
        vr = self.repo.find_by_id(virtual_room_id)
        if not vr:
            raise ValidationError("虚拟机房不存在")

        if not device_ids:
            raise ValidationError("虚拟机房必须包含至少一台交换机")

        self.repo.set_members(virtual_room_id, device_ids)
        emit_resource_change_global("virtual_room", "update", ids=[virtual_room_id])
        return self.repo.find_with_members(virtual_room_id)

    def delete(self, virtual_room_id: int) -> bool:
        vr = self.repo.find_by_id(virtual_room_id)
        if not vr:
            raise ValidationError("虚拟机房不存在")
        result = self.repo.delete(virtual_room_id)
        if result:
            emit_resource_change_global("virtual_room", "delete", ids=[virtual_room_id])
        return result

    def get_member_device_ids(self, virtual_room_id: int) -> List[int]:
        return self.repo.get_member_device_ids(virtual_room_id)

    def get_covered_room_ids(self, virtual_room_id: int) -> set[int]:
        return self.repo.get_covered_room_ids(virtual_room_id)
