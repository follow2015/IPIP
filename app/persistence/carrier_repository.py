# -*- coding: utf-8 -*-
"""运营商 Repository

唯一合法的 `carriers` 表访问入口。Service 层禁止直接使用 db_manager 或裸 SQL。
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from app.core.pagination_limits import ensure_offset_within_limit
from app.models.carrier import Carrier
from app.models.circuit import Circuit
from app.persistence.base import QueryOptimizationMixin, SQLAlchemyRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CarrierRepository(SQLAlchemyRepository, QueryOptimizationMixin):
    """运营商 Repository"""

    def __init__(self, session=None):
        super().__init__(Carrier, session)

    def get_by_name(self, name: str) -> Optional[Carrier]:
        """按全称精确查（用于重名校验 AC-C-19）。

        只查**未软删**的行：软删行的 `deleted_token` 非空，其名称已被释放，
        不应阻挡新运营商复用同名。
        """
        return (
            self.session.query(Carrier)
            .filter(Carrier.name == name, Carrier.deleted_token == "")
            .first()
        )

    def count_active_circuits(self, carrier_id: int) -> int:
        """统计挂靠在该运营商名下、且**未终止**的线路数（AC-C-20 的阻断判据）。

        为什么排除 `terminated`：已终止的线路是历史记录，不该阻止运营商退役。
        但**未终止**的线路是持续计费的租约，此时停用运营商会让线路失去归属方。
        """
        return int(
            self.session.query(func.count(Circuit.id))
            .filter(
                Circuit.carrier_id == carrier_id,
                Circuit.deleted_at.is_(None),
                Circuit.status != "terminated",
            )
            .scalar()
            or 0
        )

    def list_with_filters(
        self, filters: Optional[Dict[str, Any]] = None, page: int = 1, per_page: int = 20
    ):
        """分页列表，支持 `status` / `carrier_type` / 关键字 `keyword`。"""
        filters = filters or {}
        query = self._base_query()

        if filters.get("status"):
            query = query.filter(Carrier.status == filters["status"])
        if filters.get("carrier_type"):
            query = query.filter(Carrier.carrier_type == filters["carrier_type"])
        keyword = (filters.get("keyword") or "").strip()
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                (Carrier.name.like(like)) | (Carrier.short_name.like(like))
            )

        query = query.order_by(Carrier.name)

        total = query.count()
        offset = (max(int(page), 1) - 1) * max(int(per_page), 1)
        offset = ensure_offset_within_limit(offset)
        items = query.offset(offset).limit(max(int(per_page), 1)).all()
        return {"items": items, "total": total, "page": page, "per_page": per_page}

    def stats_by_ids(self, carrier_ids: List[int]) -> Dict[int, int]:
        """批量统计各运营商名下的线路数（列表页避免 N+1）。"""
        if not carrier_ids:
            return {}
        rows = (
            self.session.query(Circuit.carrier_id, func.count(Circuit.id))
            .filter(
                Circuit.carrier_id.in_(carrier_ids),
                Circuit.deleted_at.is_(None),
            )
            .group_by(Circuit.carrier_id)
            .all()
        )
        return {int(r[0]): int(r[1]) for r in rows if r[0] is not None}
