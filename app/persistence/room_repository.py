# -*- coding: utf-8 -*-
"""
机房 Repository 实现

提供机房相关的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.data_access import QueryExecutionError
from app.persistence.base import QueryOptimizationMixin, SQLAlchemyRepository
from app.models.room import Room
from app.core.enums import CabinetStatus, RoomStatus

logger = get_logger(__name__)


class RoomRepository(SQLAlchemyRepository, QueryOptimizationMixin):
    """机房 Repository

    提供机房相关的数据访问方法，包括查询、创建、更新、删除等操作。
    """

    def __init__(self, session=None):
        super().__init__(Room, session)


    def find_by_room_name(self, room_name: str) -> Optional[Room]:
        """根据机房名称查找机房（不过滤状态，供内部使用）

        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            return self._base_query().filter(Room.name == room_name).first()
        except SQLAlchemyError as e:
            logger.error(f"根据机房名称查找机房失败 (room_name={room_name}): {e}")
            raise QueryExecutionError("查找机房失败", original_error=e)

    def check_room_name_exists(self, room_name: str, exclude_id: Optional[int] = None) -> bool:
        """检查机房名称是否已存在（排除已软删除的机房）

        Args:
            room_name: 机房名称
            exclude_id: 排除的机房 ID（用于更新时去重）

        Raises:
            QueryExecutionError: 查询执行失败
        """
        if not room_name:
            return False

        try:
            query = self._base_query().filter(
                Room.name == room_name,
            )
            if exclude_id is not None:
                query = query.filter(Room.id != exclude_id)

            return self.session.query(query.exists()).scalar()
        except SQLAlchemyError as e:
            logger.error(f"检查机房名称存在性失败 (room_name={room_name}): {e}")
            raise QueryExecutionError("检查机房名称存在性失败", original_error=e)


    def check_room_dependencies(self, room_id: int) -> Dict[str, int]:
        """检查机房的依赖关系（交换机数量 + 机柜数量）

        Returns:
            {"switch_count": int, "cabinet_count": int}

        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            from app.models.switch_credentials import SwitchCredentials  # 避免循环导入
            from app.models.cabinet import Cabinet  # 避免循环导入
            from app.models.device import Device  # 避免循环导入

            from app.models.device_switch_ext import DeviceSwitchExt
            switch_count = (
                self.session.query(func.count(SwitchCredentials.id))
                .join(Device, SwitchCredentials.device_id == Device.id)
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .join(DeviceSwitchExt, DeviceSwitchExt.device_id == Device.id)
                .filter(Cabinet.room_id == room_id, DeviceSwitchExt.switch_role.in_([0, 1]))
                .scalar()
                or 0
            )

            cabinet_count = (
                self.session.query(func.count(Cabinet.id))
                .filter(Cabinet.room_id == room_id, Cabinet.status == CabinetStatus.DISABLED)
                .scalar()
                or 0
            )

            return {"switch_count": switch_count, "cabinet_count": cabinet_count}
        except SQLAlchemyError as e:
            logger.error(f"检查机房依赖关系失败 (room_id={room_id}): {e}")
            raise QueryExecutionError("检查机房依赖关系失败", original_error=e)

    def get_room_statistics(self, room_id: int) -> Dict[str, int]:
        """获取单个机房统计信息（机柜数 + 交换机数）

        Raises:
            QueryExecutionError: 查询执行失败
        """
        return self.check_room_dependencies(room_id)

    def get_all_room_statistics(self) -> Dict[str, Any]:
        """获取所有机房的汇总统计信息

        Returns:
            {
                "total_rooms": int,
                "rooms_with_cabinets": int,
                "rooms_with_switches": int,
                "empty_rooms": int,         # 既无机柜也无交换机的机房数
                "status_statistics": dict,
            }

        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            from app.models.cabinet import Cabinet  # 避免循环导入
            from app.models.switch_credentials import SwitchCredentials  # 避免循环导入

            total_rooms: int = self.count({"status": RoomStatus.NORMAL})

            status_stats = (
                self._base_query().with_entities(Room.status, func.count(Room.id))
                .group_by(Room.status)
                .all()
            )
            status_statistics = {
                ("活跃" if status == RoomStatus.NORMAL else "非活跃"): count
                for status, count in status_stats
            }

            rooms_with_cabinets: int = (
                self.session.query(func.count(func.distinct(Cabinet.room_id)))
                .filter(Cabinet.room_id.isnot(None), Cabinet.status == CabinetStatus.DISABLED, Cabinet.deleted_at.is_(None))
                .scalar()
                or 0
            )

            from app.models.device_switch_ext import DeviceSwitchExt
            rooms_with_switches: int = (
                self.session.query(func.count(func.distinct(Cabinet.room_id)))
                .join(Device, Device.cabinet_id == Cabinet.id)
                .join(SwitchCredentials, SwitchCredentials.device_id == Device.id)
                .join(DeviceSwitchExt, DeviceSwitchExt.device_id == Device.id)
                .filter(Cabinet.room_id.isnot(None), DeviceSwitchExt.switch_role.in_([0, 1]))
                .scalar()
                or 0
            )

            from sqlalchemy import select as sa_select, union

            has_cabinet_sq = (
                self.session.query(Cabinet.room_id)
                .filter(Cabinet.room_id.isnot(None), Cabinet.status == CabinetStatus.DISABLED, Cabinet.deleted_at.is_(None))
                .distinct()
                .subquery()
            )
            has_switch_sq = (
                self.session.query(Cabinet.room_id)
                .join(Device, Device.cabinet_id == Cabinet.id)
                .join(SwitchCredentials, SwitchCredentials.device_id == Device.id)
                .join(DeviceSwitchExt, DeviceSwitchExt.device_id == Device.id)
                .filter(Cabinet.room_id.isnot(None), DeviceSwitchExt.switch_role.in_([0, 1]))
                .distinct()
                .subquery()
            )
            rooms_with_any: int = self.session.execute(
                sa_select(func.count()).select_from(
                    union(
                        sa_select(has_cabinet_sq.c.room_id),
                        sa_select(has_switch_sq.c.room_id),
                    ).subquery()
                )
            ).scalar() or 0
            empty_rooms = max(total_rooms - rooms_with_any, 0)

            return {
                "total_rooms": total_rooms,
                "rooms_with_cabinets": rooms_with_cabinets,
                "rooms_with_switches": rooms_with_switches,
                "empty_rooms": empty_rooms,
                "status_statistics": status_statistics,
            }
        except SQLAlchemyError as e:
            logger.error(f"获取机房汇总统计信息失败: {e}")
            raise QueryExecutionError("获取机房汇总统计信息失败", original_error=e)
