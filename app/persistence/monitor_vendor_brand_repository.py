# -*- coding: utf-8 -*-
"""厂商品牌仓库（MonitorVendorBrandRepository）

C5：vendor_brand_service 的数据库访问统一经此仓库，
禁止在 Service 层直接操作 db.session（项目约束：数据库必须走 Repository 层）。
"""
from typing import List, Optional

from extensions import db
from app.models.monitor_vendor_brand import MonitorVendorBrand


class MonitorVendorBrandRepository:

    def __init__(self, session=None):
        self.session = session or db.session

    def list_all(
        self,
        device_type: Optional[str] = None,
        only_enabled: bool = True,
    ) -> List[MonitorVendorBrand]:
        q = self.session.query(MonitorVendorBrand)
        if device_type:
            q = q.filter_by(device_type=device_type)
        if only_enabled:
            q = q.filter_by(enabled=True)
        return q.order_by(
            MonitorVendorBrand.sort_order.asc(),
            MonitorVendorBrand.id.asc(),
        ).all()

    def list_enabled(self) -> List[MonitorVendorBrand]:
        return (
            self.session.query(MonitorVendorBrand)
            .filter_by(enabled=True)
            .order_by(
                MonitorVendorBrand.sort_order.asc(),
                MonitorVendorBrand.id.asc(),
            )
            .all()
        )

    def find_by_id(self, brand_id: int) -> Optional[MonitorVendorBrand]:
        return self.session.get(MonitorVendorBrand, brand_id)

    def find_by_brand_name(self, brand_name: str) -> Optional[MonitorVendorBrand]:
        return (
            self.session.query(MonitorVendorBrand)
            .filter_by(brand_name=brand_name, enabled=True)
            .first()
        )

    def find_by_id_or_404(self, brand_id: int) -> MonitorVendorBrand:
        row = self.session.get(MonitorVendorBrand, brand_id)
        if row is None:
            from app.exceptions.business import BusinessLogicError
            raise BusinessLogicError("厂商品牌不存在", status_code=404)
        return row

    def add(self, row: MonitorVendorBrand) -> MonitorVendorBrand:
        self.session.add(row)
        self.session.flush()
        return row

    def delete(self, row: MonitorVendorBrand) -> None:
        self.session.delete(row)
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()
