# -*- coding: utf-8 -*-
"""拓扑发现请求验证 Schema（T3.1：topology_routes 写路由契约）。

字段来源：逐条取自 handler 或其 service 实际读取的键——**不按接口名臆测**。
按 `app/schemas/device.py` 的既有约定：契约只声明确实会被读取的字段，
其余动态透传字段仍可发送（`Meta.unknown = EXCLUDE`）。
"""
from marshmallow import Schema, fields, validate, EXCLUDE

class TopologyAutoDetectRequestSchema(Schema):
    """自动探测拓扑（`POST /topology/auto-detect`）。"""
    class Meta:
        unknown = EXCLUDE
    room_id = fields.Int(allow_none=True)
    dry_run = fields.Bool(allow_none=True)
    force = fields.Bool(allow_none=True)


class TopologyDiscoverRequestSchema(Schema):
    """发现单个/多个设备的拓扑（`POST /topology/discover`）。"""
    class Meta:
        unknown = EXCLUDE
    device_id = fields.Int(allow_none=True)
    device_ids = fields.List(fields.Int(), allow_none=True)


class TopologyApplyRequestSchema(Schema):
    """应用发现结果（`POST /topology/apply`）。

    `suggestions` 为发现阶段产出的建议列表，结构由上游 discover 决定，故按原样透传。
    """
    class Meta:
        unknown = EXCLUDE
    device_id = fields.Int(allow_none=True)
    suggestions = fields.List(fields.Raw(), allow_none=True)
