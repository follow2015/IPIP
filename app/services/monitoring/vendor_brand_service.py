# -*- coding: utf-8 -*-
"""厂商品牌服务

提供厂商品牌列表查询 / CRUD。
事务由外层路由 @transactional 控制，service 内只 flush 不 commit。
"""
from extensions import db
from app.utils.logging import get_logger

logger = get_logger(__name__)


def list_vendor_brands(device_type: str | None = None, only_enabled: bool = True):
    from app.persistence.monitor_vendor_brand_repository import MonitorVendorBrandRepository
    repo = MonitorVendorBrandRepository()
    rows = repo.list_all(device_type=device_type, only_enabled=only_enabled)
    return [r.to_dict() for r in rows]


def create_vendor_brand(data: dict) -> int:
    from app.models.monitor_vendor_brand import MonitorVendorBrand
    from app.persistence.monitor_vendor_brand_repository import MonitorVendorBrandRepository
    repo = MonitorVendorBrandRepository()
    row = MonitorVendorBrand(
        enterprise_no=data["enterprise_no"],
        brand_name=data["brand_name"],
        label=data["label"],
        device_type=data["device_type"],
        enabled=data.get("enabled", True),
        sort_order=data.get("sort_order", 0),
    )
    repo.add(row)
    db.session.flush()
    return row.id


def update_vendor_brand(brand_id: int, data: dict) -> None:
    from app.persistence.monitor_vendor_brand_repository import MonitorVendorBrandRepository
    repo = MonitorVendorBrandRepository()
    row = repo.find_by_id_or_404(brand_id)
    for k in ("enterprise_no", "brand_name", "label", "device_type", "enabled", "sort_order"):
        if k in data:
            setattr(row, k, data[k])
    db.session.flush()


def delete_vendor_brand(brand_id: int) -> None:
    from app.persistence.monitor_vendor_brand_repository import MonitorVendorBrandRepository
    repo = MonitorVendorBrandRepository()
    row = repo.find_by_id_or_404(brand_id)
    repo.delete(row)
    db.session.flush()
