# -*- coding: utf-8 -*-
"""auth请求验证 Schema。

T3.1 从 app/api/auth.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class LoginSchema(Schema):
    """用户登录请求Schema"""
    class Meta:
        unknown = EXCLUDE
    username = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    password = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    remember = fields.Bool(load_default=False)


class QRCodeConfirmSchema(Schema):
    """确认二维码登录请求Schema"""
    class Meta:
        unknown = EXCLUDE
    scene_id = fields.Str(required=True)
    code = fields.Str(required=True, validate=validate.Length(min=1, max=200))


class QRCodeCompleteSchema(Schema):
    """完成二维码登录请求Schema"""
    class Meta:
        unknown = EXCLUDE
    scene_id = fields.Str(required=True)
