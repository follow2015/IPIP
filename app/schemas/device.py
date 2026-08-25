# -*- coding: utf-8 -*-
"""设备请求验证 Schema

从 app/api/device.py 拆分而来，供 API 层和 Service 层共同引用，
消除 service → api 的反向依赖。
"""

from marshmallow import Schema, fields, validate, EXCLUDE
from app.core.enums import SwitchDeviceTypeCode, SSHProtocolCode


class NullableDate(fields.Date):
    """Date 字段，将空字符串视为 None。

    前端表单中日期字段为空时提交 ""（空字符串），
    Marshmallow 的 fields.Date 不接受空字符串，会报 "Not a valid date"。
    此字段在反序列化前将空字符串转为 None，使 allow_none=True 生效。
    """

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, str) and not value.strip():
            return None
        return super()._deserialize(value, attr, data, **kwargs)


class DeviceCreateSchema(Schema):
    """创建设备请求验证Schema"""

    class Meta:
        unknown = EXCLUDE  # 忽略未知字段

    device_name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    cabinet_id = fields.Int(validate=validate.Range(min=1), allow_none=True)  # 节点设备可不指定机柜
    device_type = fields.Str(validate=validate.Length(max=50))
    brand = fields.Str(validate=validate.Length(max=50))
    device_model = fields.Str(validate=validate.Length(max=50))
    serial_number = fields.Str(validate=validate.Length(max=100))
    u_position = fields.Int(validate=validate.Range(min=0), allow_none=True)  # 允许0（节点设备不占用U位）
    height_u = fields.Int(validate=validate.Range(min=0, max=50), allow_none=True)  # 允许0（节点设备）
    power = fields.Float(validate=validate.Range(min=0), allow_none=True)
    ip_address = fields.Str(allow_none=True)
    management_ip = fields.Str(allow_none=True)
    mac_address = fields.Str(allow_none=True)
    customer_id = fields.Int(validate=validate.Range(min=1), allow_none=True)
    status = fields.Int(validate=validate.Range(min=0, max=7), allow_none=True)
    notes = fields.Str(validate=validate.Length(max=500), allow_none=True)
    cpu = fields.Str(validate=validate.Length(max=100), allow_none=True)
    cpu_way = fields.Int(validate=validate.Range(min=1, max=8), allow_none=True)
    cpu_cores = fields.Int(validate=validate.Range(min=1), allow_none=True)
    memory = fields.Str(validate=validate.Length(max=100), allow_none=True)
    memory_size_gb = fields.Int(validate=validate.Range(min=0), allow_none=True)
    storage = fields.Str(validate=validate.Length(max=200), allow_none=True)
    storage_summary = fields.Str(validate=validate.Length(max=200), allow_none=True)
    hostname = fields.Str(validate=validate.Length(max=100), allow_none=True)
    os_version = fields.Str(validate=validate.Length(max=100), allow_none=True)
    responsible_person = fields.Int(validate=validate.Range(min=1), allow_none=True)  # 责任人ID（外键关联users.id）
    parent_device_id = fields.Int(allow_none=True)
    is_chassis = fields.Bool(allow_none=True)
    node_position = fields.Int(allow_none=True)
    node_row = fields.Int(allow_none=True)
    node_col = fields.Int(allow_none=True)
    total_nodes = fields.Int(allow_none=True)
    node_rows = fields.Int(allow_none=True)
    node_cols = fields.Int(allow_none=True)
    device_subtype = fields.Str(validate=validate.Length(max=50), allow_none=True)
    node_naming_pattern = fields.Str(validate=validate.Length(max=100), allow_none=True)
    auto_create_nodes = fields.Bool(load_default=False)
    asset_number = fields.Str(validate=validate.Length(max=64), allow_none=True)
    supplier = fields.Str(validate=validate.Length(max=100), allow_none=True)
    supplier_contact = fields.Str(validate=validate.Length(max=100), allow_none=True)
    contract_number = fields.Str(validate=validate.Length(max=100), allow_none=True)
    purchase_date = NullableDate(allow_none=True)
    purchase_price = fields.Float(validate=validate.Range(min=0), allow_none=True)
    invoice_number = fields.Str(validate=validate.Length(max=100), allow_none=True)
    warranty_start = NullableDate(allow_none=True)
    warranty_end = NullableDate(allow_none=True)
    warranty_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    online_date = NullableDate(allow_none=True)
    offline_date = NullableDate(allow_none=True)
    lifecycle_years = fields.Int(validate=validate.Range(min=1, max=30), allow_none=True)
    ipmi_address = fields.Str(validate=validate.Length(max=50), allow_none=True)
    ipmi_username = fields.Str(validate=validate.Length(max=64), allow_none=True)
    ipmi_password = fields.Str(validate=validate.Length(max=255), allow_none=True)
    switch_config = fields.Dict(allow_none=True)
    node_hardware = fields.Dict(allow_none=True)
    storage_items = fields.List(fields.Dict(), load_default=[])
    nic_ports = fields.List(fields.Dict(), load_default=[])
    cpu_template_id    = fields.Integer(load_default=None)
    memory_template_id = fields.Integer(load_default=None)
    memory_dimm_count  = fields.Integer(load_default=None)
    gpu                = fields.Str(validate=validate.Length(max=200), allow_none=True)
    gpu_count          = fields.Integer(load_default=None, allow_none=True)
    gpu_template_id    = fields.Integer(load_default=None, allow_none=True)
    parent_device_name = fields.Str(validate=validate.Length(max=100), load_default=None)
    is_managed = fields.Bool(load_default=None, allow_none=True)
    ssh_ip = fields.Str(validate=validate.Length(max=45), load_default=None)
    ssh_port = fields.Int(load_default=None, allow_none=True)
    ssh_username = fields.Str(validate=validate.Length(max=64), load_default=None)
    ssh_password = fields.Str(validate=validate.Length(max=255), load_default=None)
    ssh_device_type = fields.Str(
        validate=validate.OneOf(
            [e.value for e in SwitchDeviceTypeCode],
            error=f"不支持的驱动类型：{{input}}。可选值：{'、'.join(e.value for e in SwitchDeviceTypeCode)}",
        ),
        load_default=None,
        allow_none=True,
    )
    ssh_protocol = fields.Str(
        validate=validate.OneOf(
            [e.value for e in SSHProtocolCode],
            error=f"不支持的连接协议：{{input}}。可选值：{'、'.join(e.value for e in SSHProtocolCode)}",
        ),
        load_default=None,
        allow_none=True,
    )
    switch_role = fields.Int(load_default=None, allow_none=True)
    port_num = fields.Int(load_default=None, allow_none=True)
