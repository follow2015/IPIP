# -*- coding: utf-8 -*-
"""交换机请求验证 Schema（T3.1：`switch_routes` 20 个写路由的 request_body 契约）。

字段来源：逐条取自各 handler 实际读取的 body（`data.get` / `data.pop` / `data[...]`），
**不按接口名臆测**。约定同 `app/schemas/device.py`：

- 契约只声明 **handler 确实读取的字段**；未声明的动态字段仍会透传（如设备创建时
  透传给 `switch_credentials` 的扩展列），这是刻意的"最小声明"而非遗漏。
- 类型以 `switch_credentials` 的真实列为准（`ip` / `port` / `username` / `password` /
  `protocol` / `authentication_method` / `device_type` / `has_ssh` / `mac_address`）。

**20 个写路由中另有 7 个不读请求体**（action 端点，路径参数即可决定行为），
故**有意不声明** `request_body`，理由与 `POST /device/clone/<id>` 相同：
`sync_switch_ports` / `scan_switch` / `scan_room` / `collect_switch_info` /
`sync_members` / `enable_port` / `disable_port`。
"""
from marshmallow import Schema, fields, validate, EXCLUDE

_CREDENTIAL_FIELDS = ("ip", "port", "username", "password", "protocol",
                      "authentication_method", "device_type", "has_ssh", "mac_address")
_DEVICE_FIELDS = ("name", "device_model", "cabinet_id", "u_position", "height_u",
                  "status", "customer_id", "room_id")
_EXT_FIELDS = ("uplink_device_id", "core_device_id", "uplink_port_ids", "port_num",
               "hostname", "switch_role", "layer")
_FRONTEND_EXT_FIELDS = ("ip_address", "room_name")


class SwitchCreateSchema(Schema):
    """创建交换机（`POST /switch/`）。

    `ip` 为必填：它既是凭据唯一数据源，也是 `name` 缺省时的回退设备名
    （`device_name or data.get("ip", "")`）。
    """
    class Meta:
        unknown = EXCLUDE

    ip = fields.Str(required=True, validate=validate.Length(max=45))
    port = fields.Int(load_default=22)
    username = fields.Str(validate=validate.Length(max=64))
    password = fields.Str()
    protocol = fields.Str(load_default="ssh")
    authentication_method = fields.Str()
    device_type = fields.Str()
    has_ssh = fields.Bool(load_default=True)
    mac_address = fields.Str(validate=validate.Length(max=17))

    name = fields.Str()
    device_model = fields.Str()
    cabinet_id = fields.Int(allow_none=True)
    u_position = fields.Int(allow_none=True)
    height_u = fields.Int(allow_none=True)
    status = fields.Str(allow_none=True)
    customer_id = fields.Int(allow_none=True)
    room_id = fields.Int(allow_none=True)

    uplink_device_id = fields.Int(allow_none=True)
    core_device_id = fields.Int(allow_none=True)
    uplink_port_ids = fields.List(fields.Int(), allow_none=True)
    port_num = fields.Int(allow_none=True)
    hostname = fields.Str(allow_none=True)
    switch_role = fields.Int(allow_none=True)   # 0/1：见 create_switch_ext 的 is_core→switch_role 映射
    layer = fields.Int(allow_none=True)

    ip_address = fields.Str(allow_none=True)    # 前端扩展，handler pop 后丢弃
    room_name = fields.Str(allow_none=True)     # 同上


class SwitchUpdateSchema(Schema):
    """更新交换机（`PUT /switch/<int:device_id>`）。

    全部字段可选（部分更新）；字段集合与创建一致，便于前端复用同一表单类型。
    """
    class Meta:
        unknown = EXCLUDE

    ip = fields.Str(validate=validate.Length(max=45))
    port = fields.Int()
    username = fields.Str(validate=validate.Length(max=64))
    password = fields.Str()
    protocol = fields.Str()
    authentication_method = fields.Str()
    device_type = fields.Str()
    has_ssh = fields.Bool()
    mac_address = fields.Str(validate=validate.Length(max=17))

    name = fields.Str()
    device_model = fields.Str()
    cabinet_id = fields.Int(allow_none=True)
    u_position = fields.Int(allow_none=True)
    height_u = fields.Int(allow_none=True)
    status = fields.Str(allow_none=True)
    customer_id = fields.Int(allow_none=True)
    room_id = fields.Int(allow_none=True)

    uplink_device_id = fields.Int(allow_none=True)
    core_device_id = fields.Int(allow_none=True)
    uplink_port_ids = fields.List(fields.Int(), allow_none=True)
    port_num = fields.Int(allow_none=True)
    hostname = fields.Str(allow_none=True)
    switch_role = fields.Int(allow_none=True)
    layer = fields.Int(allow_none=True)

    ip_address = fields.Str(allow_none=True)
    room_name = fields.Str(allow_none=True)


class SwitchPortInfoUpdateSchema(Schema):
    """更新端口信息（`PUT /switch/<int:device_id>/ports/<path:port_number>`）。

    handler 只读取 `description`（其余为响应字段，非请求体）。
    """
    class Meta:
        unknown = EXCLUDE

    description = fields.Str(allow_none=True)


class SwitchPortActionSchema(Schema):
    """单端口动作（`POST /switch/<int:device_id>/ports/action`）。

    `params` 为动态操作参数（如 `detail_op_type`、VLAN/速率等），按动作类型透传。
    """
    class Meta:
        unknown = EXCLUDE

    action = fields.Str(required=True)
    port = fields.Str(load_default="")
    params = fields.Dict(load_default=dict)


class SwitchBatchPortActionSchema(Schema):
    """批量端口动作（`POST /switch/<int:device_id>/ports/batch-action`）。

    `ports`（显式列表）与 `port_range`（范围表达式）二选一提供。
    """
    class Meta:
        unknown = EXCLUDE

    action = fields.Str(required=True)
    ports = fields.List(fields.Str(), load_default=list)
    port_range = fields.Str(load_default="")
    params = fields.Dict(load_default=dict)


class SwitchPortSpeedSetSchema(Schema):
    """设置端口速率（`POST .../ports/<path:port_number>/speed`）。"""
    class Meta:
        unknown = EXCLUDE

    inbound_speed = fields.Int(load_default=0)
    outbound_speed = fields.Int(load_default=0)


class SwitchPortVlanSetSchema(Schema):
    """设置端口 VLAN（`POST .../ports/<path:port_number>/vlan`）。"""
    class Meta:
        unknown = EXCLUDE

    vlan_id = fields.Int(required=True)
    mode = fields.Str(load_default="access")


class SwitchPortTrunkMemberAddSchema(Schema):
    """把端口加入聚合组（`POST .../port-channels/<int:trunk_id>/ports`）。

    `trunk_id` 来自路径参数；请求体只携带成员端口名。
    """
    class Meta:
        unknown = EXCLUDE

    port = fields.Str(required=True)


class SwitchPortIpSetSchema(Schema):
    """设置端口 IP（`POST .../ports/<path:port_number>/ip`）。"""
    class Meta:
        unknown = EXCLUDE

    ip_address = fields.Str(required=True)
    subnet_mask = fields.Str(allow_none=True)
    is_secondary = fields.Bool(load_default=False)


class SwitchPortChannelCreateSchema(Schema):
    """创建聚合口（`POST /switch/<int:device_id>/port-channels`）。"""
    class Meta:
        unknown = EXCLUDE

    channel_id = fields.Int(required=True)
    member_ports = fields.List(fields.Str(), load_default=list)


class _SwitchExtFieldsMixin:
    """`create_switch_ext` / `update_switch_ext` 共用字段。

    含**兼容旧字段名**（前端过渡期，handler 内 `_FIELD_MAP` 映射）：
    `is_core`→`switch_role`、`uplink_sw_id`→`uplink_device_id`、`core_sw_id`→`core_device_id`。
    """
    has_ssh = fields.Bool(allow_none=True)
    layer = fields.Int(allow_none=True)
    switch_role = fields.Int(allow_none=True)
    uplink_device_id = fields.Int(allow_none=True)
    core_device_id = fields.Int(allow_none=True)
    uplink_port_ids = fields.List(fields.Int(), allow_none=True)
    is_core = fields.Bool(allow_none=True)
    uplink_sw_id = fields.Int(allow_none=True)
    core_sw_id = fields.Int(allow_none=True)


class SwitchExtCreateSchema(_SwitchExtFieldsMixin, Schema):
    """创建交换机扩展信息（`POST /switch/<int:device_id>/ext`）。"""
    class Meta:
        unknown = EXCLUDE


class SwitchExtUpdateSchema(_SwitchExtFieldsMixin, Schema):
    """更新交换机扩展信息（`PUT /switch/<int:device_id>/ext`）。

    `has_ssh=False` 且 `uplink_*` 有值时，handler 会自动写 Redis fallback。
    """
    class Meta:
        unknown = EXCLUDE


class BatchUpdateSwitchesSchema(Schema):
    """批量更新交换机（`PUT /switch/batch-update`）。

    `updates` 为动态字段字典（handler 直接透传给批量更新逻辑）；
    `layer` / `password` / `switch_role` 为 handler 另外读取的顶层字段。
    """
    class Meta:
        unknown = EXCLUDE

    device_ids = fields.List(fields.Int(), required=True)
    updates = fields.Dict(required=True)
    layer = fields.Int(allow_none=True)
    password = fields.Str(allow_none=True)
    switch_role = fields.Int(allow_none=True)
