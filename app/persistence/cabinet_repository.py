# -*- coding: utf-8 -*-
"""
机柜 Repository

唯一合法的机柜 DB 访问入口。Service 层禁止直接使用 db_manager 或裸 SQL。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional

from sqlalchemy import case, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, subqueryload

from app.exceptions.data_access import QueryExecutionError
from app.models.cabinet import Cabinet
from app.core.enums import CabinetStatus
from app.persistence.base import QueryOptimizationMixin, SQLAlchemyRepository

logger = get_logger(__name__)

_STATUS_LABELS: Dict[int, str] = {
    0: "禁用",
    1: "可用",
    2: "使用中",
    3: "维护中",
    4: "已预留",
}


class CabinetRepository(SQLAlchemyRepository, QueryOptimizationMixin):
    """机柜 Repository

    提供机柜全部数据访问方法。所有方法均通过 SQLAlchemy ORM，
    不包含任何裸 SQL，确保数据库方言无关性。
    """

    def __init__(self, session=None):
        super().__init__(Cabinet, session)

    def clear_customer(self, customer_id: int) -> int:
        """批量解绑客户名下所有机柜（customer_id 置 NULL）。

        注意：机柜下设备的 customer_id 由 DeviceRepository.clear_customer 统一解绑，
        本方法仅处理 Cabinet 表本身。

        Returns:
            int: 受影响行数
        """
        from extensions import db
        result = db.session.query(Cabinet).filter(
            Cabinet.customer_id == customer_id,
        ).update({Cabinet.customer_id: None}, synchronize_session=False)
        return result


    def find_by_id(self, entity_id: int) -> Optional[Cabinet]:
        """根据ID查找机柜，预加载 devices/room/customer 避免懒加载 N+1"""
        try:
            return (
                self._base_query()
                .options(
                    subqueryload(Cabinet.devices),
                    joinedload(Cabinet.room),
                    joinedload(Cabinet.customer),
                )
                .filter(Cabinet.id == entity_id)
                .first()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"根据ID查找机柜失败 (ID={entity_id}): {e}")
            raise QueryExecutionError(f"查找机柜失败", original_error=e)

    def find_by_cabinet_number(self, cabinet_number: str) -> Optional[Cabinet]:
        """根据机柜编号查找机柜。"""
        try:
            return (
                self._base_query()
                .filter(Cabinet.cabinet_number == cabinet_number)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"根据机柜编号查找失败 (cabinet_number={cabinet_number}): {e}")
            raise QueryExecutionError("查找机柜失败", original_error=e)


    def find_by_room_id(self, room_id: int) -> List[Cabinet]:
        """根据机房 ID 查找机柜，按编号排序。
        
        预加载 customer 关系，确保 to_dict() 能获取 customer_name。
        """
        try:
            from sqlalchemy.orm import joinedload
            
            return (
                self._base_query()
                .options(joinedload(Cabinet.customer))
                .filter(Cabinet.room_id == room_id)
                .order_by(Cabinet.cabinet_number)
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"根据机房ID查找机柜失败 (room_id={room_id}): {e}")
            raise QueryExecutionError("查找机柜失败", original_error=e)

    def find_all(self, filters: Optional[Dict[str, Any]] = None) -> List[Cabinet]:
        """获取满足过滤条件的机柜列表（不分页）。

        Args:
            filters: 精确匹配字段字典，例如 {"status": 1, "room_id": 3}
                     列表值自动使用 IN 查询，例如 {"status": [1, 2, 3]}
        """
        try:
            query = self._base_query()
            if filters:
                query = self._apply_filters(query, filters)
            return query.order_by(Cabinet.cabinet_number).all()
        except SQLAlchemyError as e:
            logger.error(f"查找机柜列表失败 (filters={filters}): {e}")
            raise QueryExecutionError("查找机柜列表失败", original_error=e)

    def find_available_cabinets(
        self, room_id: Optional[int] = None, min_available_u: int = 1,
        all_status: bool = False, statuses: Optional[List[int]] = None,
    ) -> List[Cabinet]:
        """查找可用机柜（默认status=1，且实际可用 U 位 >= min_available_u）。

        all_status=True 时不限制状态，用于筛选场景。
        statuses 优先级高于 all_status，指定允许的状态码列表。
        可用 U 位需遍历设备数据计算，在 Python 侧过滤。
        """
        try:
            query = self._base_query()
            if statuses:
                query = query.filter(Cabinet.status.in_(statuses))
            elif not all_status:
                query = query.filter(Cabinet.status == CabinetStatus.AVAILABLE)
            if room_id is not None:
                query = query.filter(Cabinet.room_id == room_id)
            return [c for c in query.all() if c.get_available_u_count() >= min_available_u]
        except SQLAlchemyError as e:
            logger.error(f"查找可用机柜失败: {e}")
            raise QueryExecutionError("查找可用机柜失败", original_error=e)

    def search(
        self,
        search_fields: List[str],
        keyword: Optional[str],
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """关键词多字段模糊搜索 + 精确过滤 + 分页。

        Args:
            search_fields: 参与模糊搜索的字段名，例如 ["cabinet_number", "location"]
            keyword: 搜索关键词（对各字段做 ILIKE %keyword%）
            filters: 精确匹配条件
            page: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            {"data": List[Cabinet], "total_count": int, "page": int,
             "page_size": int, "total_pages": int}
        """
        try:
            query = self._base_query()

            if filters:
                query = self._apply_filters(query, filters)

            if keyword and search_fields:
                conditions = [
                    getattr(Cabinet, f).ilike(f"%{keyword}%")
                    for f in search_fields
                    if hasattr(Cabinet, f)
                ]
                if conditions:
                    query = query.filter(or_(*conditions))

            total_count = query.count()
            offset = (page - 1) * page_size
            data = query.order_by(Cabinet.cabinet_number).offset(offset).limit(page_size).all()

            return {
                "data":        data,
                "total_count": total_count,
                "page":        page,
                "page_size":   page_size,
                "total_pages": max(1, (total_count + page_size - 1) // page_size),
            }
        except SQLAlchemyError as e:
            logger.error(f"搜索机柜失败 (keyword={keyword}): {e}")
            raise QueryExecutionError("搜索机柜失败", original_error=e)

    def paginate(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """通用分页查询。

        Returns:
            {"data": List[Cabinet], "total_count": int, "page": int,
             "page_size": int, "total_pages": int}
        """
        return self.search(
            search_fields=[],
            keyword=None,
            filters=filters,
            page=page,
            page_size=page_size,
        )


    def check_cabinet_number_exists(
        self, cabinet_number: str, exclude_id: Optional[int] = None
    ) -> bool:
        """检查机柜编号是否已存在（exclude_id 用于更新时跳过自身）。"""
        if not cabinet_number:
            return False
        try:
            query = self._base_query().filter(Cabinet.cabinet_number == cabinet_number)
            if exclude_id is not None:
                query = query.filter(Cabinet.id != exclude_id)
            return self.session.query(query.exists()).scalar()
        except SQLAlchemyError as e:
            logger.error(f"检查机柜编号存在性失败 (cabinet_number={cabinet_number}): {e}")
            raise QueryExecutionError("检查机柜编号存在性失败", original_error=e)

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """统计满足条件的机柜数量。"""
        try:
            query = self._base_query().with_entities(func.count(Cabinet.id))
            if filters:
                query = self._apply_filters(query, filters)
            return query.scalar() or 0
        except SQLAlchemyError as e:
            logger.error(f"统计机柜数量失败: {e}")
            raise QueryExecutionError("统计机柜数量失败", original_error=e)


    def get_cabinet_statistics(self) -> Dict[str, Any]:
        """获取机柜整体统计信息（全局汇总，单次 DB 往返）。

        修复：原代码使用 SQLAlchemy 1.x 的 case([(cond, val)], else_=...) 元组语法，
        在 SQLAlchemy 2.x 中已移除，改用关键字参数形式 case(value, whens) 或
        SQLAlchemy 1.4/2.0 兼容的 case((cond, val), else_=...) 位置参数形式。

        修复：原代码仅将 status!=1 的一律标记为"不可用"，
        现在使用完整的状态标签映射，保留 2/3/4 等状态的粒度。
        """
        try:
            basic = self._base_query().with_entities(
                func.count(Cabinet.id).label("total_cabinets"),
                func.sum(case((Cabinet.status == CabinetStatus.AVAILABLE, 1), else_=0)).label("available_cabinets"),
                func.sum(case((Cabinet.status == CabinetStatus.DISABLED, 1), else_=0)).label("disabled_cabinets"),
                func.sum(func.coalesce(Cabinet.total_u,    0)).label("total_u"),
                func.sum(func.coalesce(Cabinet.used_u,     0)).label("used_u"),
                func.sum(func.coalesce(Cabinet.total_power,0)).label("total_power"),
                func.sum(func.coalesce(Cabinet.used_power, 0)).label("used_power"),
            ).first()

            status_rows = (
                self._base_query().with_entities(Cabinet.status, func.count(Cabinet.id))
                .group_by(Cabinet.status)
                .all()
            )
            status_statistics = {
                _STATUS_LABELS.get(s, f"状态{s}"): cnt
                for s, cnt in status_rows
            }

            from app.models.room import Room

            room_rows = (
                self.session.query(Room.name, func.count(Cabinet.id).label("cnt"))
                .join(Cabinet, Room.id == Cabinet.room_id)
                .filter(Room.deleted_at.is_(None), Cabinet.deleted_at.is_(None))
                .group_by(Room.id, Room.name)
                .all()
            )
            room_statistics = {name: cnt for name, cnt in room_rows}

            total_u     = int(basic.total_u     or 0)
            used_u      = int(basic.used_u      or 0)
            total_power = float(basic.total_power or 0)
            used_power  = float(basic.used_power  or 0)

            return {
                "total_cabinets":     basic.total_cabinets     or 0,
                "available_cabinets": basic.available_cabinets or 0,
                "disabled_cabinets":  basic.disabled_cabinets  or 0,
                "status_statistics":  status_statistics,
                "room_statistics":    room_statistics,
                "u_statistics": {
                    "total_u":        total_u,
                    "used_u":         used_u,
                    "available_u":    total_u - used_u,
                    "utilization_rate": round(used_u / total_u * 100, 2) if total_u else 0,
                },
                "power_statistics": {
                    "total_power":    total_power,
                    "used_power":     used_power,
                    "available_power":total_power - used_power,
                    "utilization_rate": round(used_power / total_power * 100, 2) if total_power else 0,
                },
            }
        except SQLAlchemyError as e:
            logger.error(f"获取机柜统计信息失败: {e}")
            raise QueryExecutionError("获取机柜统计信息失败", original_error=e)

    def get_room_cabinet_statistics(self, room_id: int) -> Dict[str, Any]:
        """获取指定机房的机柜统计信息。

        Args:
            room_id: 机房ID

        Returns:
            {
                "cabinet_count": int,
                "available_cabinets": int,
                "total_u": int,
                "used_u": int,
                "power_statistics": {
                    "功率值(W)": int,  # 按实际功率值分组统计
                    ...
                }
            }
        """
        try:
            result = self._base_query().with_entities(
                func.count(Cabinet.id).label("cabinet_count"),
                func.sum(case((Cabinet.status == CabinetStatus.AVAILABLE, 1), else_=0)).label("available_cabinets"),
                func.sum(func.coalesce(Cabinet.total_u, 0)).label("total_u"),
                func.sum(func.coalesce(Cabinet.used_u, 0)).label("used_u"),
            ).filter(Cabinet.room_id == room_id).first()

            power_stats = self._base_query().with_entities(
                Cabinet.total_power,
                func.count(Cabinet.id).label("count")
            ).filter(
                Cabinet.room_id == room_id,
                Cabinet.total_power.isnot(None)
            ).group_by(Cabinet.total_power).all()

            power_statistics = {}
            for stat in power_stats:
                power_key = f"{int(stat.total_power)}W"
                power_statistics[power_key] = stat.count

            return {
                "cabinet_count": result.cabinet_count or 0,
                "available_cabinets": result.available_cabinets or 0,
                "total_u": int(result.total_u or 0),
                "used_u": int(result.used_u or 0),
                "power_statistics": power_statistics,
            }
        except SQLAlchemyError as e:
            logger.error(f"获取机房机柜统计失败 (room_id={room_id}): {e}")
            raise QueryExecutionError("获取机房机柜统计失败", original_error=e)
