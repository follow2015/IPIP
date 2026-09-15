# -*- coding: utf-8 -*-
"""device_connection请求验证 Schema。

T3.1 从 app/api/device_connection.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class DeviceConnectionCreateSchema(Schema):
    """创建设备连接请求Schema"""
    class Meta:
        unknown = EXCLUDE
    device_id = fields.Int(required=True)
    switch_device_id = fields.Int(allow_none=True)
    switch_port_id = fields.Int(allow_none=True)
    peer_port_id = fields.Int(allow_none=True)
    device_nics_port_id = fields.Int(allow_none=True)
    link_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    connection_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    vlan_id = fields.Int(allow_none=True)
    notes = fields.Str(validate=validate.Length(max=500), allow_none=True)


class DeviceConnectionUpdateSchema(Schema):
    """更新设备连接请求Schema"""
    class Meta:
        unknown = EXCLUDE
    device_id = fields.Int(allow_none=True)
    switch_device_id = fields.Int(allow_none=True)
    switch_port_id = fields.Int(allow_none=True)
    connection_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    vlan_id = fields.Int(allow_none=True)
    notes = fields.Str(validate=validate.Length(max=500), allow_none=True)
