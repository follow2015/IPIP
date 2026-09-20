# -*- coding: utf-8 -*-
"""
机房平面图占位标记 Repository 实现

标记的增删改走基类的通用 CRUD，本类只提供机房维度的查询与唯一键反查。
"""
from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.data_access import QueryExecutionError
from app.models.room_layout_marker import RoomLayoutMarker
from app.persistence.base import QueryOptimizationMixin, SQLAlchemyRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)


class RoomLayoutMarkerRepository(SQLAlchemyRepository, QueryOptimizationMixin):
    """机房平面图占位标记 Repository"""

    def __init__(self, session=None):
        super().__init__(RoomLayoutMarker, session)

    def find_by_room_id(self, room_id: int) -> List[RoomLayoutMarker]:
        """按机房查询全部占位标记（按行列升序，与网格渲染顺序一致）

        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            return (
                self._base_query()
                .filter(RoomLayoutMarker.room_id == room_id)
                .order_by(RoomLayoutMarker.row_number, RoomLayoutMarker.col_number)
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"查询机房占位标记失败 (room_id={room_id}): {e}")
            raise QueryExecutionError("查询机房占位标记失败", original_error=e)

    def find_by_position(
        self, room_id: int, row_number: int, col_number: int
    ) -> Optional[RoomLayoutMarker]:
        """按机房 + 行列反查单条标记（唯一键 `uk_marker_position` 的定位查询）

        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            return (
                self._base_query()
                .filter(
                    RoomLayoutMarker.room_id == room_id,
                    RoomLayoutMarker.row_number == row_number,
                    RoomLayoutMarker.col_number == col_number,
                )
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(
                f"定位机房占位标记失败 (room_id={room_id}, pos=({row_number},{col_number})): {e}"
            )
            raise QueryExecutionError("定位机房占位标记失败", original_error=e)

    def delete_by_room_id(self, room_id: int) -> int:
        """删除某机房的全部占位标记，返回删除条数。

        供 Room 物理删除前清理依赖使用（同通道表：外键未设 ON DELETE CASCADE，
        必须在应用层先清理）。

        Raises:
            QueryExecutionError: 删除执行失败
        """
        try:
            deleted = self._base_query().filter(RoomLayoutMarker.room_id == room_id).delete(
                synchronize_session=False
            )
            return int(deleted or 0)
        except SQLAlchemyError as e:
            logger.error(f"清理机房占位标记失败 (room_id={room_id}): {e}")
            raise QueryExecutionError("清理机房占位标记失败", original_error=e)
