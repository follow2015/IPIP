# -*- coding: utf-8 -*-
"""
机房服务模块

提供机房管理的全部业务逻辑，通过 Repository 访问数据，不直接操作 ORM/DB。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional, Tuple

from app.exceptions.validation import ValidationError
from app.persistence.room_repository import RoomRepository
from app.persistence.cabinet_repository import CabinetRepository
from app.persistence.device_repository import DeviceRepository
from app.models.room import Room
from app.services.switch_events import emit_resource_change_global
from app.utils.cache import cache_manager

logger = get_logger(__name__)

ROOM_CACHE_TTL = 3600  # 机房基础信息缓存时间（秒）
ROOM_SHORT_CACHE_TTL = 600  # 机房统计信息缓存时间（秒）


class RoomService:
    """机房服务

    所有业务逻辑入口，统一通过 RoomRepository 访问数据库。
    对外只暴露一套 CRUD 接口，旧的双份方法已合并删除。
    """

    def __init__(self, room_repository: RoomRepository,
                 cabinet_repository: CabinetRepository,
                 device_repository: DeviceRepository):
        self.room_repository = room_repository
        self.cabinet_repository = cabinet_repository
        self.device_repository = device_repository


    def get_all_rooms(self) -> List[Dict[str, Any]]:
        """获取所有正常状态机房列表（带缓存）

        返回字典列表而非 ORM 对象，因为 Redis 缓存反序列化后无法还原 ORM 对象。
        """
        return cache_manager.get_or_set(
            "room:list:all",
            lambda: [r.to_dict() for r in self.room_repository.find_all(filters={"status": 0}, order_by="name")],
            ttl=ROOM_CACHE_TTL,
        )

    def get_by_id(self, room_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取机房（含停用状态，供存在性检查用，带缓存）

        返回字典而非 ORM 对象，因为 Redis 缓存反序列化后无法还原 ORM 对象。
        """
        room = self.room_repository.find_by_id(room_id)
        return cache_manager.get_or_set(
            f"room:{room_id}",
            lambda: room.to_dict() if room else None,
            ttl=ROOM_CACHE_TTL,
        )

    def get_active_by_id(self, room_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取正常状态的机房（带缓存）

        返回字典而非 ORM 对象，因为 Redis 缓存反序列化后无法还原 ORM 对象。
        """
        room = self.room_repository.find_one({"id": room_id, "status": 0})
        return cache_manager.get_or_set(
            f"room:active:{room_id}",
            lambda: room.to_dict() if room else None,
            ttl=ROOM_CACHE_TTL,
        )

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取正常状态的机房（带缓存）

        返回字典而非 ORM 对象，因为 Redis 缓存反序列化后无法还原 ORM 对象。
        """
        room = self.room_repository.find_one({"name": name, "status": 0})
        return cache_manager.get_or_set(
            f"room:name:{name}",
            lambda: room.to_dict() if room else None,
            ttl=ROOM_CACHE_TTL,
        )

    def get_paginated(
        self,
        page: int = 1,
        per_page: int = 20,
        filters: Optional[Dict] = None,
    ) -> Tuple[List[Room], int]:
        """分页获取机房列表

        Returns:
            (机房列表, 总数)
        """
        result = self.room_repository.paginate(
            filters=filters or {},
            page=page,
            page_size=per_page,
        )
        return result.get("data", []), result.get("total_count", 0)

    def search_rooms(self, keyword: str) -> List[Room]:
        """按关键词搜索机房（匹配名称或位置）"""
        result = self.room_repository.search(
            search_fields=["name", "location"],
            keyword=keyword,
            filters={"status": 0},
        )
        return result.get("data", [])

    def get_room_with_stats(self, room_id: int) -> Optional[Dict[str, Any]]:
        """获取机房详情 + 统计信息（机柜数、交换机数，带缓存）"""
        return cache_manager.get_or_set(
            f"room:stats:{room_id}",
            lambda: self._load_room_with_stats(room_id),
            ttl=ROOM_SHORT_CACHE_TTL,
        )

    def _load_room_with_stats(self, room_id: int) -> Optional[Dict[str, Any]]:
        """从数据库加载机房详情+统计（内部方法）"""
        room = self.room_repository.find_one({"id": room_id, "status": 0})
        if not room:
            return None

        room_dict = room.to_dict()
        room_dict.update(self.room_repository.get_room_statistics(room_id))
        return room_dict

    def get_cabinets(self, room_id: int) -> List:
        """获取机房下的所有机柜"""
        return self.cabinet_repository.find_by_room_id(room_id)

    def get_statistics(self, room_id: int) -> Dict[str, Any]:
        """获取机房详细统计信息（机柜、设备、U 位等，带缓存）"""
        return cache_manager.get_or_set(
            f"room:detail_stats:{room_id}",
            lambda: self._load_statistics(room_id),
            ttl=ROOM_SHORT_CACHE_TTL,
        )

    def _load_statistics(self, room_id: int) -> Dict[str, Any]:
        """从数据库加载机房详细统计（内部方法）"""
        cabinet_stats = self.cabinet_repository.get_room_cabinet_statistics(room_id)

        device_stats = self.device_repository.get_room_device_statistics(room_id)

        total_u = cabinet_stats["total_u"]
        used_u = device_stats["used_u"]

        return {
            "cabinet_count": cabinet_stats["cabinet_count"],
            "device_count": device_stats["device_count"],
            "available_cabinets": cabinet_stats["available_cabinets"],
            "used_u": used_u,
            "total_u": total_u,
            "u_utilization": round(used_u / total_u * 100, 2) if total_u > 0 else 0,
            "power_statistics": cabinet_stats.get("power_statistics", {}),
            "type_statistics": device_stats.get("type_statistics", {}),
            "type_u_statistics": device_stats.get("type_u_statistics", {}),
        }


    def create(self, data: Dict[str, Any]) -> Room:
        """创建机房

        Args:
            data: 机房字段字典（必须包含 name）

        Raises:
            ValidationError: 名称为空或已存在
        """
        name = (data.get("name") or "").strip()
        if not name:
            raise ValidationError("机房名称不能为空")

        if self.room_repository.check_room_name_exists(name):
            raise ValidationError("机房名称已存在")

        data.setdefault("status", 0)
        room = self.room_repository.create(data)
        self.room_repository.session.flush()
        logger.info(f"创建机房成功: {name} (ID: {room.id})")
        return room

    def update(self, room_id: int, data: Dict[str, Any]) -> Room:
        """更新机房信息

        Raises:
            ValidationError: 机房不存在或名称冲突
        """
        if not self.room_repository.exists({"id": room_id}):
            raise ValidationError("机房不存在")

        new_name = (data.get("name") or "").strip()
        if new_name and self.room_repository.check_room_name_exists(new_name, exclude_id=room_id):
            raise ValidationError("机房名称已存在")

        room = self.room_repository.update(room_id, data)
        self.room_repository.session.flush()
        logger.info(f"更新机房成功 (ID: {room_id})")
        return room

    def delete(self, room_id: int) -> bool:
        """删除机房（软删除）

        Raises:
            ValidationError: 机房不存在或存在关联交换机/机柜
        """
        if not self.room_repository.find_by_id(room_id):
            raise ValidationError("机房不存在")

        deps = self.room_repository.check_room_dependencies(room_id)
        if deps["switch_count"] > 0:
            raise ValidationError("该机房下有交换机，无法删除")
        if deps["cabinet_count"] > 0:
            raise ValidationError("该机房下有机柜，无法删除")

        result = self.room_repository.delete(room_id)
        if result:
            self.room_repository.session.flush()
        logger.info(f"删除机房成功 (ID: {room_id})")
        return result
