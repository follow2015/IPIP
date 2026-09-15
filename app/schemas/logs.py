# -*- coding: utf-8 -*-
"""前端日志上报请求验证 Schema（T3.1：logs 写路由契约）。

字段来源：逐条取自 handler 或其 service 实际读取的键——**不按接口名臆测**。
按 `app/schemas/device.py` 的既有约定：契约只声明确实会被读取的字段，
其余动态透传字段仍可发送（`Meta.unknown = EXCLUDE`）。
"""
from marshmallow import Schema, fields, validate, EXCLUDE

class LogErrorReportRequestSchema(Schema):
    """错误日志上报（`POST /logs/error`）。

    前端 SDK 直接上报的错误对象，字段名沿用浏览器事件字段（`userAgent` 为小驼峰）。
    """
    class Meta:
        unknown = EXCLUDE
    message = fields.Str(allow_none=True)
    error = fields.Raw(allow_none=True)
    url = fields.Str(allow_none=True)
    line = fields.Int(allow_none=True)
    column = fields.Int(allow_none=True)
    timestamp = fields.Raw(allow_none=True)
    userAgent = fields.Str(allow_none=True)


class LogInfoReportRequestSchema(Schema):
    """信息日志上报（`POST /logs/info`）。"""
    class Meta:
        unknown = EXCLUDE
    message = fields.Str(allow_none=True)
    level = fields.Str(allow_none=True)
    data = fields.Raw(allow_none=True)
    timestamp = fields.Raw(allow_none=True)
