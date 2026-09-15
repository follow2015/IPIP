# -*- coding: utf-8 -*-
"""device_nics_port请求验证 Schema。

T3.1 从 app/api/device_nics_port.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from typing import Dict

from marshmallow import Schema, fields, validate, EXCLUDE


class NicPortBatchSchema(Schema):
    """创建或更新设备网卡配置请求Schema"""
    class Meta:
        unknown = EXCLUDE
    nics = fields.List(fields.Dict(), required=True)


class NicPortIncrementalBatchSchema(Schema):
    """增量批量创建网卡端口请求Schema"""
    class Meta:
        unknown = EXCLUDE
    ports = fields.List(fields.Dict(), required=True)


class NicPortUpdateSchema(Schema):
    """更新单个端口请求Schema"""
    class Meta:
        unknown = EXCLUDE
    port_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    port_speed = fields.Str(validate=validate.Length(max=20), allow_none=True)
    port_name = fields.Str(validate=validate.Length(max=100), allow_none=True)
    port_status = fields.Str(validate=validate.Length(max=20), allow_none=True)
    description = fields.Str(validate=validate.Length(max=200), allow_none=True)
