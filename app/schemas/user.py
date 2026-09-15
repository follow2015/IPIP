# -*- coding: utf-8 -*-
"""user请求验证 Schema。

T3.1 从 app/api/user.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class UserLoginSchema(Schema):
    """用户登录请求Schema"""
    class Meta:
        unknown = EXCLUDE
    username = fields.Str(required=True)
    password = fields.Str(required=True)


class UserRegisterSchema(Schema):
    """用户注册请求Schema"""
    class Meta:
        unknown = EXCLUDE
    username = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    password = fields.Str(required=True, validate=validate.Length(min=6, max=200))
    email = fields.Str(required=True, validate=validate.Length(max=200))
    role = fields.Str(validate=validate.Length(max=50), allow_none=True)


class RefreshTokenSchema(Schema):
    """刷新令牌请求Schema"""
    class Meta:
        unknown = EXCLUDE
    refresh_token = fields.Str(required=True)


class UserUpdateRequestSchema(Schema):
    """更新用户信息请求Schema"""
    class Meta:
        unknown = EXCLUDE
    username = fields.Str(validate=validate.Length(max=100), allow_none=True)
    name = fields.Str(validate=validate.Length(max=100), allow_none=True)
    email = fields.Str(validate=validate.Length(max=200), allow_none=True)
    department = fields.Str(validate=validate.Length(max=100), allow_none=True)
    contact_phone = fields.Str(validate=validate.Length(max=50), allow_none=True)
    status = fields.Int(allow_none=True)
    password = fields.Str(validate=validate.Length(min=6, max=200), allow_none=True)


class ChangePasswordSchema(Schema):
    """修改密码请求Schema"""
    class Meta:
        unknown = EXCLUDE
    username = fields.Str(required=True)
    user_id = fields.Int(required=True)
    old_password = fields.Str(required=True)
    new_password = fields.Str(required=True, validate=validate.Length(min=6))
    confirm_password = fields.Str(required=True)


class ResetPasswordSchema(Schema):
    """重置密码请求Schema"""
    class Meta:
        unknown = EXCLUDE
    password = fields.Str(required=True, validate=validate.Length(min=6))
