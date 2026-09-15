# -*- coding: utf-8 -*-
"""room请求验证 Schema。

T3.1 从 app/api/room.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class RoomCreateSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    location = fields.Str(load_default="", validate=validate.Length(max=200))
    contact = fields.Str(load_default="", validate=validate.Length(max=100))
    contact_phone = fields.Str(load_default="", validate=validate.Length(max=50))


class RoomUpdateSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1, max=100))
    location = fields.Str(validate=validate.Length(max=200))
    contact = fields.Str(validate=validate.Length(max=100))
    contact_phone = fields.Str(validate=validate.Length(max=50))


