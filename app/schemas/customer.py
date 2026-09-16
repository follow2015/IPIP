# -*- coding: utf-8 -*-
"""customer请求验证 Schema。

T3.1 从 app/api/customer.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from marshmallow import Schema, fields, validate, EXCLUDE
from app.core.enums import CustomerStatus


class CustomerCreateSchema(Schema):
    """创建客户请求验证Schema
    
    字段名与数据库模型保持一致：customer_name, customer_status
    只有 customer_name 是必填，其他字段均可为空
    """
    
    class Meta:
        unknown = EXCLUDE  # 忽略未知字段

    customer_name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    customer_status = fields.Int(load_default=CustomerStatus.ACTIVE.value)
    contact_person = fields.Str(allow_none=True, validate=validate.Length(max=50))
    contact_phone = fields.Str(allow_none=True, validate=validate.Length(max=20))
    email = fields.Email(allow_none=True)  # 允许空值
    address = fields.Str(allow_none=True, validate=validate.Length(max=200))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=500))


class CustomerUpdateSchema(Schema):
    """更新客户请求验证Schema

    字段名与数据库模型保持一致：customer_name, customer_status
    """

    class Meta:
        unknown = EXCLUDE  # 忽略未知字段

    customer_name = fields.Str(validate=validate.Length(min=1, max=100))
    customer_status = fields.Int()
    contact_person = fields.Str(allow_none=True, validate=validate.Length(max=50))
    contact_phone = fields.Str(allow_none=True, validate=validate.Length(max=20))
    email = fields.Email(allow_none=True)  # 允许空值
    address = fields.Str(allow_none=True, validate=validate.Length(max=200))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=500))
    reason = fields.Str(allow_none=True, validate=validate.Length(max=500))

class CustomerTerminateRequestSchema(Schema):
    """终止客户（`POST /customers/<int:customer_id>/terminate`）。

    仅 `reason`（终止原因），可选。
    """
    class Meta:
        unknown = EXCLUDE
    reason = fields.Str(allow_none=True)
