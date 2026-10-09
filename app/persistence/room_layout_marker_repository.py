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
            raise QueryExecutionError("查询机房占位标记失败", original_error=e) from e

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
            raise QueryExecutionError("定位机房占位标记失败", original_error=e) from e

    def find_by_ids_in_room(self, ids, room_id: int) -> List[RoomLayoutMarker]:
        """批量存在性预查：一次 IN 把本批 id 查完（评审 20260924 §2.2）。

        批量编辑在循环里逐条 ``find_by_id`` 就是 N 次 SELECT —— 与 WP-9a
        「N+1 批量化」的口径正好相反，等于在"消 N+1"的同一批改动里又引入了一处。
        本方法一次查完，调用方按 id 建索引即可。

        刻意**不带**任何预加载：这里只服务"该 id 存在且属于本机房"的判定与
        version 读取，批量场景下把关联一起拉出来才是真正的放大。

        Args:
            ids: 标记 id 集合（本批）
            room_id: 机房 ID（过滤后调用方无需再逐个校验归属）

        Raises:
            QueryExecutionError: 查询执行失败
        """
        if not ids:
            return []
        try:
            return (
                self._base_query()
                .filter(
                    RoomLayoutMarker.id.in_(list(ids)),
                    RoomLayoutMarker.room_id == room_id,
                )
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"批量预查占位标记失败 (room_id={room_id}, n={len(ids)}): {e}")
            raise QueryExecutionError("批量预查占位标记失败", original_error=e) from e

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
            self.expire_instance(marker_id)
            return result.rowcount == 1
        except SQLAlchemyError as e:
            logger.error(
                f"乐观锁更新占位标记失败 (id={marker_id}, expected_v={expected_version}): {e}"
            )
            raise QueryExecutionError("乐观锁更新占位标记失败", original_error=e) from e

    def set_position(self, marker_id: int, room_id: int,
                     row_number: int, col_number: int) -> bool:
        """只改坐标的单条 UPDATE（**不递增 version**）

        供批量编辑的坐标两阶段搬迁使用：`uk_marker_position` 唯一键在 MySQL 下
        即时检查、不可延迟，交换/轮换位置时若直接把 A 更新到 B 当前所在格（B
        尚未让出）会当场违反约束。搬迁被拆成"先挪哨兵格 → 再落最终坐标"两步，
        每一步都调用本方法；version 的递增与 CAS 判据统一由 `update_versioned`
        负责，本方法不再动它，避免一次编辑把版本号加了两次。

        Returns:
            bool: True=命中 1 行；False=标记不存在或不属于该机房

        Raises:
            QueryExecutionError: SQL 执行失败（含唯一键冲突，由上层还原 409）
        """
        from sqlalchemy import update

        stmt = (
            update(RoomLayoutMarker)
            .where(
                RoomLayoutMarker.id == marker_id,
                RoomLayoutMarker.room_id == room_id,
            )
            .values(row_number=row_number, col_number=col_number)
            .execution_options(synchronize_session=False)
        )
        try:
            result = self.session.execute(stmt)
            self.expire_instance(marker_id)
            return result.rowcount == 1
        except SQLAlchemyError as e:
            logger.error(
                f"搬迁占位标记坐标失败 (id={marker_id}, pos=({row_number},{col_number})): {e}"
            )
            raise QueryExecutionError("搬迁占位标记坐标失败", original_error=e) from e

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
            raise QueryExecutionError("清理机房占位标记失败", original_error=e) from e
