# -*- coding: utf-8 -*-
"""设备端口 / 连接请求验证 Schema（T3.1：`device_port_routes.py` 的 request_body 契约）。

字段来源：`create_port` / `update_port` 的字段取自 `PortManagementService`
（`app/services/port_management_service.py`）实际读取的键，**不按接口名臆测**：

- `create_port`：服务直接读取 10 个字段（`port_name` 必填，其余可选）
- `update_port`：服务内**白名单** `{usage_status, description, vlan, customer_id, port_type, speed}`，
  非白名单字段会被静默忽略——契约只声明白名单内的字段，正因如此
- `create_connection` / `update_connection`：**复用** `app/schemas/device_connection.py`
  的现存 Schema（`create_d2n_connection` 直接转调
  `device_connection_service.create_connection(data)`，同一套字段）
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class PortCreateRequestSchema(Schema):
    """手动创建端口（`POST /device/<int:device_id>/ports`）。

    `port_name` **必填**：服务内 `if not port_name: raise ValidationError("端口名称不能为空")`，
    且会经 `parse_port_name` 解析（data_source="manual"）。端口名在设备内唯一。
    """
    class Meta:
        unknown = EXCLUDE

    port_name = fields.Str(required=True)
    port_number = fields.Str(allow_none=True)       # 服务读取的原始端口号
    port_type = fields.Str(allow_none=True)         # 如 electrical / optical
    speed = fields.Str(allow_none=True)             # 如 1000M / 10G
    vlan = fields.Int(allow_none=True)
    usage_status = fields.Str(allow_none=True)
    customer_id = fields.Int(allow_none=True)
    description = fields.Str(allow_none=True)
    card = fields.Int(allow_none=True)              # 槽位解析结果（可显式传入）
    slot = fields.Int(allow_none=True)


class PortUpdateRequestSchema(Schema):
    """更新端口（`PUT /device/<int:device_id>/ports/<path:port_name>`）。

    **只白名单内的 6 个字段会被写入**——服务内
    `allowed = {"usage_status", "description", "vlan", "customer_id", "port_type", "speed"}`，
    其余字段静默忽略。契约按白名单声明，避免前端以为能改别的字段。
    """
    class Meta:
        unknown = EXCLUDE

    usage_status = fields.Str(allow_none=True)
    description = fields.Str(allow_none=True)
    vlan = fields.Int(allow_none=True)
    customer_id = fields.Int(allow_none=True)
    port_type = fields.Str(allow_none=True)
    speed = fields.Str(allow_none=True)


class PortSyncEnabledUpdateRequestSchema(Schema):
    """更新端口同步开关（`PUT /device/<int:device_id>/port-sync-enabled`）。

    `port_sync_enabled` 可传 `null` 表示**跟随全局**（handler docstring 明示），
    故字段非必填且允许 null；handler 对非布尔非 null 值返回 400，
    schema 侧只允许 `Bool | null` 以如实描述类型。
    """
    class Meta:
        unknown = EXCLUDE

    port_sync_enabled = fields.Bool(allow_none=True)
