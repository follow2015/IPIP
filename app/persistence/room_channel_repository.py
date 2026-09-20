# -*- coding: utf-8 -*-
"""
机房通道 Repository 实现

通道的增删改走基类的通用 CRUD，本类只提供机房维度的查询与唯一键反查。
"""
from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.data_access import QueryExecutionError
from app.models.room_channel import RoomChannel
from app.persistence.base import QueryOptimizationMixin, SQLAlchemyRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)


class RoomChannelRepository(SQLAlchemyRepository, QueryOptimizationMixin):
    """机房通道 Repository"""

    def __init__(self, session=None):
        super().__init__(RoomChannel, session)

    def find_by_room_id(self, room_id: int) -> List[RoomChannel]:
        """按机房查询全部通道（按列号升序，列表式配置弹窗可直接使用）

        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            return (
                self._base_query()
                .filter(RoomChannel.room_id == room_id)
                .order_by(RoomChannel.col_number)
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"查询机房通道失败 (room_id={room_id}): {e}")
            raise QueryExecutionError("查询机房通道失败", original_error=e)

    def find_by_room_and_col(self, room_id: int, col_number: int) -> Optional[RoomChannel]:
        """按机房 + 列号反查单条通道（唯一键 `uk_room_col_channel` 的定位查询）

        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            return (
                self._base_query()
                .filter(RoomChannel.room_id == room_id, RoomChannel.col_number == col_number)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"定位机房通道失败 (room_id={room_id}, col={col_number}): {e}")
            raise QueryExecutionError("定位机房通道失败", original_error=e)

    def delete_by_room_id(self, room_id: int) -> int:
        """删除某机房的全部通道，返回删除条数。

        供 Room 物理删除前清理依赖使用（Room 为物理删除，且外键未设
        ON DELETE CASCADE，故必须在应用层先清理，见设计文档 §2.1/§8 #9）。

        Raises:
            QueryExecutionError: 删除执行失败
        """
        try:
            deleted = self._base_query().filter(RoomChannel.room_id == room_id).delete(
                synchronize_session=False
            )
            return int(deleted or 0)
        except SQLAlchemyError as e:
            logger.error(f"清理机房通道失败 (room_id={room_id}): {e}")
            raise QueryExecutionError("清理机房通道失败", original_error=e)
