# -*- coding: utf-8 -*-
"""响应 Schema 定义

为每个模型定义响应 Marshmallow Schema，字段严格对齐 to_dict() 返回结构。
这些 Schema 注册到 APISpec 后，openapi-typescript 可自动生成完整的前端类型。
"""
from marshmallow import Schema, fields, validate



class ApiResponseSchema(Schema):
    """API 统一成功响应包装"""
    success = fields.Bool(dump_default=True)
    message = fields.Str()
    data = fields.Dict()  # 实际使用时通过 schema 参数指定具体类型
    timestamp = fields.Str()


class ApiErrorResponseSchema(Schema):
    """API 统一错误响应包装"""
    success = fields.Bool(dump_default=False)
    message = fields.Str()
    error_code = fields.Str()
    timestamp = fields.Str()


class PaginationMetaSchema(Schema):
    """分页元数据（已在 spec.py 中用 dict 注册，此处提供 Marshmallow 版本）"""
    page = fields.Int()
    per_page = fields.Int()
    total = fields.Int()
    total_pages = fields.Int()



class UserResponseSchema(Schema):
    """用户响应（对齐 User.to_dict()）"""
    id = fields.Int()
    username = fields.Str()
    email = fields.Str(allow_none=True)
    name = fields.Str()
    department = fields.Str(allow_none=True)
    contact_phone = fields.Str(allow_none=True)
    roles = fields.List(fields.Str())
    is_active = fields.Bool()
    real_name = fields.Str()
    status = fields.Int()
    created_at = fields.Str()
    updated_at = fields.Str()


class LoginDataResponseSchema(Schema):
    """登录响应数据（对齐 POST /auth/login）"""
    token = fields.Str()
    refresh_token = fields.Str()
    user = fields.Nested("LoginUserResponseSchema")
    permissions = fields.List(fields.Str())
    expires_in = fields.Int()


class LoginUserResponseSchema(Schema):
    """登录响应中的用户信息"""
    id = fields.Int()
    username = fields.Str()
    email = fields.Str(allow_none=True)
    name = fields.Str()
    roles = fields.List(fields.Str())
    is_active = fields.Bool()
    status = fields.Int()


class VerifyDataResponseSchema(Schema):
    """Token 验证响应（对齐 GET /auth/verify）"""
    valid = fields.Bool()
    user_id = fields.Int()
    username = fields.Str()
    email = fields.Str()
    roles = fields.List(fields.Str())



class RoomResponseSchema(Schema):
    """机房响应（对齐 Room.to_dict()）"""
    id = fields.Int()
    name = fields.Str()
    status = fields.Int()
    location = fields.Str(allow_none=True)
    contact = fields.Str(allow_none=True)
    contact_phone = fields.Str(allow_none=True)
    cabinet_count = fields.Int()
    created_at = fields.Str()
    updated_at = fields.Str()



class CabinetResponseSchema(Schema):
    """机柜响应（对齐 Cabinet.to_dict()）"""
    id = fields.Int()
    cabinet_number = fields.Str()
    room_id = fields.Int()
    location = fields.Str(allow_none=True)
    row = fields.Int(allow_none=True)
    col = fields.Int(allow_none=True)
    total_u = fields.Int()
    used_u = fields.Int()
    total_power = fields.Int(allow_none=True)
    used_power = fields.Int()
    max_weight = fields.Float(allow_none=True)
    status = fields.Int()
    customer_id = fields.Int(allow_none=True)
    notes = fields.Str(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()
    deleted_at = fields.Str(allow_none=True)
    available_u = fields.Int()
    room_name = fields.Str()
    room_location = fields.Str(allow_none=True)
    customer_name = fields.Str(allow_none=True)
    device_count = fields.Int()
    u_usage_rate = fields.Float()
    power_usage_rate = fields.Float()


class CabinetUtilizationResponseSchema(Schema):
    """机柜利用率"""
    total_u = fields.Int()
    used_u = fields.Int()
    available_u = fields.Int()
    usage_rate = fields.Float()



class SwitchCredentialEmbeddedSchema(Schema):
    """交换机凭据嵌入信息（Device.to_dict() 中聚合）"""
    id = fields.Int()
    ip = fields.Str()
    has_ssh = fields.Bool()
    switch_role = fields.Int()
    layer = fields.Int(allow_none=True)
    device_type = fields.Str(allow_none=True)
    port_num = fields.Int(allow_none=True)
    username = fields.Str(allow_none=True)
    protocol = fields.Str(allow_none=True)
    authentication_method = fields.Str(allow_none=True)
    uplink_device_id = fields.Int(allow_none=True)
    uplink_port_ids = fields.List(fields.Int(), allow_none=True)
    core_device_id = fields.Int(allow_none=True)
    room_id = fields.Int(allow_none=True)
    device_version = fields.Str(allow_none=True)
    device_uptime = fields.Str(allow_none=True)


class PortSummaryEmbeddedSchema(Schema):
    """端口汇总信息"""
    total = fields.Int()
    used = fields.Int()
    free = fields.Int()


class DeviceResponseSchema(Schema):
    """设备响应（对齐 Device.to_dict() — 1:1扩展表字段平铺）"""
    id = fields.Int()
    device_name = fields.Str()
    device_type = fields.Str()
    device_subtype = fields.Str(allow_none=True)
    device_model = fields.Str(allow_none=True)
    brand = fields.Str(allow_none=True)
    serial_number = fields.Str(allow_none=True)
    hostname = fields.Str(allow_none=True)
    management_ip = fields.Str(allow_none=True)
    mac_address = fields.Str(allow_none=True)
    metric_template_group_id = fields.Int(allow_none=True)
    cabinet_id = fields.Int(allow_none=True)
    u_position = fields.Int(allow_none=True)
    height_u = fields.Int()
    power = fields.Float(allow_none=True)
    parent_device_id = fields.Int(allow_none=True)
    is_chassis = fields.Bool()
    node_position = fields.Int(allow_none=True)
    node_row = fields.Int(allow_none=True)
    node_col = fields.Int(allow_none=True)
    total_nodes = fields.Int(allow_none=True)
    node_rows = fields.Int(allow_none=True)
    node_cols = fields.Int(allow_none=True)
    node_naming_pattern = fields.Str(allow_none=True)
    status = fields.Int()
    responsible_person = fields.Int(allow_none=True)
    customer_id = fields.Int(allow_none=True)
    notes = fields.Str(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()
    deleted_at = fields.Str(allow_none=True)
    cpu = fields.Str(allow_none=True)
    cpu_way = fields.Int(allow_none=True)
    cpu_cores = fields.Int(allow_none=True)
    memory = fields.Str(allow_none=True)
    memory_size_gb = fields.Int(allow_none=True)
    storage = fields.Str(allow_none=True)
    os_version = fields.Str(allow_none=True)
    ipmi_address = fields.Str(allow_none=True)
    ipmi_username = fields.Str(allow_none=True)
    has_ipmi_password = fields.Bool()
    ip_address = fields.Str(allow_none=True)
    storage_summary = fields.Str(allow_none=True)
    cpu_template_id = fields.Int(allow_none=True)
    memory_template_id = fields.Int(allow_none=True)
    memory_dimm_count = fields.Int(allow_none=True)
    gpu = fields.Str(allow_none=True)
    gpu_count = fields.Int(allow_none=True)
    gpu_template_id = fields.Int(allow_none=True)
    nic_component_template_id = fields.Int(allow_none=True)
    asset_number = fields.Str(allow_none=True)
    supplier = fields.Str(allow_none=True)
    supplier_contact = fields.Str(allow_none=True)
    contract_number = fields.Str(allow_none=True)
    purchase_date = fields.Str(allow_none=True)
    purchase_price = fields.Float(allow_none=True)
    invoice_number = fields.Str(allow_none=True)
    warranty_start = fields.Str(allow_none=True)
    warranty_end = fields.Str(allow_none=True)
    warranty_type = fields.Str(allow_none=True)
    online_date = fields.Str(allow_none=True)
    offline_date = fields.Str(allow_none=True)
    lifecycle_years = fields.Int(allow_none=True)
    cabinet_number = fields.Str(allow_none=True)
    status_name = fields.Str()
    customer_name = fields.Str(allow_none=True)
    room_id = fields.Int(allow_none=True)
    room_name = fields.Str(allow_none=True)
    responsible_person_name = fields.Str(allow_none=True)
    responsible_person_username = fields.Str(allow_none=True)
    parent_u_position = fields.Int(allow_none=True)
    parent_height_u = fields.Int(allow_none=True)
    parent_device_name = fields.Str(allow_none=True)
    switch_credential = fields.Nested(SwitchCredentialEmbeddedSchema, allow_none=True)
    port_summary = fields.Nested(PortSummaryEmbeddedSchema, allow_none=True)
    connected_device_count = fields.Int(allow_none=True)
    deleted_location_snapshot = fields.Dict(allow_none=True)
    deleted_children_snapshot = fields.List(fields.Dict(), allow_none=True)



class DeviceNicPortResponseSchema(Schema):
    """设备网卡端口（对齐 DeviceNicsPort.to_dict()）"""
    id = fields.Int()
    device_id = fields.Int()
    nic_number = fields.Int()
    port_number = fields.Int()
    port_name = fields.Str()
    port_type = fields.Str()
    port_speed = fields.Str()
    port_status = fields.Str()
    description = fields.Str(allow_none=True)
    template_id = fields.Int(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()
    display_name = fields.Str()
    full_info = fields.Str()
    device_name = fields.Str(allow_none=True)
    device_type = fields.Str(allow_none=True)


class DeviceConnectionResponseSchema(Schema):
    """设备连接（对齐 DeviceConnection.to_dict()）"""
    id = fields.Int()
    device_id = fields.Int()
    switch_device_id = fields.Int(allow_none=True)
    switch_port_id = fields.Int(allow_none=True)
    device_nics_port_id = fields.Int(allow_none=True)
    link_type = fields.Str()
    connection_type = fields.Str(allow_none=True)
    vlan_id = fields.Int(allow_none=True)
    status = fields.Str()
    notes = fields.Str(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()
    device_name = fields.Str()
    switch_name = fields.Str()
    source_nic_number = fields.Int(allow_none=True)
    source_port_number = fields.Int(allow_none=True)
    source_port_display = fields.Str(allow_none=True)
    device_nics_port_name = fields.Str(allow_none=True)
    port_type = fields.Str(allow_none=True)
    port_speed = fields.Str(allow_none=True)
    switch_port_name = fields.Str(allow_none=True)
    port_name = fields.Str(allow_none=True)
    peer_port_name = fields.Str(allow_none=True)
    peer_port_id = fields.Int(allow_none=True)
    peer_device_id = fields.Int(allow_none=True)
    peer_device_name = fields.Str(allow_none=True)
    peer_port_speed = fields.Str(allow_none=True)
    peer_port_type = fields.Str(allow_none=True)


class DeviceStorageResponseSchema(Schema):
    """设备存储详细（对齐 DeviceStorage.to_dict()）"""
    id = fields.Int()
    device_id = fields.Int()
    storage_type = fields.Str()
    capacity = fields.Str()
    capacity_gb = fields.Int()
    interface_type = fields.Str(allow_none=True)
    slot_number = fields.Int(allow_none=True)
    manufacturer = fields.Str(allow_none=True)
    model = fields.Str(allow_none=True)
    serial_number = fields.Str(allow_none=True)
    firmware = fields.Str(allow_none=True)
    status = fields.Str()
    template_id = fields.Int(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()



class CustomerResponseSchema(Schema):
    """客户响应（对齐 Customer.to_dict()）"""
    id = fields.Int()
    customer_name = fields.Str()
    customer_status = fields.Int()
    contact_person = fields.Str(allow_none=True)
    contact_phone = fields.Str(allow_none=True)
    email = fields.Str(allow_none=True)
    address = fields.Str(allow_none=True)
    notes = fields.Str(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()
    deleted_at = fields.Str(allow_none=True)



class IPAddressResponseSchema(Schema):
    """IP地址列表项（对齐 GET /ip_addresses — 5表JOIN扁平结果）"""
    ip_address = fields.Str()
    room_id = fields.Int(allow_none=True)
    mac_address = fields.Str()
    switch_name = fields.Str(allow_none=True)
    port = fields.Str(allow_none=True)
    room_name = fields.Str(allow_none=True)
    customer_id = fields.Int(allow_none=True)
    customer_name = fields.Str(allow_none=True)
    notes = fields.Str(allow_none=True)
    status = fields.Int()
    updated_at = fields.Str()


class IPAddressDetailResponseSchema(Schema):
    """IP地址详情（对齐 GET /ip/<address>）"""
    ip_address = fields.Str()
    room_id = fields.Int(allow_none=True)
    mac_address = fields.Str()
    switch_name = fields.Str(allow_none=True)
    switch_ip = fields.Str(allow_none=True)
    port = fields.Str(allow_none=True)
    room_name = fields.Str(allow_none=True)
    customer_name = fields.Str(allow_none=True)
    customer_id = fields.Int(allow_none=True)
    notes = fields.Str(allow_none=True)
    status = fields.Int()
    updated_at = fields.Str()



class SwitchResponseSchema(Schema):
    """交换机列表/详情（对齐 switch_credentials JOIN devices）"""
    id = fields.Int()
    device_id = fields.Int()
    name = fields.Str()
    ip_address = fields.Str()
    port = fields.Int(allow_none=True)
    username = fields.Str(allow_none=True)
    protocol = fields.Str(allow_none=True)
    device_type = fields.Str(allow_none=True)
    device_model = fields.Str(allow_none=True)
    switch_role = fields.Int()
    layer = fields.Int(allow_none=True)
    has_ssh = fields.Bool(allow_none=True)
    uplink_device_id = fields.Int(allow_none=True)
    room_id = fields.Int(allow_none=True)
    room_name = fields.Str(allow_none=True)
    device_version = fields.Str(allow_none=True)
    device_serial = fields.Str(allow_none=True)
    device_uptime = fields.Str(allow_none=True)
    authentication_method = fields.Str(allow_none=True)
    serial_number = fields.Str(allow_none=True)
    hostname = fields.Str(allow_none=True)
    port_num = fields.Int(allow_none=True)
    core_device_id = fields.Int(allow_none=True)
    uplink_device_name = fields.Str(allow_none=True)
    core_device_name = fields.Str(allow_none=True)
    uplink_port_ids = fields.List(fields.Int(), allow_none=True)
    uplink_port_names = fields.List(fields.Str(), allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()
    connected_device_count = fields.Int(allow_none=True)
    mac_address = fields.List(fields.Str(), allow_none=True)


class SwitchPortIPResponseSchema(Schema):
    """交换机端口IP"""
    id = fields.Int()
    switch_id = fields.Int()
    port = fields.Str()
    ip_address = fields.Str()
    subnet_mask = fields.Str()
    prefix = fields.Int(allow_none=True)
    is_primary = fields.Bool()
    updated_at = fields.Str()


class SwitchPortResponseSchema(Schema):
    """交换机端口"""
    id = fields.Int()
    port_name = fields.Str()
    usage_status = fields.Str()
    link_status = fields.Str(allow_none=True)
    vlan = fields.Int(allow_none=True)
    speed = fields.Str()
    mac_address = fields.Str(allow_none=True)
    ip_address = fields.Str(allow_none=True)
    notes = fields.Str(allow_none=True)
    port_info = fields.Str(allow_none=True)
    customer_id = fields.Int(allow_none=True)
    customer_name = fields.Str(allow_none=True)
    updated_at = fields.Str(allow_none=True)
    data_source = fields.Str(allow_none=True)
    last_collected_at = fields.Str(allow_none=True)
    max_speed = fields.Int(allow_none=True)
    ip_list = fields.List(fields.Nested(SwitchPortIPResponseSchema), allow_none=True)
    description = fields.Str(allow_none=True)
    port_type = fields.Str(allow_none=True)
    slot = fields.Int(allow_none=True)



class PermissionResponseSchema(Schema):
    """RBAC 权限（对齐 Permission.to_dict()）"""
    id = fields.Int()
    code = fields.Str()
    name = fields.Str()
    category = fields.Str(allow_none=True)
    description = fields.Str(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()


class RoleResponseSchema(Schema):
    """RBAC 角色（对齐 Role.to_dict()）"""
    id = fields.Int()
    name = fields.Str()
    display_name = fields.Str()
    description = fields.Str(allow_none=True)
    status = fields.Int()
    created_at = fields.Str()
    updated_at = fields.Str()
    permissions = fields.List(fields.Nested(PermissionResponseSchema), allow_none=True)
    user_count = fields.Int(allow_none=True)



class IPStatusGroupResponseSchema(Schema):
    """IP 状态分组统计"""
    total = fields.Int()
    active = fields.Int()
    inactive = fields.Int()
    blocked = fields.Int()
    unused = fields.Int()


class DashboardStatsResponseSchema(Schema):
    """仪表盘统计数据"""
    rooms = fields.Dict()
    cabinets = fields.Dict()
    devices = fields.Dict()
    networks = fields.Dict()
    customers = fields.Dict()
    switches = fields.Dict()
    percentages = fields.Dict()



class AuditLogResponseSchema(Schema):
    """审计日志（对齐 AuditLog.to_dict()）"""
    id = fields.Int()
    user_id = fields.Int(allow_none=True)
    action = fields.Str()
    resource = fields.Str()
    resource_id = fields.Int(allow_none=True)
    detail = fields.Dict(allow_none=True)
    ip_address = fields.Str(allow_none=True)
    created_at = fields.Str()



class VLANResponseSchema(Schema):
    """VLAN（对齐 VLAN.to_dict()）"""
    id = fields.Int()
    vlan_id = fields.Int()
    name = fields.Str()
    purpose = fields.Str(allow_none=True)
    subnet_id = fields.Int(allow_none=True)
    room_id = fields.Int(allow_none=True)
    room_name = fields.Str(allow_none=True)
    status = fields.Int()
    device_id = fields.Int()
    device_name = fields.Str(allow_none=True)
    member_ports = fields.List(fields.Str())
    created_at = fields.Str()
    updated_at = fields.Str()



class LinkAggregationGroupResponseSchema(Schema):
    """链路聚合组（对齐 LinkAggregationGroup.to_dict()）"""
    id = fields.Int()
    device_id = fields.Int()
    lag_name = fields.Str()
    lag_type = fields.Str()
    algorithm = fields.Str(allow_none=True)
    status = fields.Int()
    member_count = fields.Int()
    purpose = fields.Str()
    member_ports = fields.List(fields.Str())
    created_at = fields.Str()
    updated_at = fields.Str()



class IPNetworkResponseSchema(Schema):
    """网段记录（对齐 IPNetwork.to_dict() + 关联字段）"""
    id = fields.Int()
    ip_network = fields.Str()
    switch_id = fields.Int(allow_none=True)
    port = fields.Str(allow_none=True)
    customer_id = fields.Int(allow_none=True)
    nexthop = fields.Str(allow_none=True, metadata={"description": "下一跳IP(来自switch_routes关联注入)"})
    route_type = fields.Int(allow_none=True)
    notes = fields.Str(allow_none=True)
    room_id = fields.Int(allow_none=True)
    updated_at = fields.Str(allow_none=True)
    room_name = fields.Str(allow_none=True)
    customer_name = fields.Str(allow_none=True)
    switch_name = fields.Str(allow_none=True)



class DeviceConfigBackupResponseSchema(Schema):
    """设备配置备份"""
    id = fields.Int()
    device_id = fields.Int()
    config_content = fields.Str()
    config_hash = fields.Str()
    backup_type = fields.Str()
    file_size = fields.Int(allow_none=True)
    created_at = fields.Str()


class DeviceConfigChangeResponseSchema(Schema):
    """设备配置变更"""
    id = fields.Int()
    device_id = fields.Int()
    backup_id = fields.Int(allow_none=True)
    change_summary = fields.Str()
    change_detail = fields.Str(allow_none=True)
    status = fields.Str()
    requested_by = fields.Int()
    approved_by = fields.Int(allow_none=True)
    applied_at = fields.Str(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()



class TopologyNodeSchema(Schema):
    """拓扑节点"""
    id = fields.Int()
    name = fields.Str()
    device_type = fields.Str()
    switch_role = fields.Int(allow_none=True)
    layer = fields.Int(allow_none=True)
    status = fields.Str(allow_none=True)
    ip = fields.Str(allow_none=True)
    port_num = fields.Int(allow_none=True)
    uplink_device_id = fields.Int(allow_none=True)
    core_device_id = fields.Int(allow_none=True)
    room_id = fields.Int(allow_none=True)
    room_name = fields.Str(allow_none=True)
    cabinet_id = fields.Int(allow_none=True)
    cabinet_name = fields.Str(allow_none=True)


class TopologyEdgeSchema(Schema):
    """拓扑边"""
    id = fields.Str()
    source = fields.Int()
    target = fields.Int()
    edge_type = fields.Str()  # n2n / d2n / uplink
    connection_type = fields.Str(allow_none=True)
    bandwith = fields.Str(allow_none=True)
    bandwidth = fields.Str(allow_none=True)
    status = fields.Str(allow_none=True)
    local_port = fields.Str(allow_none=True)
    peer_port = fields.Str(allow_none=True)
    uplink_port_ids = fields.List(fields.Int(), allow_none=True)
    switch_port = fields.Str(allow_none=True)


class TopologyStatsSchema(Schema):
    """拓扑统计"""
    total_nodes = fields.Int()
    total_edges = fields.Int()
    core_count = fields.Int(allow_none=True)
    access_count = fields.Int(allow_none=True)
    online_count = fields.Int()
    offline_count = fields.Int()
    switch_count = fields.Int(allow_none=True)
    server_count = fields.Int(allow_none=True)
    n2n_count = fields.Int(allow_none=True)
    d2n_count = fields.Int(allow_none=True)


class TopologyResponseSchema(Schema):
    """拓扑响应"""
    nodes = fields.List(fields.Nested(TopologyNodeSchema))
    edges = fields.List(fields.Nested(TopologyEdgeSchema))
    stats = fields.Nested(TopologyStatsSchema)


class TopologyAutoDetectChangeFieldSchema(Schema):
    """自动推断字段变更"""
    old = fields.Raw(allow_none=True)
    new = fields.Raw(allow_none=True)


class TopologyAutoDetectChangeSchema(Schema):
    """自动推断变更项"""
    device_id = fields.Int()
    device_name = fields.Str()
    fields = fields.Dict(keys=fields.Str(), values=fields.Nested(TopologyAutoDetectChangeFieldSchema))


class TopologyAutoDetectResponseSchema(Schema):
    """自动推断响应"""
    changes = fields.List(fields.Nested(TopologyAutoDetectChangeSchema))
    dry_run = fields.Bool()


class VirtualRoomResponseSchema(Schema):
    """虚拟机房响应"""
    id = fields.Int()
    name = fields.Str()
    description = fields.Str(allow_none=True)
    member_count = fields.Int()
    members = fields.List(fields.Dict(), allow_none=True)
    created_at = fields.Str(allow_none=True)
    updated_at = fields.Str(allow_none=True)
    last_scan_at = fields.Str(allow_none=True)
    last_scan_scope = fields.Str(allow_none=True)



class MonitorStatusResponseSchema(Schema):
    """监控状态快照（对齐 DeviceMonitorStatus.to_dict()）"""
    id = fields.Int()
    device_id = fields.Int()
    protocol = fields.Str()
    reachable = fields.Bool()
    ever_reachable = fields.Bool()
    down_alerted = fields.Bool()
    down_episode = fields.Int()
    last_reachable_at = fields.Str(allow_none=True)
    last_unreachable_at = fields.Str(allow_none=True)
    last_checked_at = fields.Str()
    consecutive_failures = fields.Int()
    latency_ms = fields.Int(allow_none=True)
    extra = fields.Dict(allow_none=True)
    last_error = fields.Str(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()


class DeviceMonitorStatusResponseSchema(Schema):
    """GET /devices/<id>/status 完整响应"""
    monitored = fields.Bool()
    configured_protocols = fields.List(fields.Str())
    status = fields.Nested(MonitorStatusResponseSchema, allow_none=True)
    active_metric_alerts = fields.Int()
    max_alert_severity = fields.Int()
    monitor_interrupted = fields.Bool()


class MonitorCredentialConfigResponseSchema(Schema):
    """PUT /credentials 响应"""
    configured = fields.Bool()
    protocol = fields.Str()


class MonitorCredentialDeleteResponseSchema(Schema):
    """DELETE /credentials 响应"""
    deleted = fields.Bool()
    protocol = fields.Str()


class MonitorProbeResultResponseSchema(Schema):
    """POST /check 响应（ProbeResult 序列化）"""
    reachable = fields.Bool()
    latency_ms = fields.Int(allow_none=True)
    extra = fields.Dict(allow_none=True)
    error = fields.Str(allow_none=True)


class MonitorCredentialListItemSchema(Schema):
    """GET /credentials 列表项（不回显密文）"""
    id = fields.Int()
    name = fields.Str(allow_none=True)
    protocol = fields.Str()
    enabled = fields.Bool()
    linked_count = fields.Int()
    payload_meta = fields.Dict()


class MonitorCredentialCreateSchema(Schema):
    """POST /credentials 请求体"""
    protocol = fields.Str()
    payload = fields.Dict()
    name = fields.Str(required=True)
    device_ids = fields.List(fields.Int())



class MonitorCredentialPatchResponseSchema(Schema):
    """PATCH /credentials/<id> 响应（启用/停用/改名共享凭据）"""
    updated = fields.Bool()
    credential_id = fields.Int()


class MonitorOverviewRecentAlertSchema(Schema):
    """监控总览页最近告警项"""
    device_id = fields.Int()
    device_name = fields.Str(allow_none=True)
    device_type = fields.Str(allow_none=True)
    management_ip = fields.Str(allow_none=True)
    protocol = fields.Str(allow_none=True)
    episode = fields.Int()
    consecutive_failures = fields.Int()
    last_checked_at = fields.Str(allow_none=True)
    last_alerted_at = fields.Str(allow_none=True)
    re_alert_seq = fields.Int()
    alert_blindspot = fields.Bool()


class MonitorOverviewResponseSchema(Schema):
    """GET /overview 响应（全网监控态势）"""
    total_monitored = fields.Int()
    reachable = fields.Int()
    unreachable = fields.Int()
    flapping = fields.Int()
    never_reachable = fields.Int()
    alert_blindspot = fields.Int()
    alerting_devices = fields.Int()
    crit_alert_devices = fields.Int()
    warn_alert_devices = fields.Int()
    interrupted_devices = fields.Int()
    by_protocol = fields.Dict(keys=fields.Str(), values=fields.Int())
    by_device_type = fields.Dict(keys=fields.Str(), values=fields.Int())
    recent_alerts = fields.List(fields.Nested(MonitorOverviewRecentAlertSchema))


class MonitorStatusListItemSchema(Schema):
    """GET /statuses 列表项（联表设备展示字段）"""
    device_id = fields.Int()
    device_name = fields.Str(allow_none=True)
    device_type = fields.Str(allow_none=True)
    management_ip = fields.Str(allow_none=True)
    protocol = fields.Str(allow_none=True)
    reachable = fields.Bool()
    ever_reachable = fields.Bool()
    down_alerted = fields.Bool()
    down_episode = fields.Int()
    consecutive_failures = fields.Int()
    latency_ms = fields.Int(allow_none=True)
    last_checked_at = fields.Str(allow_none=True)
    last_reachable_at = fields.Str(allow_none=True)
    last_unreachable_at = fields.Str(allow_none=True)
    last_error = fields.Str(allow_none=True)
    alert_blindspot = fields.Bool()
    monitor_enabled = fields.Bool()
    active_metric_alerts = fields.Int()
    max_alert_severity = fields.Int()
    monitor_interrupted = fields.Bool()


class MonitorStatusListResponseSchema(Schema):
    """GET /statuses 响应（分页列表）"""
    data = fields.List(fields.Nested(MonitorStatusListItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class MonitorCheckBatchResponseSchema(Schema):
    """POST /check-batch 响应（批量探测结果）。

    results 为每台被探测设备的 ProbeResult 序列化；
    skipped 为因冷却 / 不存在而被跳过的设备 id 列表。
    """
    results = fields.List(fields.Dict(), allow_none=True)
    skipped = fields.List(fields.Int(), allow_none=True)


class MonitorCredentialPayloadUpdateResponseSchema(Schema):
    """PUT /credentials/<id>/payload 与 /devices/<id>/credentials/<cid>/payload 响应。

    updated_fields: 实际被修改的字段名；
    credential_migrated: 本次是否触发「迁移到新凭据行」（hash 与其它设备不同）。
    """

    id = fields.Int()
    protocol = fields.Str(allow_none=True)
    updated_fields = fields.List(fields.Str())
    credential_migrated = fields.Bool()


class MonitorConfigItemSchema(Schema):
    """单个配置项（GET /config 响应元素）。"""

    value = fields.Raw(allow_none=True)
    editable = fields.Bool()
    type = fields.Str()
    description = fields.Str()


class MonitorConfigResponseSchema(Schema):
    """GET /config 响应：每个配置项为 {value, editable, type, description} 对象。

    字段名 = 白名单 camel 别名（与 dynamic_config.KEY_TO_CAMEL 一致）。
    """

    consecutive_failures_threshold = fields.Nested(MonitorConfigItemSchema)
    realert_interval_minutes = fields.Nested(MonitorConfigItemSchema)
    fallback_role = fields.Nested(MonitorConfigItemSchema)
    blindspot_role = fields.Nested(MonitorConfigItemSchema)
    thread_pool_size = fields.Nested(MonitorConfigItemSchema)
    timeout_seconds = fields.Nested(MonitorConfigItemSchema)
    interval_snmp = fields.Nested(MonitorConfigItemSchema)
    interval_bmc = fields.Nested(MonitorConfigItemSchema)
    interval_zabbix = fields.Nested(MonitorConfigItemSchema)
    outbox_interval = fields.Nested(MonitorConfigItemSchema)
    worker_in_process = fields.Nested(MonitorConfigItemSchema)


class MonitorConfigUpdateResponseSchema(Schema):
    """PUT /config 响应。"""

    updated = fields.List(fields.Str())
    requires_restart = fields.List(fields.Str())


class MonitorAlertListItemSchema(Schema):
    """GET /alerts 列表项（outerjoin devices；设备删除后 device_* 为 None）。"""

    id = fields.Int()
    device_id = fields.Int(allow_none=True)
    device_name = fields.Str(allow_none=True)
    device_type = fields.Str(allow_none=True)
    management_ip = fields.Str(allow_none=True)
    alert_type = fields.Str()
    severity = fields.Str()
    dedup_key = fields.Str()
    payload_json = fields.Str(allow_none=True)
    status = fields.Str()
    attempts = fields.Int()
    last_error = fields.Str(allow_none=True)
    created_at = fields.Str(allow_none=True)
    sent_at = fields.Str(allow_none=True)
    acknowledged_by = fields.Str(allow_none=True)
    acknowledged_at = fields.Str(allow_none=True)
    ack_note = fields.Str(allow_none=True)
    closed_by = fields.Str(allow_none=True)
    closed_at = fields.Str(allow_none=True)
    close_reason = fields.Str(allow_none=True)


class MonitorAlertDetailSchema(Schema):
    """GET /alerts/<id> 详情（P1-6）：列表项 + payload 解析后的结构化对象。"""

    id = fields.Int()
    device_id = fields.Int(allow_none=True)
    device_name = fields.Str(allow_none=True)
    device_type = fields.Str(allow_none=True)
    management_ip = fields.Str(allow_none=True)
    alert_type = fields.Str()
    severity = fields.Str()
    dedup_key = fields.Str()
    payload_json = fields.Str(allow_none=True)
    payload = fields.Dict(allow_none=True)
    status = fields.Str()
    attempts = fields.Int()
    last_error = fields.Str(allow_none=True)
    created_at = fields.Str(allow_none=True)
    sent_at = fields.Str(allow_none=True)
    acknowledged_by = fields.Str(allow_none=True)
    acknowledged_at = fields.Str(allow_none=True)
    ack_note = fields.Str(allow_none=True)


class MonitorAlertAckResponseSchema(Schema):
    """POST /alerts/<id>/ack 响应（G9 人工确认/认领）"""

    id = fields.Int()
    acknowledged_by = fields.Str()
    acknowledged_at = fields.Str(allow_none=True)
    ack_note = fields.Str(allow_none=True)


class MonitorAlertBatchAckRequestSchema(Schema):
    """POST /alerts/batch-ack 请求"""

    alert_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1, max=500))
    note = fields.Str(allow_none=True)


class MonitorAlertBatchAckResponseSchema(Schema):
    """POST /alerts/batch-ack 响应"""

    acknowledged = fields.Int()
    not_found = fields.Int()


class MonitorAlertBatchRetryRequestSchema(Schema):
    """POST /alerts/batch-retry 请求"""

    alert_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1, max=500))


class MonitorAlertBatchRetryResponseSchema(Schema):
    """POST /alerts/batch-retry 响应"""

    retried = fields.Int()
    skipped = fields.Int()


class MonitorAlertCloseResponseSchema(Schema):
    """POST /alerts/<id>/close 响应（P2-16 manual_close）"""

    id = fields.Int()
    closed_by = fields.Str(allow_none=True)
    closed_at = fields.Str(allow_none=True)
    close_reason = fields.Str(allow_none=True)


class MonitorAlertBatchCloseRequestSchema(Schema):
    """POST /alerts/batch-close 请求（P2-16）"""

    alert_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1, max=500))
    reason = fields.Str(allow_none=True)


class MonitorAlertBatchCloseResponseSchema(Schema):
    """POST /alerts/batch-close 响应（P2-16）"""

    closed = fields.Int()
    not_found = fields.Int()


class MonitorAlertAggregationItemSchema(Schema):
    """P2-10: 告警聚合组"""

    alert_type = fields.Str()
    severity = fields.Str()
    device_id = fields.Int(allow_none=True)
    device_name = fields.Str(allow_none=True)
    count = fields.Int()
    first_at = fields.Str(allow_none=True)
    last_at = fields.Str(allow_none=True)
    window_minutes = fields.Int()
    sample_ids = fields.List(fields.Int())
    root_device_id = fields.Int(allow_none=True)


class MonitorAlertAggregationResponseSchema(Schema):
    """GET /alerts/aggregations 响应（P2-10）"""

    data = fields.List(fields.Nested(MonitorAlertAggregationItemSchema))


class MonitorAlertListResponseSchema(Schema):
    """GET /alerts 响应（分页列表）"""

    data = fields.List(fields.Nested(MonitorAlertListItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class MonitorAlertRetryResponseSchema(Schema):
    """POST /alerts/<id>/retry 响应"""

    retried = fields.Bool()
    alert_id = fields.Int()
    status = fields.Str()


class MonitorIncidentItemSchema(Schema):
    """GET /incidents 列表项（对齐 MonitorIncident.to_dict()）"""

    id = fields.Int()
    incident_key = fields.Str()
    title = fields.Str()
    severity = fields.Str()
    status = fields.Str()
    reason_code = fields.Str(allow_none=True)
    root_device_id = fields.Int(allow_none=True)
    alert_count = fields.Int()
    device_count = fields.Int()
    first_alert_at = fields.Str(allow_none=True)
    last_alert_at = fields.Str(allow_none=True)
    closed_at = fields.Str(allow_none=True)


class MonitorIncidentListResponseSchema(Schema):
    """GET /incidents 响应（分页列表）"""

    data = fields.List(fields.Nested(MonitorIncidentItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class MonitorIncidentSuppressedLogSchema(Schema):
    """事件详情中被抑制的下游设备留痕项"""

    id = fields.Int()
    device_id = fields.Int(allow_none=True)
    alert_type = fields.Str()
    severity = fields.Str()
    reason_code = fields.Str()
    upstream_device_id = fields.Int(allow_none=True)
    incident_id = fields.Int(allow_none=True)
    created_at = fields.Str(allow_none=True)


class MonitorIncidentDetailResponseSchema(Schema):
    """GET /incidents/<id> 响应（详情含关联告警 + 被抑制下游设备）"""

    id = fields.Int()
    incident_key = fields.Str()
    title = fields.Str()
    severity = fields.Str()
    status = fields.Str()
    reason_code = fields.Str(allow_none=True)
    root_device_id = fields.Int(allow_none=True)
    alert_count = fields.Int()
    device_count = fields.Int()
    first_alert_at = fields.Str(allow_none=True)
    last_alert_at = fields.Str(allow_none=True)
    closed_at = fields.Str(allow_none=True)
    related_alerts = fields.List(fields.Dict())
    suppressed_logs = fields.List(fields.Nested(MonitorIncidentSuppressedLogSchema))


class MonitorDeviceMonitorEnabledResponseSchema(Schema):
    """PATCH /devices/<id>/monitor-enabled 响应"""

    device_id = fields.Int()
    monitor_enabled = fields.Bool()



class MonitorProbeHistoryItemSchema(Schema):
    """单条探测历史（对齐 DeviceMonitorProbeEvents.to_dict()）"""

    id = fields.Int()
    device_id = fields.Int()
    protocol = fields.Str()
    reachable = fields.Bool()
    latency_ms = fields.Int(allow_none=True)
    consecutive_failures = fields.Int()
    episode = fields.Int()
    is_alert = fields.Bool()
    error = fields.Str(allow_none=True)
    extra = fields.Dict(allow_none=True)
    probed_at = fields.Str()
    created_at = fields.Str()


class MonitorProbeHistoryResponseSchema(Schema):
    """GET /devices/<id>/history 响应（时间升序明细）"""

    items = fields.List(fields.Nested(MonitorProbeHistoryItemSchema))
    total = fields.Int()
    from_ = fields.Str(allow_none=True, data_key="from")
    to = fields.Str(allow_none=True)
    protocol = fields.Str(allow_none=True)


class MonitorProbeTrendsResponseSchema(Schema):
    """GET /devices/<id>/trends 响应（聚合统计，供趋势卡片）"""

    total = fields.Int()
    reachable = fields.Int()
    unreachable = fields.Int()
    uptime_pct = fields.Float(allow_none=True)
    avg_latency_ms = fields.Float(allow_none=True)
    min_latency_ms = fields.Int(allow_none=True)
    max_latency_ms = fields.Int(allow_none=True)
    p95_latency_ms = fields.Int(allow_none=True)
    latency_samples = fields.Int()
    down_episodes = fields.Int()


class DeviceMetricAlertStateItemSchema(Schema):
    """GET /monitor/devices/<id>/metric-alerts 响应项"""

    id = fields.Int()
    device_id = fields.Int()
    metric_key = fields.Str()
    index_key = fields.Str()
    alert_type = fields.Str()
    breached = fields.Bool()
    severity = fields.Str(allow_none=True)
    last_value = fields.Str(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()


class DeviceMetricAlertListResponseSchema(Schema):
    """GET /monitor/devices/<id>/metric-alerts 响应"""

    items = fields.List(fields.Nested(DeviceMetricAlertStateItemSchema))




class MetricTemplateItemSchema(Schema):
    """GET /monitor/metric-templates 响应项"""

    id = fields.Int()
    metric_key = fields.Str()
    category = fields.Str(allow_none=True)
    display_name = fields.Str(allow_none=True)
    device_type = fields.Str()
    source = fields.Str()
    vendor = fields.Str(allow_none=True, metadata={"description": "厂家约束（品牌厂商），可空"})
    mib = fields.Str(allow_none=True)
    oid_symbol = fields.Str(allow_none=True)
    oid = fields.Str(allow_none=True)
    zabbix_item_key = fields.Str(allow_none=True, metadata={"description": "Zabbix item key，source=zabbix 时必填"})
    index_kind = fields.Str(allow_none=True)
    metric_type = fields.Str()
    unit = fields.Str(allow_none=True)
    poll_interval = fields.Int()
    threshold = fields.Dict(allow_none=True)
    severity_default = fields.Str(allow_none=True)
    enabled = fields.Bool()
    description = fields.Str(allow_none=True)
    runbook_url = fields.Str(allow_none=True, metadata={"description": "处置预案 URL（P2-14）"})
    runbook_title = fields.Str(allow_none=True, metadata={"description": "处置预案标题（P2-14）"})


class MetricTemplateListResponseSchema(Schema):
    """GET /monitor/metric-templates 响应"""

    data = fields.List(fields.Nested(MetricTemplateItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class MetricTemplateUpsertResponseSchema(Schema):
    """PUT /monitor/metric-templates 响应"""

    id = fields.Int()
    metric_key = fields.Str()
    device_type = fields.Str()


class MetricTemplateSeedResponseSchema(Schema):
    """POST /monitor/metric-templates/seed 响应"""

    created = fields.Int()


class MetricTemplateDeleteResponseSchema(Schema):
    """DELETE /monitor/metric-templates/<id> 响应"""

    deleted = fields.Int()


class MetricTemplateBatchDeleteResponseSchema(Schema):
    """DELETE /monitor/metric-templates/batch 响应

    与单删端点不同，批量删除额外返回 total（请求条数），
    便于前端区分「请求 10 条实际删掉 7 条」的部分成功场景。
    """
    deleted = fields.Int()
    total = fields.Int()


class MetricTemplateBatchToggleResponseSchema(Schema):
    """PATCH /monitor/metric-templates/batch-enabled 响应

    此前误用 MetricTemplateDeleteResponse（只有 deleted 字段），
    契约与实际返回 {updated,total,enabled} 完全不匹配。
    """
    updated = fields.Int()
    total = fields.Int()
    enabled = fields.Bool()


class MonitorCredentialBatchDeleteFailureSchema(Schema):
    """批量删除凭据中单条的失败明细"""
    id = fields.Int()
    reason = fields.Str(metadata={"description": "失败原因（不存在 / 仍关联 N 台设备 / 异常信息）"})


class MonitorCredentialBatchDeleteResponseSchema(Schema):
    """POST /monitor/credentials/batch-delete 响应

    部分成功语义：deleted 为成功条数，failed 逐条给出失败原因，
    前端据此展示明细而非静默吞掉失败。
    """
    deleted = fields.Int()
    failed = fields.List(fields.Nested(MonitorCredentialBatchDeleteFailureSchema))




class DeviceTrafficResponseSchema(Schema):
    """GET /monitor/devices/<id>/traffic 响应"""

    port = fields.Str(allow_none=True)
    time = fields.List(fields.Int())
    rx_bps = fields.List(fields.Int())
    tx_bps = fields.List(fields.Int())
    configured = fields.Bool()


class DeviceTrafficPortItemSchema(Schema):
    """端口流量 item"""
    port = fields.Str()
    rx_itemid = fields.Str()
    tx_itemid = fields.Str()
    rx_value_type = fields.Int()
    tx_value_type = fields.Int()


class DeviceTrafficPortsResponseSchema(Schema):
    """GET /monitor/devices/<id>/traffic/ports 响应"""
    ports = fields.List(fields.Nested(DeviceTrafficPortItemSchema))
    configured = fields.Bool()
    error = fields.Str(allow_none=True, metadata={"description": "凭据解密/拉取失败原因：credential_error / fetch_error"})


class OidCategoryRuleItemSchema(Schema):
    """OID 分类规则项"""

    id = fields.Int()
    prefix = fields.Str()
    category = fields.Str()
    label = fields.Str(allow_none=True)
    device_type = fields.Str(allow_none=True)
    vendor_id = fields.Str(allow_none=True)
    priority = fields.Int()
    enabled = fields.Bool()


class OidCategoryRuleListResponseSchema(Schema):
    """GET /monitor/oid-category-rules 响应"""

    data = fields.List(fields.Nested(OidCategoryRuleItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class OidCategoryRuleMutationResponseSchema(Schema):
    """POST/PATCH/DELETE /monitor/oid-category-rules 响应"""

    id = fields.Int()


class DeviceTypeRecommendItemSchema(Schema):
    """设备类型推荐配置项"""

    id = fields.Int()
    device_type = fields.Str()
    categories = fields.List(fields.Str())


class DeviceTypeRecommendListResponseSchema(Schema):
    """GET /monitor/device-type-recommends 响应"""

    data = fields.List(fields.Nested(DeviceTypeRecommendItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class RecommendConfigResponseSchema(Schema):
    """GET /monitor/mib-scan/recommend-config 响应"""

    device_type = fields.Str()
    categories = fields.List(fields.Str())


class VendorBrandItemSchema(Schema):
    """厂商品牌项"""

    id = fields.Int()
    enterprise_no = fields.Str()
    brand_name = fields.Str()
    label = fields.Str()
    device_type = fields.Str()
    enabled = fields.Bool()
    sort_order = fields.Int()


class VendorBrandListResponseSchema(Schema):
    """GET /monitor/vendor-brands 响应"""

    data = fields.List(fields.Nested(VendorBrandItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class VendorBrandMutationResponseSchema(Schema):
    """POST/PATCH/DELETE /monitor/vendor-brands 响应"""

    id = fields.Int()


class MibScanResponseSchema(Schema):
    """POST /monitor/mib-scan 响应"""

    device_ip = fields.Str()
    oid_count = fields.Int()
    type_summary = fields.Dict()
    category_summary = fields.Dict()
    detected = fields.List(fields.Dict())
    hint = fields.Str()


class MonitorSilenceRuleItemSchema(Schema):
    """静默规则项"""

    id = fields.Int()
    name = fields.Str()
    device_ids = fields.List(fields.Int(), allow_none=True)
    alert_type = fields.List(fields.Str(), allow_none=True)
    silence_from = fields.Str()
    silence_until = fields.Str()
    reason = fields.Str(allow_none=True)
    created_by = fields.Str(allow_none=True)
    enabled = fields.Bool()
    created_at = fields.Str()


class MonitorAlertDependencyRuleItemSchema(Schema):
    """P2-17: 告警依赖抑制规则项"""

    id = fields.Int()
    name = fields.Str()
    upstream_device_id = fields.Int()
    downstream_device_id = fields.Int()
    alert_types = fields.List(fields.Str(), allow_none=True)
    reason = fields.Str(allow_none=True)
    enabled = fields.Bool()
    created_at = fields.Str()


class MonitorSlaTargetItemSchema(Schema):
    """P2-13: SLA 目标项"""

    id = fields.Int()
    name = fields.Str()
    target_device_ids = fields.List(fields.Int())
    target_ratio = fields.Float()
    window_days = fields.Int()
    description = fields.Str(allow_none=True)
    enabled = fields.Bool()
    created_at = fields.Str()


class MonitorSlaAchievementSchema(Schema):
    """P2-13: SLA 达成度报表"""

    target_id = fields.Int()
    name = fields.Str()
    target_ratio = fields.Float()
    actual_ratio = fields.Float(allow_none=True)
    sample_count = fields.Int()
    met_sla = fields.Bool()
    window_start = fields.Str()
    window_end = fields.Str()


class MonitorAlertStatisticsResponseSchema(Schema):
    """P2-15: 告警统计报表响应"""

    class _SummarySchema(Schema):
        total = fields.Int()
        active = fields.Int()
        acknowledged = fields.Int()
        closed = fields.Int()
        failed = fields.Int()

    class _CountItemSchema(Schema):
        count = fields.Int()

    class _SeverityItemSchema(Schema):
        severity = fields.Str()
        count = fields.Int()

    class _TypeItemSchema(Schema):
        alert_type = fields.Str()
        count = fields.Int()

    class _StatusItemSchema(Schema):
        status = fields.Str()
        count = fields.Int()

    class _DeviceItemSchema(Schema):
        device_id = fields.Int(allow_none=True)
        device_name = fields.Str(allow_none=True)
        count = fields.Int()

    class _DensityItemSchema(Schema):
        bucket_start = fields.Str()
        count = fields.Int()

    summary = fields.Nested(_SummarySchema)
    by_severity = fields.List(fields.Nested(_SeverityItemSchema))
    by_type = fields.List(fields.Nested(_TypeItemSchema))
    by_status = fields.List(fields.Nested(_StatusItemSchema))
    mttr_seconds = fields.Float(allow_none=True)
    ack_rate = fields.Float()
    close_rate = fields.Float()
    top_devices = fields.List(fields.Nested(_DeviceItemSchema))
    top_types = fields.List(fields.Nested(_TypeItemSchema))
    density = fields.List(fields.Nested(_DensityItemSchema))


class MonitorEscalationStepItemSchema(Schema):
    """P2-11: 升级链步骤项"""

    id = fields.Int()
    policy_id = fields.Int()
    step_no = fields.Int()
    wait_minutes = fields.Int()
    escalate_severity = fields.Str(allow_none=True)
    escalate_to_role_id = fields.Int(allow_none=True)
    escalate_webhook_url = fields.Str(allow_none=True)
    enabled = fields.Bool()
    created_at = fields.Str()
    updated_at = fields.Str()


class MonitorEscalationPolicyItemSchema(Schema):
    """升级策略项"""

    id = fields.Int()
    name = fields.Str()
    alert_type = fields.Str(allow_none=True)
    severity = fields.Str(allow_none=True)
    wait_minutes = fields.Int()
    escalate_severity = fields.Str(allow_none=True)
    escalate_to_role_id = fields.Int(allow_none=True)
    escalate_webhook_url = fields.Str(allow_none=True)
    repeat_minutes = fields.Int()
    enabled = fields.Bool()
    steps = fields.List(fields.Nested(MonitorEscalationStepItemSchema))
    created_at = fields.Str()
    updated_at = fields.Str()


class DeviceMetricOverrideItemSchema(Schema):
    """设备级阈值覆盖项"""

    id = fields.Int()
    device_id = fields.Int()
    metric_key = fields.Str()
    threshold = fields.Dict()
    enabled = fields.Bool()
    note = fields.Str(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()




class MetricTemplateGroupItemSchema(Schema):
    """GET /monitor/metric-template-groups 响应项"""

    id = fields.Int()
    name = fields.Str()
    device_type = fields.Str()
    source = fields.Str()
    vendor = fields.Str(allow_none=True)
    display_order = fields.Int()
    enabled = fields.Bool()
    description = fields.Str(allow_none=True)
    template_count = fields.Int(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()


class MetricTemplateGroupListResponseSchema(Schema):
    data = fields.List(fields.Nested(MetricTemplateGroupItemSchema))


class MetricTemplateGroupDetailResponseSchema(Schema):
    """GET /monitor/metric-template-groups/<id> 响应（含组内模板）"""

    id = fields.Int()
    name = fields.Str()
    device_type = fields.Str()
    source = fields.Str()
    vendor = fields.Str(allow_none=True)
    display_order = fields.Int()
    enabled = fields.Bool()
    description = fields.Str(allow_none=True)
    templates = fields.List(fields.Nested(MetricTemplateItemSchema))
    created_at = fields.Str()
    updated_at = fields.Str()


class MetricTemplateGroupMutationResponseSchema(Schema):
    """模板组增删改响应"""

    id = fields.Int(allow_none=True)
    name = fields.Str(allow_none=True)
    added = fields.Bool(allow_none=True)
    removed = fields.Bool(allow_none=True)
    deleted = fields.Bool(allow_none=True)
    skipped = fields.Int(allow_none=True)




class DeviceMetricLatestItemSchema(Schema):
    """GET /monitor/devices/<id>/metric-latest 响应项"""

    id = fields.Int()
    device_id = fields.Int()
    metric_key = fields.Str()
    index_key = fields.Str()
    value = fields.Str(allow_none=True)
    severity = fields.Str(allow_none=True)
    breached = fields.Bool()
    collected_at = fields.Str()


class DeviceMetricLatestListResponseSchema(Schema):
    """GET /monitor/devices/<id>/metric-latest 响应"""

    items = fields.List(fields.Nested(DeviceMetricLatestItemSchema))


class DeviceMetricHistoryItemSchema(Schema):
    """GET /monitor/devices/<id>/metrics/<metric_key>/history 响应项"""

    id = fields.Int()
    device_id = fields.Int()
    metric_key = fields.Str()
    index_key = fields.Str()
    value = fields.Str(allow_none=True)
    severity = fields.Str(allow_none=True)
    breached = fields.Bool()
    collected_at = fields.Str()


class DeviceMetricHistoryResponseSchema(Schema):
    """GET /monitor/devices/<id>/metrics/<metric_key>/history 响应"""

    items = fields.List(fields.Nested(DeviceMetricHistoryItemSchema))
    total = fields.Int()
    from_ = fields.Str(data_key="from", allow_none=True)
    to = fields.Str(allow_none=True)
    index_key = fields.Str(allow_none=True)


class DeviceMetricKeysResponseSchema(Schema):
    """GET /monitor/devices/<id>/metric-keys 响应（设备有历史时序的 metric_key 列表）"""

    items = fields.List(fields.Str())


class DeviceMetricDashboardItemSchema(Schema):
    """GET /monitor/devices/<id>/metric-dashboard 指标状态项"""

    metric_key = fields.Str()
    metric_name = fields.Str()
    source = fields.Str(allow_none=True)
    value = fields.Str(allow_none=True)
    severity = fields.Str(allow_none=True)
    breached = fields.Bool()
    collected_at = fields.Str(allow_none=True)


class DeviceMetricDashboardResponseSchema(Schema):
    """GET /monitor/devices/<id>/metric-dashboard 响应"""

    device_id = fields.Int()
    has_credential = fields.Bool()
    has_zabbix = fields.Bool()
    configured_protocols = fields.List(fields.Str())
    template_group = fields.Dict(allow_none=True)
    grouped = fields.Bool()
    metric_status = fields.List(fields.Nested(DeviceMetricDashboardItemSchema))
    overall_status = fields.Str()
    status_reason = fields.Str(allow_none=True, metadata={"description": "整体状态中文说明，供前端直接展示"})
    reachable = fields.Bool(allow_none=True)
    last_error = fields.Str(allow_none=True)
    last_checked_at = fields.Str(allow_none=True)



class DevicePortSyncEnabledResponseSchema(Schema):
    """GET /devices/<id>/port-sync-enabled 响应"""

    port_sync_enabled = fields.Bool(allow_none=True, metadata={"description": "设备级开关：null=跟随全局"})
    global_enabled = fields.Bool(metadata={"description": "全局开关当前值"})
    effective_enabled = fields.Bool(metadata={"description": "实际生效值"})


class DevicePortSyncEnabledUpdateResponseSchema(Schema):
    """PUT /devices/<id>/port-sync-enabled 响应"""

    port_sync_enabled = fields.Bool(allow_none=True, metadata={"description": "更新后的设备级开关值"})


class DeviceBatchPortSyncEnabledResponseSchema(Schema):
    """POST /devices/batch-port-sync-enabled 响应"""

    updated = fields.Int()
    with_credential = fields.Int()
    without_credential = fields.Int()
    non_network = fields.Int()
    skipped = fields.Int()



class AISkillSummarySchema(Schema):
    """AI 技能元数据"""
    name = fields.Str()
    title = fields.Str()
    description = fields.Str()
    category = fields.Str()
    version = fields.Int()
    params = fields.List(fields.Dict())
    triggers = fields.List(fields.Str())
    source = fields.Str()
    enabled = fields.Bool()


class AISkillsListResponseSchema(Schema):
    """GET /ai/skills 响应 data"""
    skills = fields.List(fields.Nested(AISkillSummarySchema))


class AISkillRunRequestSchema(Schema):
    """POST /ai/skills/<name>/run 请求体"""
    args = fields.Dict(metadata={"description": "技能参数，按技能定义的 params 传入"})


class AIAskRequestSchema(Schema):
    """POST /ai/ask 请求体"""
    question = fields.Str(required=True, validate=validate.Length(max=2000),
                          metadata={"description": "自然语言问题（≤2000 字）"})


class AIAskResponseSchema(Schema):
    """POST /ai/ask 响应 data"""
    answer = fields.Str()


class AIHealthResponseSchema(Schema):
    """GET /ai/health 响应 data"""
    configured = fields.Bool()


class AIRagIngestRequestSchema(Schema):
    """POST /ai/rag/ingest 请求体"""
    docs_dir = fields.Str(metadata={"description": "文档目录（必须在 AI_DOCS_ROOT 之下）"})


class AIRagIngestResponseSchema(Schema):
    """POST /ai/rag/ingest 响应 data"""
    task_id = fields.Str()


class AIConfigResponseSchema(Schema):
    """GET /ai/config 响应 data"""
    provider = fields.Str()
    base_url = fields.Str()
    model = fields.Str()
    timeout = fields.Int()
    stream_timeout = fields.Int()
    max_tokens = fields.Int()
    temperature = fields.Float()
    api_key_masked = fields.Str()
    api_key_configured = fields.Bool()


class AIConfigUpdateRequestSchema(Schema):
    """PUT /ai/config 请求体"""
    provider = fields.Str(allow_none=True)
    base_url = fields.Str(allow_none=True)
    model = fields.Str(allow_none=True)
    timeout = fields.Int(allow_none=True, validate=validate.Range(min=1, max=600))
    stream_timeout = fields.Int(allow_none=True, validate=validate.Range(min=1, max=600))
    max_tokens = fields.Int(allow_none=True, validate=validate.Range(min=1, max=32768))
    temperature = fields.Float(allow_none=True, validate=validate.Range(min=0.0, max=2.0))
    api_key = fields.Str(allow_none=True)


class AICircuitStatusResponseSchema(Schema):
    """GET /ai/circuit 响应 data"""
    providers = fields.Dict()


class AIMetricsResponseSchema(Schema):
    """GET /ai/metrics 响应 data

    M2 修复：对齐 get_metrics() 真实返回结构。
    两种分支：
    - Prometheus 可用时：{"raw": str}（exposition 格式文本）
    - Prometheus 不可用时：{"ai_tokens_total": int, "ai_errors_total": int, "ai_skill_runs_total": int}
    所有字段可选（partial），适配两种分支。
    """
    raw = fields.String(required=False, metadata={"description": "Prometheus exposition 格式文本（有 prometheus_client 时）"})
    ai_tokens_total = fields.Integer(required=False, metadata={"description": "AI token 总消耗（无 Prometheus 时扁平计数）"})
    ai_errors_total = fields.Integer(required=False, metadata={"description": "AI 调用错误总数"})
    ai_skill_runs_total = fields.Integer(required=False, metadata={"description": "AI 技能执行总数"})



class AIRagStatusResponseSchema(Schema):
    """GET /ai/rag/status 响应 data"""
    available = fields.Bool()
    doc_count = fields.Int()


class AIRagDocSchema(Schema):
    """RAG 文档单项"""
    doc_id = fields.Str()
    preview = fields.Str()


class AIRagDocsListResponseSchema(Schema):
    """GET /ai/rag/docs 响应 data"""
    docs = fields.List(fields.Nested(AIRagDocSchema))


class AIRagQaRequestSchema(Schema):
    """POST /ai/rag/qa 请求体"""
    question = fields.Str(required=True, validate=validate.Length(min=1, max=2000))


class AIRagQaResponseSchema(Schema):
    """POST /ai/rag/qa 响应 data"""
    answer = fields.Str()


class AIRagResetRequestSchema(Schema):
    """POST /ai/rag/reset 请求体"""
    confirm = fields.Bool(required=True)



class VoiceConfigSchema(Schema):
    """GET /api/settings/voice 响应 data（对齐前端 VoiceConfig interface）"""
    provider = fields.Str(validate=validate.OneOf(["aliyun", "tencent"]))
    aliyun_access_key_id = fields.Str()
    aliyun_access_key_secret = fields.Str()  # 脱敏值 "****" 或空
    aliyun_access_key_secret_set = fields.Bool()
    aliyun_caller_number = fields.Str()
    aliyun_tts_code = fields.Str()
    aliyun_tts_param = fields.Str()
    tencent_secret_id = fields.Str()
    tencent_secret_key = fields.Str()  # 脱敏值 "****" 或空
    tencent_secret_key_set = fields.Bool()
    tencent_app_id = fields.Str()
    tencent_template_id = fields.Str()
    play_times = fields.Int()
    volume = fields.Int()
    speed = fields.Int()
    call_timeout = fields.Int()
    callback_token = fields.Str()  # 脱敏值 "****" 或空
    callback_token_set = fields.Bool()
    callback_verify_mode = fields.Str(validate=validate.OneOf(["ip_only", "signature_and_ip", "off"]))
    enabled = fields.Bool()


class VoiceChannelStatusSchema(Schema):
    """GET /api/settings/voice/status 响应 data"""
    enabled = fields.Bool()
    provider = fields.Str()
    ready = fields.Bool()
    missing = fields.List(fields.Str())
    supports_ack = fields.Bool()
    error = fields.Str(allow_none=True)

