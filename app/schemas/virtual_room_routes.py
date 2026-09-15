# -*- coding: utf-8 -*-
"""virtual_room_routes请求验证 Schema。

T3.1 从 app/api/virtual_room_routes.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class VirtualRoomCreateSchema(Schema):
    """虚拟机房创建参数

    device_ids 允许为空（支持"先建空壳，后续通过 /members 接口添加成员"的工作流）。
    full_scan 对空成员有 early return（status=skipped, reason=no_switches），
    不会产生无意义的 Redis key 和进度记录。
    """
    name = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    description = fields.Str(validate=validate.Length(max=500), load_default="")
    device_ids = fields.List(fields.Int(), load_default=[])


class VirtualRoomUpdateSchema(Schema):
    """虚拟机房更新参数"""
    name = fields.Str(validate=validate.Length(min=1, max=255))
    description = fields.Str(validate=validate.Length(max=500))


class VirtualRoomMembersSchema(Schema):
    """虚拟机房成员更新参数"""
    device_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))


