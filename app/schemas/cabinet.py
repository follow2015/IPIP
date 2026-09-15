# -*- coding: utf-8 -*-
"""机柜请求验证 Schema。

T3.1 从 app/api/cabinet.py 迁入：这些 Schema 被 app/openapi/spec.py 引用（跨模块使用），
按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from typing import Dict

from marshmallow import Schema, fields, validate, EXCLUDE


class CabinetCreateSchema(Schema):
    """创建机柜请求验证Schema"""

    cabinet_number = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    room_id = fields.Int(required=True, validate=validate.Range(min=1))
    location = fields.Str(allow_none=True, validate=validate.Length(max=255))
    row = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1))
    col = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1))
    total_u = fields.Int(validate=validate.Range(min=1, max=100))
    total_power = fields.Int(allow_none=True, validate=validate.Range(min=0))
    customer_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    status = fields.Int(validate=validate.Range(min=0, max=4))
    notes = fields.Str(allow_none=True)
    batch = fields.Bool(load_default=False)


class CabinetUpdateSchema(Schema):
    """更新机柜请求验证Schema"""

    cabinet_number = fields.Str(validate=validate.Length(min=1, max=255))
    room_id = fields.Int(validate=validate.Range(min=1))
    location = fields.Str(allow_none=True, validate=validate.Length(max=255))
    row = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1))
    col = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1))
    total_u = fields.Int(validate=validate.Range(min=1, max=100))
    total_power = fields.Int(allow_none=True, validate=validate.Range(min=0))
    customer_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    status = fields.Int(validate=validate.Range(min=0, max=4))
    notes = fields.Str(allow_none=True)


class UPositionCheckSchema(Schema):
    """检查U位是否可用请求Schema"""
    class Meta:
        unknown = EXCLUDE
    u_position = fields.Int(required=True)
    height_u = fields.Int(allow_none=True)
    exclude_device_id = fields.Int(allow_none=True)


class UAssignSchema(Schema):
    """批量分配U位请求Schema

    devices 每项: {key: 行标识, height_u: 占用U数, u_position: 已手填起始位(可空)}
    u_position 非空的行原样保留并视为占用；空行由后端按 strategy 分配。
    """
    class Meta:
        unknown = EXCLUDE
    devices = fields.List(fields.Dict(), required=True)
    gap = fields.Int(allow_none=True)
    strategy = fields.Str(allow_none=True)


class SmartUAssignSchema(Schema):
    """智能分配U位请求Schema"""
    class Meta:
        unknown = EXCLUDE
    height_u = fields.Int(required=True)
    device_spacing = fields.Int(allow_none=True)
    allocation_strategy = fields.Str(validate=validate.Length(max=50), allow_none=True)
    min_u = fields.Int(allow_none=True)
    max_u = fields.Int(allow_none=True)


class CabinetCapacityValidateSchema(Schema):
    """验证机柜容量请求Schema"""
    class Meta:
        unknown = EXCLUDE
    new_device = fields.Dict(allow_none=True)
    device_spacing = fields.Int(allow_none=True)
    min_height_for_spacing = fields.Int(allow_none=True)
    max_usage_rate = fields.Float(allow_none=True)


class CabinetOptimizeSchema(Schema):
    """优化机柜布局请求Schema"""
    class Meta:
        unknown = EXCLUDE
    strategy = fields.Str(validate=validate.Length(max=50), allow_none=True)
    device_spacing = fields.Int(allow_none=True)


class CabinetCustomerUpdateSchema(Schema):
    """更新机柜客户请求Schema"""
    class Meta:
        unknown = EXCLUDE
    customer_id = fields.Int(allow_none=True)
