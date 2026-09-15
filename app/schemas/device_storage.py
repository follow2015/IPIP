# -*- coding: utf-8 -*-
"""device_storage请求验证 Schema。

T3.1 从 app/api/device_storage.py 迁入：这些 Schema 被 app/openapi/spec.py 等模块引用
（跨模块使用），按 app/schemas/device.py 已确立的约定，不在 app/api/ 下就地定义。
"""
from typing import Dict

from marshmallow import Schema, fields, validate, EXCLUDE


class StorageAddSchema(Schema):
    """为设备添加硬盘请求Schema"""
    class Meta:
        unknown = EXCLUDE
    storage_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    capacity = fields.Str(validate=validate.Length(max=50), allow_none=True)
    count = fields.Int(allow_none=True)
    interface_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    manufacturer = fields.Str(validate=validate.Length(max=100), allow_none=True)
    model = fields.Str(validate=validate.Length(max=100), allow_none=True)
    serial_number = fields.Str(validate=validate.Length(max=100), allow_none=True)
    storage_list = fields.List(fields.Dict(), allow_none=True)


class StorageOverwriteSchema(Schema):
    """整机覆盖写入存储配置请求Schema"""
    class Meta:
        unknown = EXCLUDE
    storage_config = fields.List(fields.Dict(), allow_none=True)


class StorageUpdateSchema(Schema):
    """更新单条硬盘信息请求Schema"""
    class Meta:
        unknown = EXCLUDE
    storage_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    capacity = fields.Str(validate=validate.Length(max=50), allow_none=True)
    interface_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    manufacturer = fields.Str(validate=validate.Length(max=100), allow_none=True)
    model = fields.Str(validate=validate.Length(max=100), allow_none=True)
    serial_number = fields.Str(validate=validate.Length(max=100), allow_none=True)


class StorageSerialCheckSchema(Schema):
    """校验硬盘序列号唯一性请求Schema"""
    class Meta:
        unknown = EXCLUDE
    serial_number = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    exclude_id = fields.Int(allow_none=True)
