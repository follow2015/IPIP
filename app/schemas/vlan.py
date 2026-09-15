# -*- coding: utf-8 -*-
"""vlan请求验证 Schema。

T3.1 从 app/api/vlan.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class VLANCreateSchema(Schema):
    """VLAN创建参数"""
    vlan_id = fields.Int(required=True, validate=validate.Range(min=1, max=4094))
    name = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    purpose = fields.Str(load_default=None, validate=validate.Length(max=200))
    subnet_id = fields.Int(load_default=None)
    room_id = fields.Int(load_default=None)
    device_id = fields.Int(required=True)
    status = fields.Int(load_default=1)


class VLANUpdateSchema(Schema):
    """VLAN更新参数"""
    name = fields.Str(validate=validate.Length(min=1, max=64))
    purpose = fields.Str(validate=validate.Length(max=200))
    subnet_id = fields.Int()
    room_id = fields.Int()
    status = fields.Int()


