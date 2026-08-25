# -*- coding: utf-8 -*-
"""配件模板仓储

提供 ComponentTemplate 的数据访问方法。
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import or_

from app.models.component_template import ComponentTemplate
from app.persistence.base import BaseRepository


class ComponentTemplateRepository(BaseRepository):
    """配件模板仓储"""

    def __init__(self, session=None):
        super().__init__(ComponentTemplate, session=session)

    def find_by_category(
        self,
        category: Optional[str] = None,
        is_active: Optional[bool] = None,
        customer_id: Optional[int] = None,
        include_global: bool = True,
    ) -> List[ComponentTemplate]:
        """按类别、启用状态和客户筛选模板。"""
        query = self._base_query()
        if category:
            query = query.filter_by(category=category)
        if is_active is not None:
            query = query.filter_by(is_active=is_active)
        if customer_id:
            if include_global:
                query = query.filter(
                    or_(
                        ComponentTemplate.customer_id.is_(None),
                        ComponentTemplate.customer_id == customer_id,
                    )
                )
            else:
                query = query.filter_by(customer_id=customer_id)
        return query.order_by(ComponentTemplate.sort_order, ComponentTemplate.id).all()

    def find_by_category_customer_model(
        self, category: str, customer_id: Optional[int], model: str
    ) -> Optional[ComponentTemplate]:
        """检查 (category, customer_id, model) 三元组是否已存在。"""
        return self._base_query().filter_by(
            category=category, customer_id=customer_id, model=model
        ).first()

    def delete_customer_templates(self, customer_id: int) -> int:
        """硬删除客户专属组件模板（scope='customer'）。

        终止客户时调用。scope='customer' 的模板 customer_id 为必填，
        置 NULL 会违反模型验证，故采用硬删除（终止后模板不可恢复）。

        Returns:
            int: 删除行数
        """
        from extensions import db
        result = db.session.query(ComponentTemplate).filter(
            ComponentTemplate.customer_id == customer_id,
            ComponentTemplate.scope == "customer",
        ).delete(synchronize_session=False)
        return result
