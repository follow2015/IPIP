# -*- coding: utf-8 -*-
"""语音配置请求验证 Schema（T3.1：voice_settings_routes 写路由契约）。

字段来源：逐条取自 handler 或其 service 实际读取的键——**不按接口名臆测**。
按 `app/schemas/device.py` 的既有约定：契约只声明确实会被读取的字段，
其余动态透传字段仍可发送（`Meta.unknown = EXCLUDE`）。
"""
from marshmallow import Schema, fields, validate, EXCLUDE

class VoiceConfigUpdateRequestSchema(Schema):
    """更新语音配置（`PUT /settings/voice`）。

    数值键与取值范围取自 `voice_settings_routes._NUMERIC_RANGES`
    （`play_times` 1-3、`volume` 0-100、`speed` -500-500、`call_timeout` 10-30、
    `voice_budget_hour` 1-5、`voice_budget_day` 1-20）；`provider` 仅允许
    `aliyun` / `tencent`。**范围校验仍在 handler 内**，此处只描述类型。
    """
    class Meta:
        unknown = EXCLUDE
    provider = fields.Str(validate=validate.OneOf(["aliyun", "tencent"]), allow_none=True)
    play_times = fields.Int(allow_none=True)
    volume = fields.Int(allow_none=True)
    speed = fields.Int(allow_none=True)
    call_timeout = fields.Int(allow_none=True)
    voice_budget_hour = fields.Int(allow_none=True)
    voice_budget_day = fields.Int(allow_none=True)
