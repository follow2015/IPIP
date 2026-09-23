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

    def update_versioned(
        self, marker_id: int, room_id: int, expected_version: int,
        fields: dict,
    ) -> bool:
        """乐观锁 CAS 更新（WP-7：消 lost-update）

        版本判据放在 **UPDATE 谓词内**而不是"先 SELECT 再比较"——MySQL
        REPEATABLE READ 下事务先读到的快照可能已过期，先读后比会被骗过；
        谓词内判定由当前行版本兜底，rowcount 即裁决。

        Returns:
            bool: True=命中（1 行被更新）；False=未命中（不存在或版本过期，
            由调用方重读区分两种情形）。

        Raises:
            QueryExecutionError: SQL 执行失败（含唯一键竞态，由上层还原 409）
        """
        from sqlalchemy import update

        stmt = (
            update(RoomLayoutMarker)
            .where(
                RoomLayoutMarker.id == marker_id,
                RoomLayoutMarker.room_id == room_id,
                RoomLayoutMarker.version == expected_version,
            )
            .values(**fields, version=expected_version + 1)
            .execution_options(synchronize_session=False)
        )
        try:
            result = self.session.execute(stmt)
            self.session.expire_all()
            return result.rowcount == 1
        except SQLAlchemyError as e:
            logger.error(
                f"乐观锁更新占位标记失败 (id={marker_id}, expected_v={expected_version}): {e}"
            )
            raise QueryExecutionError("乐观锁更新占位标记失败", original_error=e)

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
