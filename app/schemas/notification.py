# -*- coding: utf-8 -*-
"""通知请求验证 Schema（T3.1：notification_routes 写路由契约）。

字段来源：逐条取自 handler 或其 service 实际读取的键——**不按接口名臆测**。
按 `app/schemas/device.py` 的既有约定：契约只声明确实会被读取的字段，
其余动态透传字段仍可发送（`Meta.unknown = EXCLUDE`）。
"""
from marshmallow import Schema, fields, validate, EXCLUDE

class NotificationMarkReadRequestSchema(Schema):
    """标记通知已读（`POST /notifications/mark-read`）。"""
    class Meta:
        unknown = EXCLUDE
    notification_ids = fields.List(fields.Int(), allow_none=True)


class NotificationPreferencesUpdateRequestSchema(Schema):
    """更新通知偏好（`PUT /notifications/preferences`）。

    服务为 **merge 语义**（`NotificationService.update_preferences`）：
    只覆盖传入的键，故三项均可选。
    """
    class Meta:
        unknown = EXCLUDE
    channels = fields.Dict(allow_none=True)
    subscribed_types = fields.List(fields.Str(), allow_none=True)
    quiet_hours = fields.Dict(allow_none=True)
