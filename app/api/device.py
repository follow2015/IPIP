# -*- coding: utf-8 -*-
"""
设备API

提供设备管理的RESTful API端点。
"""
from app.utils.logging import get_logger
from flask import Blueprint, request, g
import hashlib
from marshmallow import Schema, fields, validate, EXCLUDE, pre_load


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

logger = get_logger(__name__)

from app.openapi.doc import doc, public
from app.services import DeviceService, CabinetService
from app.services.network_device_service import NetworkDeviceService
from app.api.monitor import monitor_service
from app.api.base import APIResponse
from app.utils import (
    login_required,
    permission_required,
    rate_limit_api,
    validation_manager,
)
from app.utils.transactional import transactional
from app.persistence.cabinet_repository import CabinetRepository
from app.persistence.device_repository import DeviceRepository
from app.persistence.vlan_repository import VLANRepository
from app.persistence.link_aggregation_repository import LinkAggregationRepository
from app.persistence.switch_port_repository import NetworkPortRepository
from app.core.enums import NotificationTypeCode

device_bp = Blueprint("device", __name__)
device_service = DeviceService(DeviceRepository())
cabinet_service = CabinetService(CabinetRepository())


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


@device_bp.route("/", methods=["GET"])
@doc(summary="获取设备列表", tags=["设备"], parameters=[{"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "per_page", "in": "query", "schema": {"type": "integer", "default": 20}}, {"name": "search", "in": "query", "schema": {"type": "string"}}, {"name": "cabinet_id", "in": "query", "schema": {"type": "integer"}}, {"name": "room_id", "in": "query", "schema": {"type": "integer"}}, {"name": "customer_id", "in": "query", "schema": {"type": "integer"}}, {"name": "device_type", "in": "query", "schema": {"type": "string"}}, {"name": "device_subtype", "in": "query", "schema": {"type": "string"}}, {"name": "status", "in": "query", "schema": {"type": "integer"}}, {"name": "parent_device_id", "in": "query", "schema": {"type": "integer"}}, {"name": "is_chassis", "in": "query", "schema": {"type": "integer"}}, {"name": "has_ssh", "in": "query", "schema": {"type": "string"}}], responses={200: "DeviceResponse", 500: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def list_devices():
    """获取设备列表（支持分页、搜索过滤）

    Query Parameters:
        page: 页码（默认1）
        per_page: 每页数量（默认20）
        search: 搜索关键词，模糊匹配设备名/序列号/资产标签/管理IP等（可选）
        cabinet_id: 按机柜ID过滤（可选）
        room_id: 按机房ID过滤（可选，通过机柜关联）
        customer_id: 按客户ID过滤（可选）
        device_type: 按设备主类型过滤（可选）
        device_subtype: 按设备子类型过滤（可选）
        status: 按状态过滤（可选）
        parent_device_id: 按父设备ID过滤（可选）
        is_chassis: 按是否为机箱过滤（可选，1=机箱，0=非机箱）
        has_ssh: 按是否有SSH管理权限过滤（可选，true/false，仅网络设备有效）
    """
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search = request.args.get("search", type=str)
    cabinet_id = request.args.get("cabinet_id", type=int)
    room_id = request.args.get("room_id", type=int)
    customer_id = request.args.get("customer_id", type=int)
    device_type = request.args.get("device_type")
    device_subtype = request.args.get("device_subtype")
    parent_device_id = request.args.get("parent_device_id", type=int)
    is_chassis = request.args.get("is_chassis", type=int)
    has_ssh = request.args.get("has_ssh", type=str)

    try:
        has_ssh_bool = None
        if has_ssh is not None:
            has_ssh_bool = has_ssh.lower() == 'true'

        if search:
            result = device_service.search_devices(
                keyword=search,
                cabinet_id=cabinet_id,
                device_type=device_type,
                customer_id=customer_id,
                page=page,
                page_size=per_page,
            )
            devices = result.get("data", [])
            total = result.get("total_count", 0)
        else:
            result = device_service.get_all_devices(
                cabinet_id=cabinet_id,
                customer_id=customer_id,
                room_id=room_id,
                device_type=device_type,
                device_subtype=device_subtype,
                parent_device_id=parent_device_id,
                is_chassis=is_chassis,
                has_ssh=has_ssh_bool,
                page=page,
                page_size=per_page,
            )
            devices = result.get("devices", [])
            total = result.get("total", 0)

        items = [device if isinstance(device, dict) else device.to_dict() for device in devices]
        try:
            device_ids = [d.get("id") for d in items if d.get("id") is not None]
            monitor_summary_map = monitor_service.get_devices_monitor_summary(device_ids)
            for d in items:
                did = d.get("id")
                if did is not None and did in monitor_summary_map:
                    d["monitor_summary"] = monitor_summary_map[did]
        except Exception:  # noqa: BLE001 - 监控摘要注入失败不阻断列表
            logger.warning("设备列表监控摘要注入失败", exc_info=True)

        return APIResponse.paginated(
            data=items,
            page=page,
            per_page=per_page,
            total=total,
            message="获取设备列表成功",
        )
    except Exception as e:
        logger.error("获取设备列表失败: %s", e)
        return APIResponse.error(message="获取设备列表失败", error_code="DEVICE_LIST_ERROR", status_code=500)


@device_bp.route("/<int:device_id>", methods=["GET"])
@doc(summary="获取设备详情", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceResponse", 404: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_device(device_id):
    """获取单个设备详情

    Args:
        device_id: 设备ID

    Returns:
        JSON响应，包含设备详细信息
    """
    try:
        device = device_service.get_by_id(device_id)
    except Exception as e:
        logger.error("获取设备详情失败: %s", e)
        return APIResponse.error(message="获取设备信息失败", error_code="DEVICE_QUERY_ERROR", status_code=500)

    if not device:
        return APIResponse.error(message="设备不存在", error_code="DEVICE_NOT_FOUND", status_code=404)

    device_data = device.to_dict()
    if device.parent_device_id:
        parent_device = device_service.get_by_id(device.parent_device_id)
        if parent_device:
            device_data["parent_device_name"] = parent_device.device_name

    from app.services.device_nics_port_service import device_nics_port_service
    from app.persistence.device_storage_repository import DeviceStorageRepository
    from app.persistence.factory import create_repository
    nic_ports = device_nics_port_service.get_device_ports(device_id)
    device_data["nic_ports"] = [p.to_dict() for p in nic_ports] if nic_ports else []
    storage_repo = create_repository(DeviceStorageRepository)
    storage_items = storage_repo.find_by_device(device_id)
    device_data["storage_items"] = [s.to_dict() for s in storage_items] if storage_items else []

    return APIResponse.success(data=device_data, message="获取设备信息成功")


@device_bp.route("/", methods=["POST"])
@doc(summary="创建设备", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/DeviceCreate"}}}}, responses={201: "DeviceResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:create")
@rate_limit_api
@transactional
def create_device():
    """创建新设备

    Request Body:
        name: 设备名称（必需）
        cabinet_id: 机柜ID（必需）
        device_type: 设备类型（可选）
        brand: 品牌（可选）
        model: 型号（可选）
        serial_number: 序列号（可选）
        u_position: U位位置（可选）
        u_height: U位高度（可选）
        power_consumption: 功耗（可选）
        ip_address: IP地址（可选）
        mac_address: MAC地址（可选）
        customer_id: 客户ID（可选）
        status: 状态（可选）
        description: 描述（可选）

    Returns:
        JSON响应，包含新创建的设备信息
    """
    data = validation_manager.validate_schema(request.json, DeviceCreateSchema())

    if not data.get("parent_device_id") and not data.get("cabinet_id"):
        return APIResponse.error(message="非子节点设备必须指定所属机柜", error_code="CABINET_REQUIRED", status_code=400)

    if "ip_address" in data and data["ip_address"]:
        from app.services.device_service import _parse_ip_address_json
        parsed = _parse_ip_address_json(data["ip_address"])
        if parsed is None:
            return APIResponse.error(message="IP地址格式无效", error_code="INVALID_IP_ADDRESS", status_code=400)

    if "mac_address" in data and data["mac_address"]:
        if not validation_manager.validate_mac(data["mac_address"]):
            return APIResponse.error(message="MAC地址格式无效", error_code="INVALID_MAC_ADDRESS", status_code=400)

    device_type = data.get("device_type")
    device_subtype = data.get("device_subtype")
    if device_type and device_subtype:
        is_valid, error_msg = DeviceService.validate_device_type(device_type, device_subtype)
        if not is_valid:
            return APIResponse.error(message=error_msg, error_code="INVALID_DEVICE_TYPE", status_code=400)

    switch_config = data.pop("switch_config", None)
    if device_type == "network" and switch_config and isinstance(switch_config, dict):
        try:
            nd_svc = NetworkDeviceService()
            device, _switch = nd_svc.create_network_device(data, switch_config)
        except Exception as e:
            logger.error("网络设备创建失败: %s", e)
            return APIResponse.error(message="网络设备创建失败", error_code="DEVICE_CREATE_ERROR", status_code=500)
    else:
        try:
            device = device_service.create_device(data)
        except Exception as e:
            logger.error("设备创建失败: %s", e)
            return APIResponse.error(message="设备创建失败", error_code="DEVICE_CREATE_ERROR", status_code=500)

    return APIResponse.success(data=device.to_dict(), message="设备创建成功", status_code=201)


@device_bp.route("/<int:device_id>", methods=["PUT"])
@doc(summary="更新设备信息", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/DeviceUpdate"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceResponse", 400: "ApiError", 404: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def update_device(device_id):
    """更新设备信息

    Args:
        device_id: 设备ID

    Request Body:
        name: 设备名称（可选）
        cabinet_id: 机柜ID（可选）
        device_type: 设备类型（可选）
        brand: 品牌（可选）
        model: 型号（可选）
        serial_number: 序列号（可选）
        u_position: U位位置（可选）
        u_height: U位高度（可选）
        power_consumption: 功耗（可选）
        ip_address: IP地址（可选）
        mac_address: MAC地址（可选）
        customer_id: 客户ID（可选）
        status: 状态（可选）
        description: 描述（可选）

    Returns:
        JSON响应，包含更新后的设备信息
    """
    data = validation_manager.validate_schema(request.json, DeviceUpdateSchema())

    device = device_service.get_by_id(device_id)
    if not device:
        return APIResponse.error(message="设备不存在", error_code="DEVICE_NOT_FOUND", status_code=404)

    if "ip_address" in data and data["ip_address"]:
        from app.services.device_service import _parse_ip_address_json
        parsed = _parse_ip_address_json(data["ip_address"])
        if parsed is None:
            return APIResponse.error(message="IP地址格式无效", error_code="INVALID_IP_ADDRESS", status_code=400)

    if "mac_address" in data and data["mac_address"]:
        if not validation_manager.validate_mac(data["mac_address"]):
            return APIResponse.error(message="MAC地址格式无效", error_code="INVALID_MAC_ADDRESS", status_code=400)

    device_type = data.get("device_type")
    device_subtype = data.get("device_subtype")
    if device_type and device_subtype:
        is_valid, error_msg = DeviceService.validate_device_type(device_type, device_subtype)
        if not is_valid:
            return APIResponse.error(message=error_msg, error_code="INVALID_DEVICE_TYPE", status_code=400)

    auto_create_nodes = data.pop("auto_create_nodes", False)
    node_hardware = data.pop("node_hardware", {})
    storage_items = data.pop("storage_items", [])
    nic_ports = data.pop("nic_ports", [])
    overwrite_nodes = data.pop("overwrite_nodes", False)
    switch_config = data.pop("switch_config", None)
    effective_device_type = data.get("device_type") or device.device_type
    if effective_device_type == "network" and switch_config and isinstance(switch_config, dict):
        try:
            nd_svc = NetworkDeviceService()
            updated_device = nd_svc.update_network_device(device_id, data, switch_config)
        except Exception as e:
            logger.error("网络设备更新失败: %s", e)
            return APIResponse.error(message="网络设备更新失败", error_code="DEVICE_UPDATE_ERROR", status_code=500)
    else:
        try:
            updated_device = device_service.update_device(
                device_id, data,
                auto_create_nodes=auto_create_nodes,
                node_hardware=node_hardware,
                storage_items=storage_items,
                nic_ports=nic_ports,
                overwrite_nodes=overwrite_nodes,
            )
        except Exception as e:
            logger.error("设备更新失败: %s", e)
            return APIResponse.error(message="设备更新失败", error_code="DEVICE_UPDATE_ERROR", status_code=500)

    return APIResponse.success(data=updated_device.to_dict(), message="设备更新成功")


@device_bp.route("/<int:device_id>", methods=["DELETE"])
@doc(summary="删除设备", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("device:delete")
@rate_limit_api
@transactional
def delete_device(device_id):
    """删除设备

    Args:
        device_id: 设备ID

    Returns:
        JSON响应
    """
    device = device_service.get_by_id(device_id)
    if not device:
        return APIResponse.error(message="设备不存在", error_code="DEVICE_NOT_FOUND", status_code=404)

    try:
        device_service.delete_device(device_id)
    except Exception as e:
        logger.error("设备删除失败: %s", e)
        return APIResponse.error(message="设备删除失败", error_code="DEVICE_DELETE_ERROR", status_code=500)

    return APIResponse.success(message="设备删除成功")


@device_bp.route("/<int:device_id>/connections", methods=["GET"])
@doc(summary="获取设备连接列表", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceConnectionResponse", 404: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_device_connections(device_id):
    """获取设备连接列表

    Args:
        device_id: 设备ID

    Returns:
        JSON响应，包含设备连接列表
    """
    from app.services.device_connection_service import device_connection_service

    device = device_service.get_by_id(device_id)
    if not device:
        return APIResponse.error(message="设备不存在", error_code="DEVICE_NOT_FOUND", status_code=404)

    connections = device_connection_service.get_device_connections(device_id)

    return APIResponse.success(
        data=connections,
        message="获取连接列表成功"
    )


@device_bp.route("/<int:device_id>/ports", methods=["GET"])
@doc(summary="获取设备端口列表", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceNicPortResponse", 404: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_device_ports(device_id):
    """获取设备端口列表

    根据设备类型分流查询：
      - 网络设备 (network) → 查询 network_ports 表
      - 其他设备           → 查询 device_nics_port 表

    Args:
        device_id: 设备ID

    Returns:
        JSON响应，包含设备端口列表
    """
    device = device_service.get_by_id(device_id)
    if not device:
        return APIResponse.error(message="设备不存在", error_code="DEVICE_NOT_FOUND", status_code=404)

    if device.device_type == "network":
        from app.services.network_port_service import NetworkPortService
        port_data = NetworkPortService(NetworkPortRepository()).get_ports_by_device(device_id)
    else:
        from app.services.device_nics_port_service import device_nics_port_service
        ports = device_nics_port_service.get_device_ports(device_id)
        port_data = [p.to_dict() for p in ports] if ports else []

    return APIResponse.success(
        data={"ports": port_data},
        message="获取端口列表成功"
    )


@device_bp.route("/<int:device_id>/nodes", methods=["GET"])
@doc(summary="获取设备节点列表", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_device_nodes(device_id):
    """获取设备的节点列表（机箱模式）

    Args:
        device_id: 设备ID

    Returns:
        JSON响应，包含节点列表
    """
    device = device_service.get_by_id(device_id)
    if not device:
        return APIResponse.error(message="设备不存在", error_code="DEVICE_NOT_FOUND", status_code=404)

    if not device.is_chassis:
        return APIResponse.error(message="该设备不是机箱", error_code="NOT_CHASSIS", status_code=400)

    nodes = device_service.get_chassis_nodes(device_id)

    return APIResponse.success(
        data={"nodes": nodes},
        message="获取节点列表成功"
    )


@device_bp.route("/switch-ports/find-by-name", methods=["GET"])
@doc(summary="根据名称查找交换机端口", tags=["设备"], parameters=[{"name": "device_id", "in": "query", "required": True, "schema": {"type": "integer"}}, {"name": "port_name", "in": "query", "required": True, "schema": {"type": "string"}}], responses={200: "DeviceNicPortResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def find_switch_port_by_name():
    """根据交换机ID和端口名称查找端口
    
    Query Parameters:
        device_id: 设备ID(必需)
        port_name: 端口名称(必需)
    
    Returns:
        JSON响应,包含端口信息
    """
    from app.services.network_port_service import NetworkPortService
    _port_svc = NetworkPortService(NetworkPortRepository())

    device_id = request.args.get("device_id", type=int)
    port_name = request.args.get("port_name", type=str)

    if not device_id or not port_name:
        return APIResponse.error(
            message="设备ID和端口名称不能为空",
            error_code="INVALID_PARAMS",
            status_code=400
        )

    port = _port_svc.find_port_by_name(device_id, port_name)
    
    if not port:
        return APIResponse.error(
            message="未找到匹配的端口",
            error_code="PORT_NOT_FOUND",
            status_code=404
        )
    
    return APIResponse.success(data=port, message="获取端口信息成功")


@device_bp.route("/switch-ports/<int:port_id>", methods=["PUT"])
@doc(summary="更新交换机端口信息", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/SwitchPortUpdate"}}}}, parameters=[{"name": "port_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceNicPortResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def update_switch_port(port_id):
    """更新交换机端口信息

    Args:
        port_id: 端口ID

    Request Body:
        可更新字段: port_type, port_name, speed, status, description, vlan 等
    """
    from app.services.network_port_service import NetworkPortService
    _port_svc = NetworkPortService(NetworkPortRepository())

    data = request.get_json(silent=True) or {}
    if not data:
        return APIResponse.error(message="请求体不能为空", error_code="EMPTY_BODY", status_code=400)

    port = _port_svc.get_port_by_id(port_id)
    if not port:
        return APIResponse.error(message="端口不存在", error_code="PORT_NOT_FOUND", status_code=404)

    try:
        result = _port_svc.update_port(port_id, data)
        if result:
            updated_port = _port_svc.get_port_by_id(port_id)

            return APIResponse.success(data=updated_port, message="端口更新成功")
        return APIResponse.error(message="端口更新失败", error_code="UPDATE_FAILED", status_code=500)
    except Exception as e:
        logger.error("更新端口失败: port_id=%d, error=%s", port_id, e)
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/switch-ports/batch", methods=["POST"])
@doc(summary="批量创建交换机端口", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchCreateSwitchPorts"}}}}, responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("device:create")
@rate_limit_api
@transactional
def batch_create_switch_ports():
    """批量创建交换机端口
    
    Request Body:
        device_id: 设备ID（必需）
        ports: 端口列表（必需）
            - port_name: 端口名称
            - port_type: 端口类型（electrical/optical/management等）
            - slot: 槽位号
            - card: 卡号
            - port_number: 端口号
            - speed: 速率
            - status: 状态（free/used/disabled）
            - description: 描述
    
    Returns:
        JSON响应，包含创建结果
    """
    from app.services.network_port_service import NetworkPortService
    _port_svc = NetworkPortService(NetworkPortRepository())

    data = request.get_json()
    if not data:
        return APIResponse.error(message="请求数据不能为空", status_code=400)

    device_id = data.get("device_id")
    ports = data.get("ports", [])

    if not device_id:
        return APIResponse.error(message="设备ID不能为空", status_code=400)

    if not ports or not isinstance(ports, list):
        return APIResponse.error(message="端口列表不能为空", status_code=400)

    try:
        device = device_service.get_by_id(device_id)
        if not device:
            return APIResponse.error(message="设备不存在", error_code="DEVICE_NOT_FOUND", status_code=404)

        count = _port_svc.create_ports_batch(device_id, ports)
        
        return APIResponse.success(
            data={"created_count": count},
            message=f"成功创建 {count} 个端口"
        )
    except Exception as e:
        logger.error("批量创建端口失败: %s", str(e), exc_info=True)
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/switch-ports/device/<int:device_id>", methods=["DELETE"])
@doc(summary="删除设备的所有交换机端口", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("device:delete")
@rate_limit_api
@transactional
def delete_device_switch_ports(device_id):
    """删除设备的所有端口
    
    Args:
        device_id: 设备ID
    
    Returns:
        JSON响应
    """
    from app.services.network_port_service import NetworkPortService
    _port_svc = NetworkPortService(NetworkPortRepository())

    try:
        deleted_count = _port_svc.delete_device_ports(device_id)

        return APIResponse.success(
            data={"deleted_count": deleted_count},
            message=f"成功删除设备的所有端口,共 {deleted_count} 个"
        )
    except Exception as e:
        logger.error("删除设备端口失败: device_id=%d, error=%s", device_id, str(e))
        return APIResponse.error(message="删除设备端口失败", status_code=500)


@device_bp.route("/batch-delete", methods=["POST"])
@doc(summary="批量删除设备", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchDelete"}}}}, responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("device:delete")
@rate_limit_api
@transactional
def batch_delete_devices():
    """批量删除设备
    
    Request Body:
        ids: 设备ID列表
    
    Returns:
        JSON响应，包含删除结果
    """
    
    data = request.get_json()
    if not data or "ids" not in data:
        return APIResponse.error(message="请提供要删除的设备ID列表", status_code=400)
    
    ids = data.get("ids", [])
    if not isinstance(ids, list):
        return APIResponse.error(message="ID列表格式错误", status_code=400)
    if len(ids) > 200:
        return APIResponse.error(message="单次批量操作上限为200个", status_code=400)
    
    deleted_count = 0
    failed_ids = []
    
    for device_id in ids:
        try:
            result = device_service.delete_device(device_id)
            if result:
                deleted_count += 1
            else:
                failed_ids.append(device_id)
        except Exception as e:
            logger.error("删除设备 %d 失败: %s", device_id, str(e))
            failed_ids.append(device_id)
    
    message = f"成功删除 {deleted_count} 个设备"
    if failed_ids:
        message += f"，{len(failed_ids)} 个删除失败"
    
    return APIResponse.success(
        data={
            "deleted_count": deleted_count,
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids
        },
        message=message
    )



@device_bp.route("/deleted", methods=["GET"])
@doc(summary="查询已删除设备（回收站）", tags=["设备"], responses={200: "ApiResponse"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_deleted_devices():
    """查询已软删除的设备列表

    Query Params:
        page, per_page: 分页
        start_date, end_date: 删除时间段 (YYYY-MM-DD)
        room_id: 机房ID
        cabinet_id: 机柜ID
        device_type: 设备类型
        ip_search: IP地址搜索（参数名：search）
    """
    from datetime import datetime

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")
    room_id = request.args.get("room_id", type=int)
    cabinet_id = request.args.get("cabinet_id", type=int)
    device_type = request.args.get("device_type")
    ip_search = request.args.get("search")

    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError:
            return APIResponse.error(message="start_date 格式错误，应为 YYYY-MM-DD", status_code=400)
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
            end_date = end_date.replace(hour=23, minute=59, second=59)
        except ValueError:
            return APIResponse.error(message="end_date 格式错误，应为 YYYY-MM-DD", status_code=400)

    result = device_service.get_deleted_devices(
        page=page, page_size=per_page,
        start_date=start_date, end_date=end_date,
        room_id=room_id, cabinet_id=cabinet_id,
        device_type=device_type, ip_search=ip_search,
    )

    return APIResponse.success(data=result)


@device_bp.route("/<int:device_id>/restore", methods=["POST"])
@doc(summary="恢复已删除设备", tags=["设备"], responses={200: "DeviceResponse"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def restore_device(device_id):
    """恢复已软删除的设备

    Request Body (可选):
        cabinet_id: 指定机柜ID（U位冲突时）
        u_position: 指定U位（U位冲突时）
    """
    data = request.get_json() or {}
    cabinet_id = data.get("cabinet_id")
    u_position = data.get("u_position")

    from app.exceptions.validation import ValidationError
    try:
        result = device_service.restore_device(
            device_id, cabinet_id=cabinet_id, u_position=u_position
        )
        if result.get("restored"):
            return APIResponse.success(data=result, message="设备恢复成功")
        else:
            return APIResponse.error(
                data=result, message="原U位已被占用，请重新指定位置",
                error_code="LOCATION_CONFLICT", status_code=409
            )
    except ValidationError as e:
        return APIResponse.error(message=str(e), status_code=400)
    except Exception as e:
        logger.error("恢复设备 %d 失败: %s", device_id, str(e))
        return APIResponse.error(message="恢复设备失败", error_code="DEVICE_RESTORE_ERROR", status_code=500)


@device_bp.route("/batch-restore", methods=["POST"])
@doc(summary="批量恢复已删除设备", tags=["设备"])
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def batch_restore_devices():
    """批量恢复已软删除的设备

    Request Body:
        device_ids: 设备ID列表
        cabinet_id: 指定机柜ID（可选）
        u_position: 指定U位（可选）
    """
    data = request.get_json()
    if not data or "device_ids" not in data:
        return APIResponse.error(message="请提供要恢复的设备ID列表", status_code=400)

    device_ids = data.get("device_ids", [])
    if len(device_ids) > 200:
        return APIResponse.error(message="单次批量操作上限为200个", status_code=400)
    cabinet_id = data.get("cabinet_id")
    u_position = data.get("u_position")

    try:
        result = device_service.batch_restore_devices(
            device_ids, cabinet_id=cabinet_id, u_position=u_position
        )
    except Exception as e:
        logger.error("批量恢复设备失败: %s", str(e))
        return APIResponse.error(message="批量恢复设备失败", error_code="BATCH_RESTORE_ERROR", status_code=500)
    return APIResponse.success(data=result, message=f"成功恢复 {len(result['success'])} 个设备")


@device_bp.route("/<int:device_id>/permanent", methods=["DELETE"])
@doc(summary="永久删除设备", tags=["设备"], responses={200: "ApiResponse"})
@login_required
@permission_required("device:delete")
@rate_limit_api
@transactional
def permanent_delete_device(device_id):
    """永久删除设备（物理删除，不可恢复）"""
    from app.exceptions.validation import ValidationError
    try:
        device_service.permanent_delete_device(device_id)

        return APIResponse.success(message="设备已永久删除")
    except ValidationError as e:
        return APIResponse.error(message=str(e), status_code=400)
    except Exception as e:
        logger.error("永久删除设备 %d 失败: %s", device_id, str(e))
        return APIResponse.error(message="永久删除设备失败", error_code="DEVICE_PERMANENT_DELETE_ERROR", status_code=500)


@device_bp.route("/batch-permanent-delete", methods=["POST"])
@doc(summary="批量永久删除设备", tags=["设备"])
@login_required
@permission_required("device:delete")
@rate_limit_api
@transactional
def batch_permanent_delete_devices():
    """批量永久删除设备（物理删除，不可恢复）

    Request Body:
        device_ids: 设备ID列表
    """
    data = request.get_json()
    if not data or "device_ids" not in data:
        return APIResponse.error(message="请提供要永久删除的设备ID列表", status_code=400)

    device_ids = data.get("device_ids", [])
    if len(device_ids) > 200:
        return APIResponse.error(message="单次批量操作上限为200个", status_code=400)
    result = device_service.batch_permanent_delete_devices(device_ids)

    return APIResponse.success(
        data=result,
        message=f"成功永久删除 {len(result['success'])} 个设备"
    )




@device_bp.route("/batch-create", methods=["POST"])
@doc(summary="批量创建设备", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchCreateDevices"}}}}, responses={200: "DeviceResponse", 400: "ApiError"})
@login_required
@permission_required("device:create")
@transactional
def batch_create_devices():
    """批量创建设备，逐条创建，支持部分成功

    Request Body:
        devices: 设备数据列表（每项符合 DeviceCreateSchema）

    Returns:
        JSON响应，包含批量创建结果（total、success_count、failed_count、results）
    """
    data = request.get_json()
    devices_data = data.get("devices", [])

    if not devices_data:
        return APIResponse.error(message="设备列表不能为空", status_code=400)

    if len(devices_data) > 50:
        return APIResponse.error(message="单次批量创建上限为50台", status_code=400)

    from app.utils.cabinet_utils import CabinetUCalculator
    cabinet_groups: dict[int, list[tuple[int, dict]]] = {}  # cabinet_id → [(index, device_data)]
    for index, device_data in enumerate(devices_data):
        cabinet_id = device_data.get("cabinet_id")
        if cabinet_id and device_data.get("u_position") is None:
            cabinet_groups.setdefault(cabinet_id, []).append((index, device_data))

    for cabinet_id, group in cabinet_groups.items():
        cabinet = cabinet_service.get_by_id(cabinet_id)
        if not cabinet:
            continue
        available = CabinetUCalculator.get_available_u_positions(
            devices=[d.to_dict() for d in cabinet.devices],
            total_u=cabinet.total_u,
        )
        available_positions = sorted(available.get("available_positions", []))
        pos_idx = 0
        for index, device_data in group:
            height_u = device_data.get("height_u", 1) or 1
            assigned = None
            for j in range(pos_idx, len(available_positions) - height_u + 1):
                start = available_positions[j]
                continuous = all(
                    available_positions[j + k] == start + k
                    for k in range(height_u)
                )
                if continuous:
                    assigned = start
                    for k in range(height_u):
                        if j + k < len(available_positions):
                            available_positions[j + k] = -1
                    pos_idx = j + height_u
                    break
            if assigned is not None:
                devices_data[index]["u_position"] = assigned

    for index, device_data in enumerate(devices_data):
        cabinet_id = device_data.get("cabinet_id")
        u_position = device_data.get("u_position")
        height_u = device_data.get("height_u", 1) or 1
        if cabinet_id and u_position:
            conflicts = device_service.device_repository.check_u_position_conflict(
                cabinet_id, u_position, height_u
            )
            if conflicts:
                cabinet = cabinet_service.get_by_id(cabinet_id)
                if cabinet:
                    available = CabinetUCalculator.get_available_u_positions(
                        devices=[d.to_dict() for d in cabinet.devices],
                        total_u=cabinet.total_u,
                    )
                    available_positions = sorted(available.get("available_positions", []))
                    for j in range(len(available_positions) - height_u + 1):
                        start = available_positions[j]
                        continuous = all(
                            available_positions[j + k] == start + k
                            for k in range(height_u)
                        )
                        if continuous:
                            devices_data[index]["u_position"] = start
                            break

    results = []
    success_count = 0
    failed_count = 0

    for index, device_data in enumerate(devices_data):
        try:
            validated = validation_manager.validate_schema(device_data, DeviceCreateSchema())
            switch_config = validated.pop("switch_config", None)
            device_type = validated.get("device_type")

            if device_type == "network" and switch_config:
                nd_svc = NetworkDeviceService()
                device, _ = nd_svc.create_network_device(validated, switch_config)
            else:
                device = device_service.create_device(validated)

            results.append({
                "index": index,
                "device_name": device_data.get("device_name", ""),
                "success": True,
                "device_id": device.id,
            })
            success_count += 1
        except Exception as e:
            results.append({
                "index": index,
                "device_name": device_data.get("device_name", ""),
                "success": False,
                "error": str(e),
            })
            failed_count += 1

    result_data = {
        "total": len(devices_data),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results,
    }

    if failed_count > 0:
        from app.services.notification_service import notification_service
        from flask import g
        user_id = g.current_user["user_id"] if hasattr(g, 'current_user') else None
        severity = "warning" if success_count > 0 else "critical"
        title = "批量创建设备部分失败" if success_count > 0 else "批量创建设备全部失败"
        notification_service.notify(
            type=NotificationTypeCode.BATCH_CREATE_DEVICES,
            severity=severity,
            title=title,
            content=f"共 {len(devices_data)} 台，成功 {success_count} 台，失败 {failed_count} 台",
            payload=result_data,
            source_module="device",
            target_type="user",
            target_id=user_id,
            idempotency_key=f"batch_create_devices:{user_id or 'anon'}:{int(__import__('time').time())}",
        )

    return APIResponse.success(data=result_data)


CLONE_EXCLUDE_FIELDS = {
    "id", "created_at", "updated_at", "deleted_at",
    "device_name", "serial_number", "hostname",
    "management_ip", "mac_address", "ip_address",
    "asset_number", "ipmi_address",
    "u_position",
    "cabinet_number", "status_name", "customer_name",
    "room_id", "room_name",
    "responsible_person_name", "responsible_person_username",
    "available_u", "device_count", "u_usage_rate", "power_usage_rate",
    "parent_u_position", "parent_height_u",
    "switch_credential",
    "port_summary", "nic_ports", "storage_items",
    "deleted_location_snapshot", "deleted_children_snapshot",
}

@device_bp.route("/clone/<int:device_id>", methods=["POST"])
@doc(summary="获取设备克隆模板数据", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceResponse", 404: "ApiError"})
@login_required
@permission_required("device:view")
def clone_device(device_id):
    """获取设备模板数据用于克隆，排除唯一性字段"""
    device = device_service.get_device_by_id(device_id)
    if not device:
        return APIResponse.error(message="设备不存在", status_code=404)

    device_dict = device
    clone_data = {k: v for k, v in device_dict.items() if k not in CLONE_EXCLUDE_FIELDS}

    return APIResponse.success(data=clone_data)


@device_bp.route("/switch-ports", methods=["GET"])
@doc(summary="获取交换机端口列表", tags=["设备"], parameters=[{"name": "device_id", "in": "query", "schema": {"type": "integer"}}, {"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "per_page", "in": "query", "schema": {"type": "integer", "default": 20}}], responses={200: "DeviceNicPortResponse", 500: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_switch_ports():
    """获取交换机端口列表
    
    Query Parameters:
        device_id: 交换机设备ID（可选）
        page: 页码（默认1）
        per_page: 每页数量（默认20）
    
    Returns:
        JSON响应，包含端口列表
    """
    from app.services.network_port_service import NetworkPortService

    device_id = request.args.get("device_id", type=int)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    per_page = min(per_page, 100)

    try:
        port_service = NetworkPortService(NetworkPortRepository())
        
        if device_id:
            ports = port_service.get_ports_by_device(device_id)
            total = len(ports)
        else:
            ports, total = port_service.get_all_ports(page=page, per_page=per_page)
        
        return APIResponse.paginated(
            data=ports,
            page=page,
            per_page=per_page,
            total=total,
            message="获取交换机端口列表成功"
        )
    except Exception as e:
        logger.error("获取交换机端口列表失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)



@device_bp.route("/statistics", methods=["GET"])
@doc(summary="获取设备统计信息", tags=["设备"], responses={200: "ApiResponse", 500: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_device_statistics():
    """获取设备统计信息
    
    Returns:
        JSON响应，包含设备统计数据（按类型、状态、机房等维度统计）
    """
    try:
        stats = device_service.get_device_statistics()
        return APIResponse.success(data=stats, message="获取设备统计信息成功")
    except Exception as e:
        logger.error("获取设备统计信息失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/count", methods=["GET"])
@doc(summary="获取设备总数", tags=["设备"], parameters=[{"name": "cabinet_id", "in": "query", "schema": {"type": "integer"}}, {"name": "room_id", "in": "query", "schema": {"type": "integer"}}], responses={200: "ApiResponse", 500: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_device_count():
    """获取设备总数
    
    Query Parameters:
        cabinet_id: 按机柜ID过滤（可选）
        room_id: 按机房ID过滤（可选）
    
    Returns:
        JSON响应，包含设备总数
    """
    try:
        cabinet_id = request.args.get("cabinet_id", type=int)
        room_id = request.args.get("room_id", type=int)
        
        if cabinet_id:
            count = device_service.get_device_count_by_cabinet(cabinet_id)
        elif room_id:
            count = device_service.get_device_count_by_room(room_id)
        else:
            count = device_service.get_device_count()
        
        return APIResponse.success(data={"count": count}, message="获取设备数量成功")
    except Exception as e:
        logger.error("获取设备数量失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/<int:device_id>/status", methods=["PUT"])
@doc(summary="更改设备状态", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/DeviceStatusUpdate"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def change_device_status(device_id):
    """更改设备状态
    
    Args:
        device_id: 设备ID
    
    Request Body:
        status: 新状态值（0-已报废, 1-可用, 2-在线, 3-离线, 4-维护中, 5-预留）
    
    Returns:
        JSON响应，包含更新结果
    """
    try:
        data = request.get_json()
        if not data:
            return APIResponse.error(message="请求数据不能为空", status_code=400)
        
        new_status = data.get("status")
        if new_status is None:
            return APIResponse.error(message="缺少status参数", status_code=400)
        
        device = device_service.get_by_id(device_id)
        if not device:
            return APIResponse.error(message="设备不存在", error_code="DEVICE_NOT_FOUND", status_code=404)
        
        device_service.change_device_status(device_id, new_status)

        return APIResponse.success(message="设备状态更新成功")
    except ValueError as e:
        return APIResponse.error(message=str(e), status_code=400)
    except Exception as e:
        logger.error("更改设备状态失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/<int:device_id>/location", methods=["PUT"])
@doc(summary="更新设备所在机柜", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/DeviceLocationUpdate"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def update_device_location(device_id):
    """更新设备所在机柜
    
    Args:
        device_id: 设备ID
    
    Request Body:
        cabinet_id: 新机柜ID
    
    Returns:
        JSON响应，包含更新结果
    """
    try:
        data = request.get_json()
        if not data:
            return APIResponse.error(message="请求数据不能为空", status_code=400)
        
        cabinet_id = data.get("cabinet_id")
        if cabinet_id is None:
            return APIResponse.error(message="缺少cabinet_id参数", status_code=400)
        
        device_service.update_device_location(device_id, cabinet_id)

        return APIResponse.success(message="设备位置更新成功")
    except ValueError as e:
        return APIResponse.error(message=str(e), status_code=400)
    except Exception as e:
        logger.error("更新设备位置失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/batch-update-status", methods=["POST"])
@doc(summary="批量更新设备状态", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchUpdateDeviceStatus"}}}}, responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def batch_update_device_status():
    """批量更新设备状态
    
    Request Body:
        device_ids: 设备ID列表
        status: 新状态值
    
    Returns:
        JSON响应，包含更新结果
    """
    try:
        data = request.get_json()
        if not data:
            return APIResponse.error(message="请求数据不能为空", status_code=400)
        
        device_ids = data.get("device_ids", [])
        new_status = data.get("status")
        
        if not device_ids:
            return APIResponse.error(message="device_ids不能为空", status_code=400)
        if new_status is None:
            return APIResponse.error(message="缺少status参数", status_code=400)
        
        device_service.batch_update_status(device_ids, new_status)

        return APIResponse.success(message=f"成功更新 {len(device_ids)} 台设备状态")
    except ValueError as e:
        return APIResponse.error(message=str(e), status_code=400)
    except Exception as e:
        logger.error("批量更新设备状态失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/batch-update-hardware", methods=["POST"])
@doc(summary="批量更新设备硬件配置", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchUpdateHardware"}}}}, responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def batch_update_device_hardware():
    """批量更新设备硬件配置

    Request Body:
        ids: 设备ID列表
        其余字段: 硬件配置字段（cpu, memory, os_version 等）

    Returns:
        JSON响应，包含 {updated, skipped}
    """
    try:
        data = request.get_json()
        if not data:
            return APIResponse.error(message="请求数据不能为空", status_code=400)

        device_ids = data.get("ids", [])
        if not device_ids:
            return APIResponse.error(message="ids不能为空", status_code=400)

        hardware_fields = {k: v for k, v in data.items() if k != "ids"}
        result = device_service.batch_update_hardware(device_ids, hardware_fields)

        return APIResponse.success(data=result, message=f"更新 {result['updated']} 台，跳过 {result['skipped']} 台")
    except Exception as e:
        logger.error("批量更新硬件配置失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/batch-update-asset", methods=["POST"])
@doc(summary="批量更新设备资产信息", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchUpdateAsset"}}}}, responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def batch_update_device_asset():
    """批量更新设备资产信息

    Request Body:
        ids: 设备ID列表
        auto_generate_asset_number: 是否为每个设备自动生成资产编号（默认false）
        其余字段: 资产信息字段（supplier, purchase_date 等，资产编号仅支持自动生成）

    Returns:
        JSON响应，包含 {updated, skipped}
    """
    try:
        data = request.get_json()
        if not data:
            return APIResponse.error(message="请求数据不能为空", status_code=400)

        device_ids = data.get("ids", [])
        if not device_ids:
            return APIResponse.error(message="ids不能为空", status_code=400)

        auto_generate = data.get("auto_generate_asset_number", False)

        asset_fields = {k: v for k, v in data.items()
                        if k not in ("ids", "auto_generate_asset_number")}

        result = device_service.batch_update_asset(
            device_ids, asset_fields, auto_generate=auto_generate
        )

        return APIResponse.success(data=result, message=f"更新 {result['updated']} 台，跳过 {result['skipped']} 台")
    except Exception as e:
        logger.error("批量更新资产信息失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/batch-metric-template-group", methods=["POST"])
@doc(summary="批量设置/清除设备指标模板组", tags=["设备"], responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def batch_update_device_metric_template_group():
    """批量设置/清除设备的显式指标模板组关联。

    Request Body:
        device_ids: 设备ID列表
        metric_template_group_id: 目标模板组ID（传 null 表示清除，回到自动匹配）

    供「批量修改监控」弹窗使用：选中多台设备统一绑定（或清除）某个指标模板组。
    """
    try:
        data = request.get_json(silent=True) or {}
        device_ids = data.get("device_ids") or []
        group_id = data.get("metric_template_group_id")
        if not device_ids:
            return APIResponse.error(message="device_ids不能为空", status_code=400)
        result = device_service.batch_update_metric_template_group(device_ids, group_id)
        return APIResponse.success(
            data=result,
            message=f"更新 {result['updated']} 台，跳过 {result['skipped']} 台",
        )
    except Exception as e:
        logger.error("批量更新指标模板组失败: %s", str(e))
        return APIResponse.error(message=str(e), status_code=400)


@device_bp.route("/batch-port-sync-enabled", methods=["POST"])
@doc(summary="批量设置/清除设备端口同步开关", tags=["设备"], responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def batch_update_device_port_sync_enabled():
    """批量设置/清除设备的端口同步开关。

    Request Body:
        device_ids: 设备ID列表
        port_sync_enabled: true=强制开, false=强制关, null=跟随全局

    供「批量修改监控」弹窗使用：选中多台网络设备统一开启/关闭/跟随全局端口同步。
    仅对网络设备（device_type='network'）生效，非网络设备跳过。
    """
    try:
        data = request.get_json(silent=True) or {}
        device_ids = data.get("device_ids") or []
        port_sync_enabled = data.get("port_sync_enabled")
        if not device_ids:
            return APIResponse.error(message="device_ids不能为空", status_code=400)
        if port_sync_enabled is not None and not isinstance(port_sync_enabled, bool):
            return APIResponse.error(message="port_sync_enabled必须为bool或null", status_code=400)
        result = device_service.batch_update_port_sync_enabled(device_ids, port_sync_enabled)
        parts = [f"已设置 {result['updated']} 台网络设备"]
        if result["with_credential"] > 0:
            parts.append(f"{result['with_credential']} 台有凭据可立即生效")
        if result["without_credential"] > 0:
            parts.append(f"{result['without_credential']} 台需配置凭据后才能同步")
        if result["non_network"] > 0:
            parts.append(f"跳过 {result['non_network']} 台非网络设备")
        return APIResponse.success(
            data=result,
            message="，".join(parts),
        )
    except Exception as e:
        logger.error("批量更新端口同步开关失败: %s", str(e))
        return APIResponse.error(message=str(e), status_code=400)


@device_bp.route("/batch-update-config", methods=["POST"])
@doc(
    summary="批量修改设备配置",
    tags=["设备"],
    responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"},
)
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def batch_update_device_config():
    """批量修改设备配置（通用字段 + 硬件配置 / 网络拓扑 + 端口生成）

    请求体（其余字段除 ids 外均为可选，按需传）：
        ids: 设备ID列表（须为同一子类型）
        main: {brand, device_model, power, responsible_person, customer_id}
        hardware: DeviceHardware 字段（cpu/memory/gpu/storage_summary/ipmi_username/ipmi_password 等，不含 ipmi_address）
        nic_ports: 已展开的网卡端口列表
        switch_config: {switch_role, layer, uplink_device_id, core_device_id, uplink_port_ids, port_num}
        switch_ports: 已展开的交换机端口列表（由端口生成规则展开）

    Returns:
        JSON响应，包含 {updated, skipped, nic_created, port_created}
    """
    try:
        data = request.get_json()
        if not data:
            return APIResponse.error(message="请求数据不能为空", status_code=400)

        device_ids = data.get("ids", [])
        if not device_ids:
            return APIResponse.error(message="ids不能为空", status_code=400)

        payload = {k: v for k, v in data.items() if k != "ids"}
        result = device_service.batch_update_config(device_ids, payload)

        return APIResponse.success(
            data=result,
            message=f"更新 {result['updated']} 台，跳过 {result['skipped']} 台"
            + (f"，生成网卡端口 {result['nic_created']} 个" if result.get("nic_created") else "")
            + (f"，生成交换机端口 {result['port_created']} 个" if result.get("port_created") else ""),
        )
    except Exception as e:
        logger.error("批量修改设备配置失败: %s", str(e), exc_info=True)
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/batch-reset-asset", methods=["POST"])
@doc(summary="批量重置设备资产信息", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchResetAsset"}}}}, responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def batch_reset_device_asset():
    """批量重置（清空）设备资产信息

    Request Body:
        ids: 设备ID列表

    Returns:
        JSON响应，包含 {updated, skipped}
    """
    try:
        data = request.get_json()
        if not data:
            return APIResponse.error(message="请求数据不能为空", status_code=400)

        device_ids = data.get("ids", [])
        if not device_ids:
            return APIResponse.error(message="ids不能为空", status_code=400)

        result = device_service.batch_reset_asset(device_ids)

        return APIResponse.success(data=result, message=f"重置 {result['updated']} 台，跳过 {result['skipped']} 台")
    except Exception as e:
        logger.error("批量重置资产信息失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/generate-serial-number", methods=["POST"])
@doc(summary="生成唯一序列号", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/SerialNumberGenerate"}}}}, responses={200: "ApiResponse", 500: "ApiError"})
@login_required
@permission_required("device:create")
@rate_limit_api
def generate_serial_number():
    """生成唯一序列号
    
    Request Body:
        prefix: 序列号前缀（可选）
        format_type: 格式类型（可选，默认'numeric'）
        length: 序列号长度（可选，默认8）
    
    Returns:
        JSON响应，包含生成的序列号
    """
    try:
        data = request.get_json(silent=True) or {}
        prefix = data.get("prefix", "DEV")
        format_type = data.get("format_type", "numeric")
        length = data.get("length", 8)
        
        serial_number = device_service.generate_serial_number(prefix, format_type, length)
        return APIResponse.success(data={"serial_number": serial_number}, message="序列号生成成功")
    except Exception as e:
        logger.error("生成序列号失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/check-serial-unique", methods=["POST"])
@doc(summary="检查序列号唯一性", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/SerialNumberCheck"}}}}, responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def check_serial_number_unique():
    """检查序列号是否唯一
    
    Request Body:
        serial_number: 待检查的序列号
        exclude_id: 排除的设备ID（可选，用于编辑时排除自身）
    
    Returns:
        JSON响应，包含是否唯一的结果
    """
    try:
        data = request.get_json()
        if not data:
            return APIResponse.error(message="请求数据不能为空", status_code=400)
        
        serial_number = data.get("serial_number")
        exclude_id = data.get("exclude_id")
        
        if not serial_number:
            return APIResponse.error(message="缺少serial_number参数", status_code=400)
        
        is_unique = device_service.is_serial_number_unique(serial_number, exclude_id)
        return APIResponse.success(data={"is_unique": is_unique}, message="检查完成")
    except Exception as e:
        logger.error("检查序列号唯一性失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/by-name/<device_name>", methods=["GET"])
@doc(summary="根据名称获取设备", tags=["设备"], parameters=[{"name": "device_name", "in": "path", "required": True, "schema": {"type": "string"}}], responses={200: "DeviceResponse", 404: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_device_by_name(device_name):
    """根据设备名称获取设备
    
    Args:
        device_name: 设备名称
    
    Returns:
        JSON响应，包含设备信息
    """
    try:
        device = device_service.get_by_device_name(device_name)
        if not device:
            return APIResponse.error(message="设备不存在", status_code=404)
        return APIResponse.success(data=device.to_dict() if hasattr(device, 'to_dict') else device, message="获取设备成功")
    except Exception as e:
        logger.error("根据名称获取设备失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/by-serial/<serial_number>", methods=["GET"])
@doc(summary="根据序列号获取设备", tags=["设备"], parameters=[{"name": "serial_number", "in": "path", "required": True, "schema": {"type": "string"}}], responses={200: "DeviceResponse", 404: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_device_by_serial(serial_number):
    """根据序列号获取设备
    
    Args:
        serial_number: 序列号
    
    Returns:
        JSON响应，包含设备信息
    """
    try:
        device = device_service.get_by_serial_number(serial_number)
        if not device:
            return APIResponse.error(message="设备不存在", status_code=404)
        return APIResponse.success(data=device.to_dict() if hasattr(device, 'to_dict') else device, message="获取设备成功")
    except Exception as e:
        logger.error("根据序列号获取设备失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/check-node-position", methods=["POST"])
@doc(summary="检查节点位置是否重复", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/NodePositionCheck"}}}}, responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:view")
def check_node_position():
    """检查节点位置是否重复

    用于设备创建/编辑时验证节点位置的唯一性。

    Request Body:
        chassis_id: 机箱ID
        node_position: 节点位置
        exclude_device_id: 排除的设备ID（编辑时使用）

    Returns:
        JSON响应，包含检查结果
    """
    try:
        data = request.get_json()
        chassis_id = data.get("chassis_id")
        node_position = data.get("node_position")
        exclude_device_id = data.get("exclude_device_id")

        if not chassis_id or node_position is None:
            return APIResponse.error(
                message="缺少必要参数", error_code="VALIDATION_ERROR", status_code=400
            )

        result = device_service.check_node_position(
            chassis_id, node_position, exclude_device_id
        )
        return APIResponse.success(
            data=result,
            message="节点位置重复" if result["is_duplicate"] else "节点位置可用",
        )
    except Exception as e:
        logger.error("检查节点位置失败: %s", e)
        return APIResponse.error(message="操作失败", status_code=500)


@device_bp.route("/<int:chassis_id>/swap-node-positions", methods=["POST"])
@doc(summary="拖拽更换机箱节点位置", tags=["设备"], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@transactional
def swap_node_positions(chassis_id):
    """拖拽更换机箱节点位置

    请求体：
        source_position: 拖拽源节点所在位置（该位置必须已有节点）
        target_position: 目标位置（可空可占用；占用则交换，空则移动）

    返回：{ swapped, source, target, exchanged }
    """
    from app.exceptions.validation import ValidationError

    data = request.get_json(silent=True) or {}
    source = data.get("source_position")
    target = data.get("target_position")
    if not isinstance(source, int) or not isinstance(target, int):
        return APIResponse.error(
            message="source_position 与 target_position 必须为整数",
            error_code="VALIDATION_ERROR",
            status_code=400,
        )
    try:
        result = device_service.swap_node_positions(chassis_id, source, target)
    except ValidationError as e:
        return APIResponse.error(message=str(e), error_code="VALIDATION_ERROR", status_code=400)
    except Exception as e:  # noqa: BLE001
        logger.error("交换节点位置失败: %s", e)
        return APIResponse.error(message="交换节点位置失败", error_code="DEVICE_UPDATE_ERROR", status_code=500)
    return APIResponse.success(data=result, message="节点位置已更新")



@device_bp.route("/<int:device_id>/vlans", methods=["GET"])
@doc(summary="获取设备VLAN列表", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
def list_device_vlans(device_id):
    """获取设备VLAN列表（所有交换机可用，has_ssh无关）

    Args:
        device_id: 设备ID

    Returns:
        JSON响应，包含VLAN列表
    """
    from app.services.vlan_service import VLANService
    vlan_svc = VLANService(VLANRepository())
    vlans = vlan_svc.get_by_device(device_id)
    return APIResponse.success(data=[v.to_dict() for v in vlans], message="获取VLAN列表成功")


@device_bp.route("/<int:device_id>/vlans", methods=["POST"])
@doc(summary="在设备上创建VLAN", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/DeviceVLANCreate"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={201: "ApiResponse", 409: "ApiError"})
@login_required
@permission_required("switch:create")
@transactional
def create_device_vlan(device_id):
    """在指定设备上创建VLAN（设备维度端点，device_id通过URL路径传递）

    Request Body: vlan_id, name, purpose等（不含device_id）
    """
    from marshmallow import Schema, fields, validate
    from app.services.vlan_service import VLANService
    from app.exceptions.validation import ValidationError

    class DeviceVLANCreateSchema(Schema):
        """设备维度VLAN创建参数（device_id从URL获取）"""
        vlan_id = fields.Int(required=True, validate=validate.Range(min=1, max=4094))
        name = fields.Str(required=True, validate=validate.Length(min=1, max=64))
        purpose = fields.Str(load_default=None, validate=validate.Length(max=200))
        subnet_id = fields.Int(load_default=None)
        room_id = fields.Int(load_default=None)
        status = fields.Int(load_default=1)

    schema = DeviceVLANCreateSchema()
    data = schema.load(request.get_json())
    data['device_id'] = device_id
    try:
        vlan_svc = VLANService(VLANRepository())
        vlan = vlan_svc.create(data)
        return APIResponse.success(data=vlan.to_dict(), message="VLAN创建成功", status_code=201)
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="VLAN_CONFLICT", status_code=409)


@device_bp.route("/<int:device_id>/vlans/<int:vlan_db_id>/members", methods=["GET"])
@doc(summary="获取VLAN成员端口列表", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "vlan_db_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
def get_vlan_members(device_id, vlan_db_id):
    """获取VLAN成员端口列表

    Args:
        device_id: 设备ID
        vlan_db_id: VLAN数据库ID

    Returns:
        JSON响应，包含成员端口列表
    """
    from app.services.vlan_service import VLANService
    vlan_svc = VLANService(VLANRepository())
    members = vlan_svc.get_members(vlan_db_id)
    return APIResponse.success(data=members, message="获取VLAN成员端口成功")


@device_bp.route("/<int:device_id>/vlans/<int:vlan_db_id>/members", methods=["PUT"])
@doc(summary="更新VLAN成员端口", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/VLANMemberUpdate"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "vlan_db_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("switch:config")
@transactional
def update_vlan_members(device_id, vlan_db_id):
    """手动更新VLAN成员端口（全量替换，所有交换机可用）

    Args:
        device_id: 设备ID
        vlan_db_id: VLAN数据库ID

    Request Body:
        port_ids: 端口ID列表

    Returns:
        JSON响应
    """
    from app.services.vlan_service import VLANService
    data = request.get_json()
    port_ids = data.get("port_ids", [])
    vlan_svc = VLANService(VLANRepository())
    vlan_svc.update_members_manual(vlan_db_id, port_ids)
    return APIResponse.success(message="成员端口已更新")


@device_bp.route("/<int:device_id>/vlans/<int:vlan_db_id>", methods=["PUT"])
@doc(summary="更新VLAN字段", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/VLANFieldUpdate"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "vlan_db_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("switch:config")
@transactional
def update_device_vlan(device_id, vlan_db_id):
    """更新 VLAN 字段（如 purpose、name），仅修改数据库记录，不操作交换机

    Args:
        device_id: 设备ID
        vlan_db_id: VLAN数据库ID

    Request Body:
        purpose: 用途说明
        name: VLAN名称

    Returns:
        JSON响应，包含更新后的VLAN记录
    """
    from app.services.vlan_service import VLANService
    data = request.get_json()
    vlan_svc = VLANService(VLANRepository())
    vlan = vlan_svc.update(vlan_db_id, data)
    return APIResponse.success(data=vlan.to_dict(), message="更新成功")


@device_bp.route("/<int:device_id>/port-links", methods=["GET"])
@doc(summary="获取设备端口互联关系", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
def get_device_port_links(device_id):
    """查询设备的端口互联关系（network_to_network）

    从 network_connections 表查询，返回包含 connection_type 等业务字段的完整数据。

    Args:
        device_id: 设备ID

    Returns:
        JSON响应，包含端口互联关系列表
    """
    from app.services.device_connection_service import device_connection_service
    links = device_connection_service.get_network_connections(device_id)
    return APIResponse.success(data=links, message="获取端口互联关系成功")


@device_bp.route("/<int:device_id>/port-links/<int:connection_id>", methods=["DELETE"])
@doc(summary="断开端口互联关系", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "connection_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("device:delete")
@transactional
def disconnect_port_link(device_id, connection_id):
    """断开端口的互联关系（network_to_network）

    从 network_connections 表删除记录，同时释放两端端口的占用状态。

    Args:
        device_id: 设备ID
        connection_id: network_connections 表的主键 ID

    Returns:
        JSON响应
    """
    from app.services.device_connection_service import device_connection_service
    from app.persistence.network_connection_repository import NetworkConnectionRepository
    nc_repo = NetworkConnectionRepository()
    conn = nc_repo.find_by_id(connection_id)
    if not conn or (conn.get("local_device_id") != device_id and conn.get("peer_device_id") != device_id):
        return APIResponse.error("连接不存在或不属于该设备", status_code=404)
    peer_device_id = conn.get("peer_device_id") if conn.get("local_device_id") == device_id else conn.get("local_device_id")
    svc = device_connection_service
    result = svc.delete_network_connection_by_id(connection_id)
    if not result:
        return APIResponse.error("删除连接失败", status_code=400)
    return APIResponse.success(data={"peer_device_id": peer_device_id}, message="端口互联已断开")


@device_bp.route("/<int:device_id>/port-links/<int:connection_id>", methods=["PUT"])
@doc(summary="更新端口互联关系", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "connection_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("device:update")
@transactional
def update_port_link(device_id, connection_id):
    """更新端口互联关系的业务字段（network_to_network）

    可更新字段：connection_type, vlan_id, status, notes, bandwidth, description, lag_group_id
    不支持更换端口（需删除后重建）。

    Args:
        device_id: 设备ID
        connection_id: network_connections 表的主键 ID

    Returns:
        JSON响应
    """
    from app.persistence.network_connection_repository import NetworkConnectionRepository
    nc_repo = NetworkConnectionRepository()
    conn = nc_repo.find_by_id(connection_id)
    if not conn or (conn.get("local_device_id") != device_id and conn.get("peer_device_id") != device_id):
        return APIResponse.error("连接不存在或不属于该设备", status_code=404)

    data = request.get_json(silent=True) or {}
    allowed = {"connection_type", "vlan_id", "status", "notes", "bandwidth", "description", "lag_group_id"}
    update_data = {k: v for k, v in data.items() if k in allowed}
    if not update_data:
        return APIResponse.error("无有效更新字段", status_code=400)

    result = nc_repo.update_connection(connection_id, update_data)
    if not result:
        return APIResponse.error("更新连接失败", status_code=400)

    updated_conn = nc_repo.find_by_id(connection_id)
    return APIResponse.success(data=updated_conn, message="更新成功")


@device_bp.route("/<int:device_id>/port-channels", methods=["GET"])
@doc(summary="获取设备LAG列表", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
def list_device_port_channels(device_id):
    """获取设备LAG列表（所有交换机可用）

    Args:
        device_id: 设备ID

    Returns:
        JSON响应，包含LAG列表
    """
    from app.services.link_aggregation_service import LinkAggregationService
    lag_svc = LinkAggregationService(LinkAggregationRepository())
    lags = lag_svc.get_by_device(device_id)
    return APIResponse.success(data=[l.to_dict() for l in lags], message="获取LAG列表成功")


@device_bp.route("/<int:device_id>/port-channels", methods=["POST"])
@doc(summary="在设备上创建链路聚合组", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/LAGCreate"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={201: "ApiResponse", 409: "ApiError"})
@login_required
@permission_required("switch:create")
@transactional
def create_device_port_channel(device_id):
    """在指定设备上创建链路聚合组（设备维度端点）

    Args:
        device_id: 设备ID

    Request Body: lag_name, lag_type等（不含device_id）
    """
    from app.services.link_aggregation_service import LinkAggregationService
    from app.exceptions.validation import ValidationError
    data = request.get_json()
    data['device_id'] = device_id
    try:
        lag_svc = LinkAggregationService(LinkAggregationRepository())
        group = lag_svc.create(data)
        return APIResponse.success(data=group.to_dict(), message="链路聚合组创建成功", status_code=201)
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="LAG_CONFLICT", status_code=409)


@device_bp.route("/<int:device_id>/port-channels/<int:lag_id>", methods=["DELETE"])
@doc(summary="删除链路聚合组", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "lag_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("switch:delete")
@transactional
def delete_device_port_channel(device_id, lag_id):
    """删除链路聚合组（设备维度端点）

    Args:
        device_id: 设备ID
        lag_id: 链路聚合组ID
    """
    from app.services.link_aggregation_service import LinkAggregationService
    lag_svc = LinkAggregationService(LinkAggregationRepository())
    if lag_svc.delete(lag_id):
        return APIResponse.success(message="链路聚合组删除成功")
    return APIResponse.error("链路聚合组不存在", error_code="LAG_NOT_FOUND", status_code=404)


@device_bp.route("/<int:device_id>/port-channels/<int:lag_id>/members", methods=["GET"])
@doc(summary="获取LAG成员端口列表", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "lag_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
def get_lag_members(device_id, lag_id):
    """获取LAG成员端口列表

    Args:
        device_id: 设备ID
        lag_id: LAG组ID

    Returns:
        JSON响应，包含成员端口列表
    """
    from app.services.link_aggregation_service import LinkAggregationService
    lag_svc = LinkAggregationService(LinkAggregationRepository())
    members = lag_svc.get_members(lag_id)
    return APIResponse.success(data=members, message="获取LAG成员端口成功")


@device_bp.route("/<int:device_id>/port-channels/<int:lag_id>/members", methods=["PUT"])
@doc(summary="更新LAG成员端口", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/LAGMemberUpdate"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "lag_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("switch:config")
@transactional
def update_lag_members(device_id, lag_id):
    """手动更新LAG成员端口（全量替换，所有交换机可用）

    Args:
        device_id: 设备ID
        lag_id: LAG组ID

    Request Body:
        port_ids: 端口ID列表

    Returns:
        JSON响应
    """
    from app.services.link_aggregation_service import LinkAggregationService
    data = request.get_json()
    port_ids = data.get("port_ids", [])
    lag_svc = LinkAggregationService(LinkAggregationRepository())
    lag_svc.update_members_manual(lag_id, port_ids)
    return APIResponse.success(message="成员端口已更新")


@device_bp.route("/<int:device_id>/port-channels/<int:lag_id>", methods=["PUT"])
@doc(summary="更新链路聚合组字段", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/LAGFieldUpdate"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "lag_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("switch:config")
@transactional
def update_port_channel(device_id, lag_id):
    """更新链路聚合组字段（如 purpose）

    Args:
        device_id: 设备ID
        lag_id: LAG组ID

    Request Body:
        purpose: 用途说明

    Returns:
        JSON响应，包含更新后的LAG记录
    """
    from app.services.link_aggregation_service import LinkAggregationService
    data = request.get_json()
    lag_svc = LinkAggregationService(LinkAggregationRepository())
    lag = lag_svc.update(lag_id, data)
    return APIResponse.success(data=lag.to_dict(), message="更新成功")
