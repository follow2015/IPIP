# -*- coding: utf-8 -*-
"""前端错误上报请求验证 Schema（T3.1：errors 写路由契约）。

字段来源：逐条取自 handler 或其 service 实际读取的键——**不按接口名臆测**。
按 `app/schemas/device.py` 的既有约定：契约只声明确实会被读取的字段，
其余动态透传字段仍可发送（`Meta.unknown = EXCLUDE`）。
"""
from marshmallow import Schema, fields, validate, EXCLUDE

class ErrorReportRequestSchema(Schema):
    """前端错误批量上报（`POST /errors/report`）。

    handler 读取 `errors`（数组）；元素结构由前端 SDK 决定，按原样透传。
    """
    class Meta:
        unknown = EXCLUDE
    errors = fields.List(fields.Raw(), required=True)
