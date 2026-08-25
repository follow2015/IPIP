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

    def __init__(self, session=None):
        super().__init__(Cabinet, session)

    def clear_customer(self, customer_id: int) -> int:
        from extensions import db
        result = db.session.query(Cabinet).filter(
            Cabinet.customer_id == customer_id,
        ).update({Cabinet.customer_id: None}, synchronize_session=False)
        return result


    def find_by_id(self, entity_id: int) -> Optional[Cabinet]:
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
        try:
            query = self._base_query().with_entities(func.count(Cabinet.id))
            if filters:
                query = self._apply_filters(query, filters)
            return query.scalar() or 0
        except SQLAlchemyError as e:
            logger.error(f"统计机柜数量失败: {e}")
            raise QueryExecutionError("统计机柜数量失败", original_error=e)


    def get_cabinet_statistics(self) -> Dict[str, Any]:
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
