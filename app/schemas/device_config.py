# -*- coding: utf-8 -*-
"""device_config请求验证 Schema。

T3.1 从 app/api/device_config.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class ConfigChangeRequestSchema(Schema):
    """提交配置变更请求Schema（字段名对齐 DeviceConfigChange 模型）"""
    class Meta:
        unknown = EXCLUDE
    change_summary = fields.Str(
        required=True, validate=validate.Length(min=1, max=500),
        error_messages={"required": "变更摘要不能为空"},
    )
    change_detail = fields.Str(allow_none=True)
    backup_id = fields.Int(allow_none=True)


