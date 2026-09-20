# -*- coding: utf-8 -*-
"""room请求验证 Schema。

T3.1 从 app/api/room.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from marshmallow import Schema, fields, validate, EXCLUDE

from app.core.enums import RoomStatus


class RoomCreateSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    room_number = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    location = fields.Str(load_default="", validate=validate.Length(max=200))
    contact = fields.Str(load_default="", validate=validate.Length(max=100))
    contact_phone = fields.Str(load_default="", validate=validate.Length(max=50))
    building = fields.Str(load_default=None, allow_none=True, validate=validate.Length(max=100))
    floor = fields.Str(load_default=None, allow_none=True, validate=validate.Length(max=20))


class RoomUpdateSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1, max=100))
    room_number = fields.Str(validate=validate.Length(min=1, max=50))
    status = fields.Int(validate=validate.OneOf([s.value for s in RoomStatus]))
    location = fields.Str(validate=validate.Length(max=200))
    contact = fields.Str(validate=validate.Length(max=100))
    contact_phone = fields.Str(validate=validate.Length(max=50))
    building = fields.Str(allow_none=True, validate=validate.Length(max=100))
    floor = fields.Str(allow_none=True, validate=validate.Length(max=20))



CHANNEL_TYPES = ["cold", "hot", "mixed"]
SUPPLY_TYPES = ["floor", "direct", "none"]


class RoomChannelCreateSchema(Schema):
    """通道配置：新增"""

    col_number = fields.Int(required=True, validate=validate.Range(min=0, max=999))
    channel_type = fields.Str(required=True, validate=validate.OneOf(CHANNEL_TYPES))
    enclosed = fields.Bool(load_default=False)
    supply = fields.Str(
        load_default=None, allow_none=True, validate=validate.OneOf(SUPPLY_TYPES)
    )
    label = fields.Str(load_default=None, allow_none=True, validate=validate.Length(max=100))
    notes = fields.Str(load_default=None, allow_none=True, validate=validate.Length(max=500))


class RoomChannelUpdateSchema(Schema):
    """通道配置：编辑（全部可选）"""

    col_number = fields.Int(validate=validate.Range(min=0, max=999))
    channel_type = fields.Str(validate=validate.OneOf(CHANNEL_TYPES))
    enclosed = fields.Bool()
    supply = fields.Str(allow_none=True, validate=validate.OneOf(SUPPLY_TYPES))
    label = fields.Str(allow_none=True, validate=validate.Length(max=100))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=500))



MARKER_TYPES = ["ac", "pdu", "pillar", "door", "other"]


class RoomLayoutMarkerCreateSchema(Schema):
    """占位标记：新增"""

    row_number = fields.Int(required=True, validate=validate.Range(min=0, max=9999))
    col_number = fields.Int(required=True, validate=validate.Range(min=0, max=9999))
    marker_type = fields.Str(required=True, validate=validate.OneOf(MARKER_TYPES))
    label = fields.Str(load_default=None, allow_none=True, validate=validate.Length(max=100))
    notes = fields.Str(load_default=None, allow_none=True, validate=validate.Length(max=500))


class RoomLayoutMarkerUpdateSchema(Schema):
    """占位标记：编辑（全部可选）"""

    row_number = fields.Int(validate=validate.Range(min=0, max=9999))
    col_number = fields.Int(validate=validate.Range(min=0, max=9999))
    marker_type = fields.Str(validate=validate.OneOf(MARKER_TYPES))
    label = fields.Str(allow_none=True, validate=validate.Length(max=100))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=500))


