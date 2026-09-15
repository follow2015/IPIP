# -*- coding: utf-8 -*-
"""Webhook 配置请求验证 Schema（T3.1：webhook_config_routes 写路由契约）。

字段来源：逐条取自 handler 或其 service 实际读取的键——**不按接口名臆测**。
按 `app/schemas/device.py` 的既有约定：契约只声明确实会被读取的字段，
其余动态透传字段仍可发送（`Meta.unknown = EXCLUDE`）。
"""
from marshmallow import Schema, fields, validate, EXCLUDE

class WebhookConfigCreateRequestSchema(Schema):
    """创建 Webhook 配置（`POST /webhook-configs`）。

    字段取自 `WebhookConfigService.create_config` 实读的键。
    """
    class Meta:
        unknown = EXCLUDE
    name = fields.Str(required=True)
    channel = fields.Str(allow_none=True)          # feishu / dingtalk / wechat_work
    url = fields.Str(allow_none=True)
    secret = fields.Str(allow_none=True)           # 加签密钥（企微无签名）
    enabled = fields.Bool(allow_none=True)
    message_template = fields.Str(allow_none=True)
    applicable_types = fields.List(fields.Str(), allow_none=True)
    applicable_severities = fields.List(fields.Str(), allow_none=True)


class WebhookConfigUpdateRequestSchema(Schema):
    """更新 Webhook 配置（`PUT /webhook-configs/<id>`）——字段同创建，全部可选。"""
    class Meta:
        unknown = EXCLUDE
    name = fields.Str(allow_none=True)
    channel = fields.Str(allow_none=True)
    url = fields.Str(allow_none=True)
    secret = fields.Str(allow_none=True)
    enabled = fields.Bool(allow_none=True)
    message_template = fields.Str(allow_none=True)
    applicable_types = fields.List(fields.Str(), allow_none=True)
    applicable_severities = fields.List(fields.Str(), allow_none=True)
