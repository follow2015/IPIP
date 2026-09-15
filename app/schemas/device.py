# -*- coding: utf-8 -*-
"""设备请求验证 Schema

从 app/api/device.py 拆分而来，供 API 层和 Service 层共同引用，
消除 service → api 的反向依赖。

约定：
- 新 Schema 一律定义在本包，不要在 app/api/ 下就地定义。
- 只在本文件内使用一次的 Schema 可继续留在 app/api/ 下，无需迁移。
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


_IMPORT_ONLY_FIELDS = (
    "ssh_ip",
    "ssh_port",
    "ssh_username",
    "ssh_password",
    "ssh_protocol",
    "ssh_device_type",
    "is_managed",
    "parent_device_name",
    "switch_role",
    "port_num",
)


class DeviceCreateApiSchema(DeviceCreateSchema):
    """HTTP 接口专用创建设备 Schema

    等于 DeviceCreateSchema 剔除 _IMPORT_ONLY_FIELDS 后的子集，
    字段集与原 app/api/device.py 中的本地定义严格一致（行为等价替换）。

    批量导入请使用完整的 DeviceCreateSchema。
    """

    class Meta(DeviceCreateSchema.Meta):
        unknown = EXCLUDE
        exclude = _IMPORT_ONLY_FIELDS



class DeviceUpdateSchema(Schema):
    """更新设备请求验证Schema"""

    class Meta:
        unknown = EXCLUDE  # 忽略未知字段

    id = fields.Int(dump_only=True)  # 只读，不参与验证
    device_name = fields.Str(validate=validate.Length(min=1, max=100), allow_none=True)
    cabinet_id = fields.Int(validate=validate.Range(min=1), allow_none=True)
    device_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    brand = fields.Str(validate=validate.Length(max=50), allow_none=True)
    device_model = fields.Str(validate=validate.Length(max=50), allow_none=True)
    serial_number = fields.Str(validate=validate.Length(max=100), allow_none=True)
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
    cpu_template_id    = fields.Integer(load_default=None)
    memory_template_id = fields.Integer(load_default=None)
    memory_dimm_count  = fields.Integer(load_default=None)
    gpu                = fields.Str(validate=validate.Length(max=200), allow_none=True)
    gpu_count          = fields.Integer(load_default=None, allow_none=True)
    gpu_template_id    = fields.Integer(load_default=None, allow_none=True)
    auto_create_nodes = fields.Bool(load_default=False)
    node_hardware = fields.Dict(allow_none=True)
    storage_items = fields.List(fields.Dict(), load_default=[])
    nic_ports = fields.List(fields.Dict(), load_default=[])
    overwrite_nodes = fields.Bool(load_default=False)
    metric_template_group_id = fields.Int(allow_none=True)


class BatchUpdateAssetSchema(Schema):
    """批量更新设备资产信息请求Schema"""

    class Meta:
        unknown = EXCLUDE

    ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))
    auto_generate_asset_number = fields.Bool(load_default=False)
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


class BatchResetAssetSchema(Schema):
    """批量重置设备资产信息请求Schema"""

    class Meta:
        unknown = EXCLUDE

    ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))


class BatchDeleteSchema(Schema):
    """批量删除请求Schema"""

    class Meta:
        unknown = EXCLUDE

    ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))




class DeviceRestoreSchema(Schema):
    """恢复已回收设备请求Schema（可选同时指定落位机柜与 U 位）"""

    class Meta:
        unknown = EXCLUDE

    cabinet_id = fields.Int(allow_none=True)
    u_position = fields.Int(allow_none=True)


class BatchRestoreDevicesSchema(Schema):
    """批量恢复设备请求Schema（device_ids 必填，落位信息可选）"""

    class Meta:
        unknown = EXCLUDE

    device_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))
    cabinet_id = fields.Int(allow_none=True)
    u_position = fields.Int(allow_none=True)


class BatchPermanentDeleteSchema(Schema):
    """批量永久删除请求Schema。

    注意字段名是 `device_ids` 而**不是** `ids`，故不能复用 `BatchDeleteSchema`
    （后者对应 `/batch-delete`，字段为 `ids`）。
    """

    class Meta:
        unknown = EXCLUDE

    device_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))


class BatchUpdateMetricTemplateGroupSchema(Schema):
    """批量设置设备监控模板组请求Schema"""

    class Meta:
        unknown = EXCLUDE

    device_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))
    metric_template_group_id = fields.Int(allow_none=True)


class BatchUpdatePortSyncEnabledSchema(Schema):
    """批量开关设备端口同步请求Schema（port_sync_enabled 必填）"""

    class Meta:
        unknown = EXCLUDE

    device_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))
    port_sync_enabled = fields.Bool(required=True)


class BatchUpdateDeviceConfigSchema(Schema):
    """批量修改设备配置请求Schema。

    除 `ids` 外的字段由 handler **动态透传**给 `device_service.batch_update_config`
    （`payload = {k: v for k, v in data.items() if k != "ids"}`），故此处只声明必填的
    `ids`；其余配置项不在契约内，避免把可变集合写死成文档。
    """

    class Meta:
        unknown = EXCLUDE

    ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))


class SwapNodePositionsSchema(Schema):
    """交换机箱内两个节点 U 位请求Schema"""

    class Meta:
        unknown = EXCLUDE

    source_position = fields.Int(required=True)
    target_position = fields.Int(required=True)


class PortLinkUpdateSchema(Schema):
    """更新端口互联请求Schema。

    handler 用白名单过滤（`allowed = {...}`），此处字段与白名单逐条对齐；
    请求体为空或无命中字段时返回 400「无有效更新字段」。
    """

    class Meta:
        unknown = EXCLUDE

    connection_type = fields.Str()
    vlan_id = fields.Int(allow_none=True)
    status = fields.Str()
    notes = fields.Str(allow_none=True)
    bandwidth = fields.Int(allow_none=True)
    description = fields.Str(allow_none=True)
    lag_group_id = fields.Int(allow_none=True)


class BatchUpdateDeviceStatusSchema(Schema):
    """批量更新设备状态请求Schema"""

    class Meta:
        unknown = EXCLUDE

    device_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))
    status = fields.Int(required=True, validate=validate.Range(min=0, max=7))


class BatchUpdateHardwareSchema(Schema):
    """批量更新设备硬件配置请求Schema"""

    class Meta:
        unknown = EXCLUDE

    ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))
    cpu = fields.Str(validate=validate.Length(max=100), allow_none=True)
    cpu_way = fields.Int(validate=validate.Range(min=1, max=8), allow_none=True)
    cpu_cores = fields.Int(validate=validate.Range(min=1), allow_none=True)
    cpu_template_id = fields.Int(allow_none=True)
    memory = fields.Str(validate=validate.Length(max=100), allow_none=True)
    memory_size_gb = fields.Int(validate=validate.Range(min=0), allow_none=True)
    memory_template_id = fields.Int(allow_none=True)
    gpu = fields.Str(validate=validate.Length(max=200), allow_none=True)
    gpu_count = fields.Int(allow_none=True)
    gpu_template_id = fields.Int(allow_none=True)
    storage_summary = fields.Str(validate=validate.Length(max=200), allow_none=True)
    os_version = fields.Str(validate=validate.Length(max=100), allow_none=True)
    ipmi_address = fields.Str(validate=validate.Length(max=50), allow_none=True)
    ipmi_username = fields.Str(validate=validate.Length(max=64), allow_none=True)
    ipmi_password = fields.Str(validate=validate.Length(max=255), allow_none=True)


class DeviceStatusUpdateSchema(Schema):
    """更新设备状态请求Schema"""

    class Meta:
        unknown = EXCLUDE

    status = fields.Int(required=True, validate=validate.Range(min=0, max=7))


class DeviceLocationUpdateSchema(Schema):
    """更新设备位置请求Schema"""

    class Meta:
        unknown = EXCLUDE

    cabinet_id = fields.Int(required=True, validate=validate.Range(min=1))
    u_position = fields.Int(validate=validate.Range(min=0), allow_none=True)
    height_u = fields.Int(validate=validate.Range(min=0, max=50), allow_none=True)


class SerialNumberGenerateSchema(Schema):
    """生成序列号请求Schema"""

    class Meta:
        unknown = EXCLUDE

    prefix = fields.Str(load_default="SN")
    format_type = fields.Str(load_default="numeric")
    length = fields.Int(load_default=8)


class SerialNumberCheckSchema(Schema):
    """检查序列号唯一性请求Schema"""

    class Meta:
        unknown = EXCLUDE

    serial_number = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    exclude_id = fields.Int(allow_none=True)


class NodePositionCheckSchema(Schema):
    """检查节点位置重复请求Schema"""

    class Meta:
        unknown = EXCLUDE

    chassis_id = fields.Int(required=True)
    node_position = fields.Int(required=True)
    exclude_device_id = fields.Int(allow_none=True)


class SwitchPortUpdateSchema(Schema):
    """更新交换机端口请求Schema"""
    class Meta:
        unknown = EXCLUDE
    port_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    port_name = fields.Str(validate=validate.Length(max=100), allow_none=True)
    speed = fields.Str(validate=validate.Length(max=20), allow_none=True)
    status = fields.Str(validate=validate.Length(max=20), allow_none=True)
    description = fields.Str(validate=validate.Length(max=200), allow_none=True)
    vlan = fields.Int(allow_none=True)


class BatchCreateSwitchPortsSchema(Schema):
    """批量创建交换机端口请求Schema"""
    class Meta:
        unknown = EXCLUDE
    device_id = fields.Int(required=True)
    ports = fields.List(fields.Dict(), required=True)


class BatchCreateDevicesSchema(Schema):
    """批量创建设备请求Schema"""
    class Meta:
        unknown = EXCLUDE
    devices = fields.List(fields.Dict(), required=True)


class DeviceVLANCreateSchema(Schema):
    """在设备上创建VLAN请求Schema"""
    class Meta:
        unknown = EXCLUDE
    vlan_id = fields.Int(required=True)
    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    purpose = fields.Str(validate=validate.Length(max=200), allow_none=True)
    subnet_id = fields.Int(allow_none=True)
    room_id = fields.Int(allow_none=True)
    status = fields.Int(allow_none=True)


class VLANMemberUpdateSchema(Schema):
    """更新VLAN成员端口请求Schema"""
    class Meta:
        unknown = EXCLUDE
    port_ids = fields.List(fields.Int(), required=True)


class VLANFieldUpdateSchema(Schema):
    """更新VLAN字段请求Schema"""
    class Meta:
        unknown = EXCLUDE
    purpose = fields.Str(validate=validate.Length(max=200), allow_none=True)
    name = fields.Str(validate=validate.Length(max=100), allow_none=True)


class LAGCreateSchema(Schema):
    """创建链路聚合组请求Schema"""
    class Meta:
        unknown = EXCLUDE
    lag_name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    lag_type = fields.Str(validate=validate.Length(max=50), allow_none=True)


class LAGMemberUpdateSchema(Schema):
    """更新LAG成员端口请求Schema"""
    class Meta:
        unknown = EXCLUDE
    port_ids = fields.List(fields.Int(), required=True)


class LAGFieldUpdateSchema(Schema):
    """更新链路聚合组字段请求Schema"""
    class Meta:
        unknown = EXCLUDE
    purpose = fields.Str(validate=validate.Length(max=200), allow_none=True)
