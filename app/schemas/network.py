# -*- coding: utf-8 -*-
"""网络扫描请求验证 Schema（T3.1：network_routes 写路由契约）。

字段来源：逐条取自 handler 或其 service 实际读取的键——**不按接口名臆测**。
按 `app/schemas/device.py` 的既有约定：契约只声明确实会被读取的字段，
其余动态透传字段仍可发送（`Meta.unknown = EXCLUDE`）。
"""
from marshmallow import Schema, fields, validate, EXCLUDE

class NetworkCustomerUpdateRequestSchema(Schema):
    """更新网段客户归属（`PUT /network/<network_id>/customer`）。"""
    class Meta:
        unknown = EXCLUDE
    network_id = fields.Int(allow_none=True)
    customer_id = fields.Int(allow_none=True)
    force = fields.Bool(allow_none=True)


class NetworkNoAuthRebuildRequestSchema(Schema):
    """重建无鉴权回退（`POST /network/no-auth/rebuild`）。"""
    class Meta:
        unknown = EXCLUDE
    room_id = fields.Int(allow_none=True)
