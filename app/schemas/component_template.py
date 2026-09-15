# -*- coding: utf-8 -*-
"""组件模板请求验证 Schema（T3.1：component_template 写路由契约）。

字段来源：逐条取自 handler 或其 service 实际读取的键——**不按接口名臆测**。
按 `app/schemas/device.py` 的既有约定：契约只声明确实会被读取的字段，
其余动态透传字段仍可发送（`Meta.unknown = EXCLUDE`）。
"""
from marshmallow import Schema, fields, validate, EXCLUDE

class ComponentTemplateCreateRequestSchema(Schema):
    """创建组件模板（`POST /component-templates`）。

    `category` / `model` 必填：服务内 `raise ValidationError("类别不能为空")` /
    `("型号不能为空")`。其余模板内容字段按原样透传。
    """
    class Meta:
        unknown = EXCLUDE
    category = fields.Str(required=True)
    model = fields.Str(required=True)


class ComponentTemplateUpdateRequestSchema(Schema):
    """更新组件模板（`PUT /component-templates/<id>`）——全部可选。"""
    class Meta:
        unknown = EXCLUDE
    category = fields.Str(allow_none=True)
    model = fields.Str(allow_none=True)
