# -*- coding: utf-8 -*-
"""响应 Schema 定义

为每个模型定义响应 Marshmallow Schema，字段严格对齐 to_dict() 返回结构。
这些 Schema 注册到 APISpec 后，openapi-typescript 可自动生成完整的前端类型。
"""
from marshmallow import Schema, fields, validate


class ApiResponseSchema(Schema):
    success = fields.Bool(dump_default=True)
    message = fields.Str()
    data = fields.Dict()
    timestamp = fields.Str()


class ApiErrorResponseSchema(Schema):
    success = fields.Bool(dump_default=False)
    message = fields.Str()
    error_code = fields.Str()
    timestamp = fields.Str()


class PaginationMetaSchema(Schema):
    page = fields.Int()
    per_page = fields.Int()
    total = fields.Int()
    total_pages = fields.Int()


class UserResponseSchema(Schema):
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
    token = fields.Str()
    refresh_token = fields.Str()
    user = fields.Nested("LoginUserResponseSchema")
    permissions = fields.List(fields.Str())
    expires_in = fields.Int()


class LoginUserResponseSchema(Schema):
    id = fields.Int()
    username = fields.Str()
    email = fields.Str(allow_none=True)
    name = fields.Str()
    roles = fields.List(fields.Str())
    is_active = fields.Bool()
    status = fields.Int()


class VerifyDataResponseSchema(Schema):
    valid = fields.Bool()
    user_id = fields.Int()
    username = fields.Str()
    email = fields.Str()
    roles = fields.List(fields.Str())


class RoomResponseSchema(Schema):
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
    total_u = fields.Int()
    used_u = fields.Int()
    available_u = fields.Int()
    usage_rate = fields.Float()


class SwitchCredentialEmbeddedSchema(Schema):
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
    total = fields.Int()
    used = fields.Int()
    free = fields.Int()


class DeviceResponseSchema(Schema):
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
    ip_address = fields.Str()
    mac_address = fields.Str()
    switch_name = fields.Str(allow_none=True)
    port = fields.Str(allow_none=True)
    room_name = fields.Str(allow_none=True)
    customer_name = fields.Str(allow_none=True)
    notes = fields.Str(allow_none=True)
    status = fields.Int()
    updated_at = fields.Str()


class IPAddressDetailResponseSchema(Schema):
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
    id = fields.Int()
    switch_id = fields.Int()
    port = fields.Str()
    ip_address = fields.Str()
    subnet_mask = fields.Str()
    prefix = fields.Int(allow_none=True)
    is_primary = fields.Bool()
    updated_at = fields.Str()


class SwitchPortResponseSchema(Schema):
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
    id = fields.Int()
    code = fields.Str()
    name = fields.Str()
    category = fields.Str(allow_none=True)
    description = fields.Str(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()


class RoleResponseSchema(Schema):
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
    total = fields.Int()
    active = fields.Int()
    inactive = fields.Int()
    blocked = fields.Int()
    unused = fields.Int()


class DashboardStatsResponseSchema(Schema):
    rooms = fields.Dict()
    cabinets = fields.Dict()
    devices = fields.Dict()
    networks = fields.Dict()
    customers = fields.Dict()
    switches = fields.Dict()
    percentages = fields.Dict()


class AuditLogResponseSchema(Schema):
    id = fields.Int()
    user_id = fields.Int(allow_none=True)
    action = fields.Str()
    resource = fields.Str()
    resource_id = fields.Int(allow_none=True)
    detail = fields.Dict(allow_none=True)
    ip_address = fields.Str(allow_none=True)
    created_at = fields.Str()


class VLANResponseSchema(Schema):
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
    id = fields.Int()
    device_id = fields.Int()
    config_content = fields.Str()
    config_hash = fields.Str()
    backup_type = fields.Str()
    file_size = fields.Int(allow_none=True)
    created_at = fields.Str()


class DeviceConfigChangeResponseSchema(Schema):
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
    id = fields.Str()
    source = fields.Int()
    target = fields.Int()
    edge_type = fields.Str()
    connection_type = fields.Str(allow_none=True)
    bandwith = fields.Str(allow_none=True)
    bandwidth = fields.Str(allow_none=True)
    status = fields.Str(allow_none=True)
    local_port = fields.Str(allow_none=True)
    peer_port = fields.Str(allow_none=True)
    uplink_port_ids = fields.List(fields.Int(), allow_none=True)
    switch_port = fields.Str(allow_none=True)


class TopologyStatsSchema(Schema):
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
    nodes = fields.List(fields.Nested(TopologyNodeSchema))
    edges = fields.List(fields.Nested(TopologyEdgeSchema))
    stats = fields.Nested(TopologyStatsSchema)


class TopologyAutoDetectChangeFieldSchema(Schema):
    old = fields.Raw(allow_none=True)
    new = fields.Raw(allow_none=True)


class TopologyAutoDetectChangeSchema(Schema):
    device_id = fields.Int()
    device_name = fields.Str()
    fields = fields.Dict(keys=fields.Str(), values=fields.Nested(TopologyAutoDetectChangeFieldSchema))


class TopologyAutoDetectResponseSchema(Schema):
    changes = fields.List(fields.Nested(TopologyAutoDetectChangeSchema))
    dry_run = fields.Bool()


class VirtualRoomResponseSchema(Schema):
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
    monitored = fields.Bool()
    configured_protocols = fields.List(fields.Str())
    status = fields.Nested(MonitorStatusResponseSchema, allow_none=True)
    active_metric_alerts = fields.Int()
    max_alert_severity = fields.Int()
    monitor_interrupted = fields.Bool()


class MonitorCredentialConfigResponseSchema(Schema):
    configured = fields.Bool()
    protocol = fields.Str()


class MonitorCredentialDeleteResponseSchema(Schema):
    deleted = fields.Bool()
    protocol = fields.Str()


class MonitorProbeResultResponseSchema(Schema):
    reachable = fields.Bool()
    latency_ms = fields.Int(allow_none=True)
    extra = fields.Dict(allow_none=True)
    error = fields.Str(allow_none=True)


class MonitorCredentialListItemSchema(Schema):
    id = fields.Int()
    name = fields.Str(allow_none=True)
    protocol = fields.Str()
    enabled = fields.Bool()
    linked_count = fields.Int()
    payload_meta = fields.Dict()


class MonitorCredentialCreateSchema(Schema):
    protocol = fields.Str()
    payload = fields.Dict()
    name = fields.Str(required=True)
    device_ids = fields.List(fields.Int())


class MonitorCredentialPatchResponseSchema(Schema):
    updated = fields.Bool()
    credential_id = fields.Int()


class MonitorOverviewRecentAlertSchema(Schema):
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
    data = fields.List(fields.Nested(MonitorStatusListItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class MonitorCheckBatchResponseSchema(Schema):
    results = fields.List(fields.Dict(), allow_none=True)
    skipped = fields.List(fields.Int(), allow_none=True)


class MonitorCredentialPayloadUpdateResponseSchema(Schema):

    id = fields.Int()
    protocol = fields.Str(allow_none=True)
    updated_fields = fields.List(fields.Str())
    credential_migrated = fields.Bool()


class MonitorConfigItemSchema(Schema):

    value = fields.Raw(allow_none=True)
    editable = fields.Bool()
    type = fields.Str()
    description = fields.Str()


class MonitorConfigResponseSchema(Schema):

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

    updated = fields.List(fields.Str())
    requires_restart = fields.List(fields.Str())


class MonitorAlertListItemSchema(Schema):

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

    id = fields.Int()
    acknowledged_by = fields.Str()
    acknowledged_at = fields.Str(allow_none=True)
    ack_note = fields.Str(allow_none=True)


class MonitorAlertBatchAckRequestSchema(Schema):

    alert_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1, max=500))
    note = fields.Str(allow_none=True)


class MonitorAlertBatchAckResponseSchema(Schema):

    acknowledged = fields.Int()
    not_found = fields.Int()


class MonitorAlertBatchRetryRequestSchema(Schema):

    alert_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1, max=500))


class MonitorAlertBatchRetryResponseSchema(Schema):

    retried = fields.Int()
    skipped = fields.Int()


class MonitorAlertCloseResponseSchema(Schema):

    id = fields.Int()
    closed_by = fields.Str(allow_none=True)
    closed_at = fields.Str(allow_none=True)
    close_reason = fields.Str(allow_none=True)


class MonitorAlertBatchCloseRequestSchema(Schema):

    alert_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1, max=500))
    reason = fields.Str(allow_none=True)


class MonitorAlertBatchCloseResponseSchema(Schema):

    closed = fields.Int()
    not_found = fields.Int()


class MonitorAlertAggregationItemSchema(Schema):

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

    data = fields.List(fields.Nested(MonitorAlertAggregationItemSchema))


class MonitorAlertListResponseSchema(Schema):

    data = fields.List(fields.Nested(MonitorAlertListItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class MonitorAlertRetryResponseSchema(Schema):

    retried = fields.Bool()
    alert_id = fields.Int()
    status = fields.Str()


class MonitorDeviceMonitorEnabledResponseSchema(Schema):

    device_id = fields.Int()
    monitor_enabled = fields.Bool()


class MonitorProbeHistoryItemSchema(Schema):

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

    items = fields.List(fields.Nested(MonitorProbeHistoryItemSchema))
    total = fields.Int()
    from_ = fields.Str(allow_none=True, data_key="from")
    to = fields.Str(allow_none=True)
    protocol = fields.Str(allow_none=True)


class MonitorProbeTrendsResponseSchema(Schema):

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

    items = fields.List(fields.Nested(DeviceMetricAlertStateItemSchema))


class MetricTemplateItemSchema(Schema):

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

    data = fields.List(fields.Nested(MetricTemplateItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class MetricTemplateUpsertResponseSchema(Schema):

    id = fields.Int()
    metric_key = fields.Str()
    device_type = fields.Str()


class MetricTemplateSeedResponseSchema(Schema):

    created = fields.Int()


class MetricTemplateDeleteResponseSchema(Schema):

    deleted = fields.Int()


class DeviceTrafficResponseSchema(Schema):

    port = fields.Str(allow_none=True)
    time = fields.List(fields.Int())
    rx_bps = fields.List(fields.Int())
    tx_bps = fields.List(fields.Int())
    configured = fields.Bool()


class DeviceTrafficPortItemSchema(Schema):
    port = fields.Str()
    rx_itemid = fields.Str()
    tx_itemid = fields.Str()
    rx_value_type = fields.Int()
    tx_value_type = fields.Int()


class DeviceTrafficPortsResponseSchema(Schema):
    ports = fields.List(fields.Nested(DeviceTrafficPortItemSchema))
    configured = fields.Bool()
    error = fields.Str(allow_none=True, metadata={"description": "凭据解密/拉取失败原因：credential_error / fetch_error"})


class OidCategoryRuleItemSchema(Schema):

    id = fields.Int()
    prefix = fields.Str()
    category = fields.Str()
    label = fields.Str(allow_none=True)
    device_type = fields.Str(allow_none=True)
    vendor_id = fields.Str(allow_none=True)
    priority = fields.Int()
    enabled = fields.Bool()


class OidCategoryRuleListResponseSchema(Schema):

    data = fields.List(fields.Nested(OidCategoryRuleItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class OidCategoryRuleMutationResponseSchema(Schema):

    id = fields.Int()


class DeviceTypeRecommendItemSchema(Schema):

    id = fields.Int()
    device_type = fields.Str()
    categories = fields.List(fields.Str())


class DeviceTypeRecommendListResponseSchema(Schema):

    data = fields.List(fields.Nested(DeviceTypeRecommendItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class RecommendConfigResponseSchema(Schema):

    device_type = fields.Str()
    categories = fields.List(fields.Str())


class VendorBrandItemSchema(Schema):

    id = fields.Int()
    enterprise_no = fields.Str()
    brand_name = fields.Str()
    label = fields.Str()
    device_type = fields.Str()
    enabled = fields.Bool()
    sort_order = fields.Int()


class VendorBrandListResponseSchema(Schema):

    data = fields.List(fields.Nested(VendorBrandItemSchema))
    pagination = fields.Nested(PaginationMetaSchema)


class VendorBrandMutationResponseSchema(Schema):

    id = fields.Int()


class MibScanResponseSchema(Schema):

    device_ip = fields.Str()
    oid_count = fields.Int()
    type_summary = fields.Dict()
    category_summary = fields.Dict()
    detected = fields.List(fields.Dict())
    hint = fields.Str()


class MonitorSilenceRuleItemSchema(Schema):

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

    id = fields.Int()
    name = fields.Str()
    upstream_device_id = fields.Int()
    downstream_device_id = fields.Int()
    alert_types = fields.List(fields.Str(), allow_none=True)
    reason = fields.Str(allow_none=True)
    enabled = fields.Bool()
    created_at = fields.Str()


class MonitorSlaTargetItemSchema(Schema):

    id = fields.Int()
    name = fields.Str()
    target_device_ids = fields.List(fields.Int())
    target_ratio = fields.Float()
    window_days = fields.Int()
    description = fields.Str(allow_none=True)
    enabled = fields.Bool()
    created_at = fields.Str()


class MonitorSlaAchievementSchema(Schema):

    target_id = fields.Int()
    name = fields.Str()
    target_ratio = fields.Float()
    actual_ratio = fields.Float(allow_none=True)
    sample_count = fields.Int()
    met_sla = fields.Bool()
    window_start = fields.Str()
    window_end = fields.Str()


class MonitorAlertStatisticsResponseSchema(Schema):

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

    id = fields.Int()
    device_id = fields.Int()
    metric_key = fields.Str()
    threshold = fields.Dict()
    enabled = fields.Bool()
    note = fields.Str(allow_none=True)
    created_at = fields.Str()
    updated_at = fields.Str()


class MetricTemplateGroupItemSchema(Schema):

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

    id = fields.Int(allow_none=True)
    name = fields.Str(allow_none=True)
    added = fields.Bool(allow_none=True)
    removed = fields.Bool(allow_none=True)
    deleted = fields.Bool(allow_none=True)
    skipped = fields.Int(allow_none=True)


class DeviceMetricLatestItemSchema(Schema):

    id = fields.Int()
    device_id = fields.Int()
    metric_key = fields.Str()
    index_key = fields.Str()
    value = fields.Str(allow_none=True)
    severity = fields.Str(allow_none=True)
    breached = fields.Bool()
    collected_at = fields.Str()


class DeviceMetricLatestListResponseSchema(Schema):

    items = fields.List(fields.Nested(DeviceMetricLatestItemSchema))


class DeviceMetricHistoryItemSchema(Schema):

    id = fields.Int()
    device_id = fields.Int()
    metric_key = fields.Str()
    index_key = fields.Str()
    value = fields.Str(allow_none=True)
    severity = fields.Str(allow_none=True)
    breached = fields.Bool()
    collected_at = fields.Str()


class DeviceMetricHistoryResponseSchema(Schema):

    items = fields.List(fields.Nested(DeviceMetricHistoryItemSchema))
    total = fields.Int()
    from_ = fields.Str(data_key="from", allow_none=True)
    to = fields.Str(allow_none=True)
    index_key = fields.Str(allow_none=True)


class DeviceMetricKeysResponseSchema(Schema):

    items = fields.List(fields.Str())


class DeviceMetricDashboardItemSchema(Schema):

    metric_key = fields.Str()
    metric_name = fields.Str()
    source = fields.Str(allow_none=True)
    value = fields.Str(allow_none=True)
    severity = fields.Str(allow_none=True)
    breached = fields.Bool()
    collected_at = fields.Str(allow_none=True)


class DeviceMetricDashboardResponseSchema(Schema):

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

    port_sync_enabled = fields.Bool(allow_none=True, metadata={"description": "设备级开关：null=跟随全局"})
    global_enabled = fields.Bool(metadata={"description": "全局开关当前值"})
    effective_enabled = fields.Bool(metadata={"description": "实际生效值"})


class DevicePortSyncEnabledUpdateResponseSchema(Schema):

    port_sync_enabled = fields.Bool(allow_none=True, metadata={"description": "更新后的设备级开关值"})


class DeviceBatchPortSyncEnabledResponseSchema(Schema):

    updated = fields.Int()
    with_credential = fields.Int()
    without_credential = fields.Int()
    non_network = fields.Int()
    skipped = fields.Int()
