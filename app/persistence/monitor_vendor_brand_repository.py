# -*- coding: utf-8 -*-
"""厂商品牌仓库（MonitorVendorBrandRepository）

C5：vendor_brand_service 的数据库访问统一经此仓库，
禁止在 Service 层直接操作 db.session（项目约束：数据库必须走 Repository 层）。
"""
from typing import List, Optional

from extensions import db
from app.models.monitor_vendor_brand import MonitorVendorBrand


class MonitorVendorBrandRepository:
    """厂商品牌仓库"""

    def __init__(self, session=None):
        self.session = session or db.session

    def list_all(
        self,
        device_type: Optional[str] = None,
        only_enabled: bool = True,
    ) -> List[MonitorVendorBrand]:
        """列出厂商品牌（按 sort_order 排序）。"""
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
        """列出启用的厂商品牌（按 sort_order 排序，用于 label map）。"""
        return (
            self.session.query(MonitorVendorBrand)
            .filter_by(enabled=True)
            .order_by(
                MonitorVendorBrand.sort_order.asc(),
                MonitorVendorBrand.id.asc(),
            )
            .all()
        )

    def find_by_enterprise_no(self, enterprise_no: str) -> Optional[MonitorVendorBrand]:
        """按 enterprise 号查启用品牌；不存在返回 None。

        供 AI 诊断把 device.brand（存的是 enterprise 号）解析为命令族时使用。
        同一 enterprise 号可能存在多行（如 2011 同时登记了服务器与网络设备），
        此处只取 sort_order 最小的一行 —— 命令族只取决于厂商，与设备类别无关。
        """
        return (
            self.session.query(MonitorVendorBrand)
            .filter_by(enterprise_no=str(enterprise_no), enabled=True)
            .order_by(MonitorVendorBrand.sort_order.asc())
            .first()
        )

    def find_by_id(self, brand_id: int) -> Optional[MonitorVendorBrand]:
        """按 ID 查询；不存在返回 None。"""
        return self.session.get(MonitorVendorBrand, brand_id)

    def find_by_brand_name(self, brand_name: str) -> Optional[MonitorVendorBrand]:
        """按 brand_name 查启用品牌；不存在返回 None。

        供 batch_import_templates 防御性归一化使用：前端传 brand_name 时转成 enterprise_no。
        仅查启用品牌，避免导入到已下线厂商。
        """
        return (
            self.session.query(MonitorVendorBrand)
            .filter_by(brand_name=brand_name, enabled=True)
            .first()
        )

    def find_by_id_or_404(self, brand_id: int) -> MonitorVendorBrand:
        """按 ID 查询；不存在抛 404。"""
        row = self.session.get(MonitorVendorBrand, brand_id)
        if row is None:
            from app.exceptions.business import BusinessLogicError
            raise BusinessLogicError("厂商品牌不存在", status_code=404)
        return row

    def add(self, row: MonitorVendorBrand) -> MonitorVendorBrand:
        """新增并 flush。"""
        self.session.add(row)
        self.session.flush()
        return row

    def delete(self, row: MonitorVendorBrand) -> None:
        """删除并 flush。"""
        self.session.delete(row)
        self.session.flush()

    def commit(self) -> None:
        """提交事务。"""
        self.session.commit()
