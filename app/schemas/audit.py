# -*- coding: utf-8 -*-
"""audit请求验证 Schema。

T3.1 从 app/api/audit.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class AuditLogQuerySchema(Schema):
    """审计日志查询参数"""
    user_id = fields.Int(load_default=None)
    action = fields.Str(load_default=None)
    resource = fields.Str(load_default=None)
    resource_id = fields.Int(load_default=None)
    start_time = fields.Str(load_default=None, metadata={"description": "起始时间 ISO8601"})
    end_time = fields.Str(load_default=None, metadata={"description": "结束时间 ISO8601"})
    page = fields.Int(load_default=1, validate=validate.Range(min=1))
    per_page = fields.Int(load_default=20, validate=validate.Range(min=1, max=100))


