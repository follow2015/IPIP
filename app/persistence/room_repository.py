# -*- coding: utf-8 -*-
"""
机房 Repository 实现

提供机房相关的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.data_access import QueryExecutionError
from app.persistence.base import QueryOptimizationMixin, SQLAlchemyRepository
from app.models.room import Room
from app.core.enums import RoomStatus

logger = get_logger(__name__)


class RoomRepository(SQLAlchemyRepository, QueryOptimizationMixin):
    """机房 Repository

    提供机房相关的数据访问方法，包括查询、创建、更新、删除等操作。
    """

    def __init__(self, session=None):
        super().__init__(Room, session)


    def list_all_ordered_by_id(self) -> List[Room]:
        """全部机房，按 ID 升序（B-44 部署计划批：逐机房出报告的**稳定顺序**）。"""
        return self.session.query(Room).order_by(Room.id).all()

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

    def find_by_name_like(self, pattern: str) -> List[Room]:
        """按名称 ilike 匹配机房（B-44 收敛：AI 机房名解析的模糊匹配）

        ``pattern`` 由调用方构造（是否含 ``%`` 通配符决定"精确大小写不敏感"还是
        "contains"语义）—— 与调用方的两处既有用法一一对应，故不在仓储内再包一层。

        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            return self._base_query().filter(Room.name.ilike(pattern)).all()
        except SQLAlchemyError as e:
            logger.error(f"模糊匹配机房失败 (pattern={pattern}): {e}")
            raise QueryExecutionError("查找机房失败", original_error=e)

    def exists_alive(self, room_id: int) -> bool:
        """机房是否存在（B-44 收敛：扫描调度的配置校验）。

        ⚠️ **修正了一处潜伏错误**：原实现写 ``filter_by(id, deleted_at=None)``，
        但 ``rooms`` 表**没有 deleted_at 列** —— 该行一旦真实执行即抛
        ``InvalidRequestError``（此前从未触达：配置了 room_ids 的部署才会走到）。
        迁移时按"存在即有效"修正；Room 的退役语义走 ``status`` 列，
        如需排除退役机房应显式按 status 过滤（勿再引用不存在的列）。
        """
        return (
            self.session.query(Room)
            .filter_by(id=room_id)
            .first()
            is not None
        )

    def check_room_name_exists(self, room_name: str, exclude_id: Optional[int] = None) -> bool:
        """检查机房名称是否已存在（排除已软删除的机房）

        .. deprecated:: 名称已放开为分组键（可重复），本方法不再被查重使用，
            保留备查；组合唯一见 `check_room_number_exists`。

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

    def check_room_number_exists(
        self, name: str, room_number: str, exclude_id: Optional[int] = None
    ) -> bool:
        """检查（机房名称, 房间号）组合是否已存在（唯一键 uk_room_name_number 的应用层前置）

        名称已放开为分组键（可重复），同一名称组内房间号必须唯一——
        组合查重给出可读的 409，数据库唯一约束只做并发兜底。

        Raises:
            QueryExecutionError: 查询执行失败
        """
        if not room_number or not name:
            return False

        try:
            query = self._base_query().filter(
                Room.name == name,
                Room.room_number == room_number,
            )
            if exclude_id is not None:
                query = query.filter(Room.id != exclude_id)

            return self.session.query(query.exists()).scalar()
        except SQLAlchemyError as e:
            logger.error(f"检查房间号存在性失败 (name={name}, room_number={room_number}): {e}")
            raise QueryExecutionError("检查房间号存在性失败", original_error=e)

    def find_name_options(self) -> List[Dict[str, Any]]:
        """机房名称联想选项：[{name, room_count}]（按名称分组计数，升序）

        供表单强联想使用（实施计划 D3）：前端据此提示"将并入「X」机房组（现有 N 条记录）"。
        """
        try:
            rows = (
                self._base_query()
                .with_entities(Room.name, func.count(Room.id))
                .group_by(Room.name)
                .order_by(Room.name)
                .all()
            )
            return [{"name": name, "room_count": count} for name, count in rows]
        except SQLAlchemyError as e:
            logger.error(f"查询机房名称联想选项失败: {e}")
            raise QueryExecutionError("查询机房名称联想选项失败", original_error=e)


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
                .filter(Cabinet.room_id == room_id)
                .scalar()
                or 0
            )

            return {"switch_count": switch_count, "cabinet_count": cabinet_count}
        except SQLAlchemyError as e:
            logger.error(f"检查机房依赖关系失败 (room_id={room_id}): {e}")
            raise QueryExecutionError("检查机房依赖关系失败", original_error=e)

    def find_distinct_buildings(self) -> List[str]:
        """已使用的 building 去重值（升序，排除空值）。

        供机房表单的联想选项使用（设计文档 §2.4）：不限定枚举，运维可自由新增楼栋名。
        """
        try:
            rows = (
                self._base_query()
                .with_entities(Room.building)
                .filter(Room.building.isnot(None), Room.building != "")
                .distinct()
                .order_by(Room.building)
                .all()
            )
            return [row[0] for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"查询楼栋去重值失败: {e}")
            raise QueryExecutionError("查询楼栋失败", original_error=e)

    def find_distinct_floors(self, building: Optional[str] = None) -> List[str]:
        """已使用的 floor 去重值（升序，排除空值）。

        供机房表单的联想选项与总览页的楼层筛选使用。

        Args:
            building: 指定时只返回该楼栋下出现过的楼层。**联动是必需的而非优化**：
                不限定楼栋时，A 栋与 B 栋各自的"3层"会混在同一个下拉里，
                用户选"3层"分不清是哪一栋的。
        """
        try:
            query = (
                self._base_query()
                .with_entities(Room.floor)
                .filter(Room.floor.isnot(None), Room.floor != "")
            )
            if building:
                query = query.filter(Room.building == building)
            rows = query.distinct().order_by(Room.floor).all()
            return [row[0] for row in rows]
        except SQLAlchemyError as e:
            logger.error(f"查询楼层去重值失败: {e}")
            raise QueryExecutionError("查询楼层失败", original_error=e)

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
            from app.models.device import Device  # 避免循环导入
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
                .filter(Cabinet.room_id.isnot(None))
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
                .filter(Cabinet.room_id.isnot(None))
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
