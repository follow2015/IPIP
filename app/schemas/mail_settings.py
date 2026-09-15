# -*- coding: utf-8 -*-
"""邮件配置请求验证 Schema（T3.1：mail_settings_routes 写路由契约）。

字段来源：逐条取自 handler 或其 service 实际读取的键——**不按接口名臆测**。
按 `app/schemas/device.py` 的既有约定：契约只声明确实会被读取的字段，
其余动态透传字段仍可发送（`Meta.unknown = EXCLUDE`）。
"""
from marshmallow import Schema, fields, validate, EXCLUDE

class MailConfigUpdateRequestSchema(Schema):
    """更新邮件配置（`PUT /settings/mail`）。

    handler 直接读取这两个布尔开关；其余邮件参数走动态白名单透传。
    """
    class Meta:
        unknown = EXCLUDE
    mail_use_ssl = fields.Bool(allow_none=True)
    mail_use_tls = fields.Bool(allow_none=True)


class MailConfigTestRequestSchema(Schema):
    """发送测试邮件（`POST /settings/mail/test`）。"""
    class Meta:
        unknown = EXCLUDE
    recipient = fields.Str(allow_none=True)
