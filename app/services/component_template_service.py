# -*- coding: utf-8 -*-
"""配件模板服务

业务逻辑层：所有数据访问经由 ComponentTemplateRepository，
API 层不再直接使用 db.session 或 Model.query。
"""
from typing import Any, Dict, List, Optional

from app.exceptions.validation import ValidationError
from app.models.component_template import ComponentTemplate
from app.persistence.component_template_repository import ComponentTemplateRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ComponentTemplateService:
    """配件模板服务"""

    def __init__(self, template_repository: ComponentTemplateRepository):
        self.template_repository = template_repository

    def list_templates(
        self,
        category: Optional[str] = None,
        is_active: Optional[bool] = None,
        customer_id: Optional[int] = None,
        include_global: bool = True,
    ) -> List[Dict[str, Any]]:
        """列出配件模板，支持按类别、启用状态和客户筛选。"""
        templates = self.template_repository.find_by_category(
            category=category,
            is_active=is_active,
            customer_id=customer_id,
            include_global=include_global,
        )
        return [t.to_dict() for t in templates]

    def get_template(self, template_id: int) -> Optional[ComponentTemplate]:
        """获取单个配件模板。"""
        return self.template_repository.find_by_id(template_id)

    def create_template(self, data: Dict[str, Any]) -> ComponentTemplate:
        """创建配件模板。

        Raises:
            ValidationError: 类别/型号缺失，或三元组重复
        """
        category = data.get("category")
        model = data.get("model")
        if not category:
            raise ValidationError("类别不能为空")
        if not model:
            raise ValidationError("型号不能为空")

        exists = self.template_repository.find_by_category_customer_model(
            category=category,
            customer_id=data.get("customer_id"),
            model=model,
        )
        if exists:
            raise ValidationError("该类别下已存在同名型号模板")

        template = ComponentTemplate(
            category=category,
            customer_id=data.get("customer_id"),
            brand=data.get("brand", ""),
            model=model,
            spec=data.get("spec"),
            is_active=data.get("is_active", True),
            sort_order=data.get("sort_order", 0),
            remark=data.get("remark", ""),
            scope="customer" if data.get("customer_id") else "global",
        )
        template.validate_scope_customer()
        self.template_repository.session.add(template)
        return template

    def update_template(
        self, template_id: int, data: Dict[str, Any]
    ) -> ComponentTemplate:
        """更新配件模板。

        Raises:
            ValidationError: 三元组冲突
        """
        template = self.template_repository.find_by_id(template_id)
        if not template:
            return None

        new_category = data.get("category", template.category)
        new_customer_id = data.get("customer_id", template.customer_id)
        new_model = data.get("model", template.model)
        if (
            new_category != template.category
            or new_customer_id != template.customer_id
            or new_model != template.model
        ):
            exists = self.template_repository.find_by_category_customer_model(
                category=new_category, customer_id=new_customer_id, model=new_model
            )
            if exists:
                raise ValidationError("该类别下已存在同名型号模板")

        for field in (
            "category", "customer_id", "brand", "model",
            "spec", "is_active", "sort_order", "remark",
        ):
            if field in data:
                setattr(template, field, data[field])

        template.scope = "customer" if template.customer_id else "global"
        template.validate_scope_customer()
        return template

    def delete_template(self, template_id: int) -> bool:
        """删除配件模板。"""
        template = self.template_repository.find_by_id(template_id)
        if not template:
            return False
        self.template_repository.session.delete(template)
        return True


component_template_service = ComponentTemplateService(ComponentTemplateRepository())
