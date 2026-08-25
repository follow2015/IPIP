# -*- coding: utf-8 -*-
"""
设备网卡端口API接口

提供网卡端口的REST API接口,包括配置管理、查询、状态更新等。

变更记录:
  - [Fix #1] 注册为 Flask Blueprint，修复所有路由 404 问题
             原文件为裸函数,Flask 无法路由
"""
from flask import Blueprint, request
from marshmallow import Schema, fields, validate, EXCLUDE

from app.openapi.doc import doc, public
from app.services.device_nics_port_service import device_nics_port_service
from app.services.port_matching_engine import PortMatchingEngine
from app.api.base import APIResponse, api_exception_handler
from app.utils import login_required, permission_required, rate_limit_api
from app.utils.transactional import transactional


device_nics_port_bp = Blueprint(
    "device_nics_port",
    __name__,
    url_prefix="/api/devices"
)


class NicPortBatchSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    nics = fields.List(fields.Dict(), required=True)


class NicPortIncrementalBatchSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    ports = fields.List(fields.Dict(), required=True)


class NicPortUpdateSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    port_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    port_speed = fields.Str(validate=validate.Length(max=20), allow_none=True)
    port_name = fields.Str(validate=validate.Length(max=100), allow_none=True)
    port_status = fields.Str(validate=validate.Length(max=20), allow_none=True)
    description = fields.Str(validate=validate.Length(max=200), allow_none=True)


class NicPortBatchDeleteSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    port_ids = fields.List(fields.Int(), required=True)


@device_nics_port_bp.route("/<int:device_id>/nics", methods=["PUT"])
@doc(summary="创建或更新设备网卡配置", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/NicPortBatch"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceNicPortResponse", 400: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def create_or_update_nics(device_id: int):
    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    nics_config = data.get('nics', [])

    success, message, ports = device_nics_port_service.create_or_update_nics(
        device_id, nics_config
    )

    if success:
        return APIResponse.success(
            data={'ports': [port.to_dict() for port in ports]},
            message=message
        )
    return APIResponse.error(message, status_code=400)


@device_nics_port_bp.route("/<int:device_id>/nics/batch-create", methods=["POST"])
@doc(summary="增量批量创建网卡端口", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/NicPortIncrementalBatch"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceNicPortResponse", 400: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def batch_create_nics(device_id: int):
    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    ports_data = data.get('ports', [])
    if not ports_data:
        return APIResponse.error("端口列表不能为空", status_code=400)

    success, message, ports = device_nics_port_service.batch_create_ports(
        device_id, ports_data
    )

    if success:
        return APIResponse.success(
            data={'ports': [port.to_dict() for port in ports]},
            message=message
        )
    return APIResponse.error(message, status_code=400)


@device_nics_port_bp.route("/<int:device_id>/nics", methods=["GET"])
@doc(summary="获取设备网卡配置", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceNicPortResponse", 404: "ApiError"})
@login_required
@rate_limit_api
@api_exception_handler
def get_device_nics(device_id: int):
    ports   = device_nics_port_service.get_device_ports(device_id)
    summary = device_nics_port_service.get_ports_summary(device_id)

    return APIResponse.success(
        data={
            'ports':   [port.to_dict() for port in ports],
            'summary': summary
        },
        message="获取网卡配置成功"
    )


@device_nics_port_bp.route("/<int:device_id>/nics", methods=["DELETE"])
@doc(summary="删除设备所有网卡配置", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def delete_device_nics(device_id: int):
    success, message = device_nics_port_service.delete_device_ports(device_id)

    if success:
        return APIResponse.success(message=message)
    return APIResponse.error(message, status_code=400)


@device_nics_port_bp.route("/<int:device_id>/available-ports", methods=["GET"])
@doc(summary="获取设备可用端口列表", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "port_type", "in": "query", "schema": {"type": "string"}}, {"name": "port_speed", "in": "query", "schema": {"type": "string"}}], responses={200: "DeviceNicPortResponse", 404: "ApiError"})
@login_required
@rate_limit_api
@api_exception_handler
def get_available_ports(device_id: int):
    port_type  = request.args.get('port_type')
    port_speed = request.args.get('port_speed')

    ports = PortMatchingEngine.get_available_ports(device_id, port_type, port_speed)

    return APIResponse.success(
        data={'ports': [port.to_dict() for port in ports]},
        message="获取可用端口成功"
    )


@device_nics_port_bp.route("/<int:device_id>/nics/<int:port_id>", methods=["GET"])
@doc(summary="获取单个端口详情", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "port_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceNicPortResponse", 404: "ApiError"})
@login_required
@rate_limit_api
@api_exception_handler
def get_single_port(device_id: int, port_id: int):
    port = device_nics_port_service.get_port_by_id(port_id)

    if not port or port.device_id != device_id:
        return APIResponse.error(
            f"端口不存在: {port_id}",
            error_code="PORT_NOT_FOUND",
            status_code=404
        )

    return APIResponse.success(data=port.to_dict(), message="获取端口信息成功")


@device_nics_port_bp.route("/<int:device_id>/nics/<int:port_id>", methods=["PUT"])
@doc(summary="更新单个端口", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/NicPortUpdate"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "port_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceNicPortResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def update_single_port(device_id: int, port_id: int):
    port = device_nics_port_service.get_port_by_id(port_id)

    if not port or port.device_id != device_id:
        return APIResponse.error(
            f"端口不存在: {port_id}",
            error_code="PORT_NOT_FOUND",
            status_code=404
        )

    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    if port.port_status == 'occupied':
        allowed_when_occupied = {'port_status', 'description'}
        disallowed = set(data.keys()) - allowed_when_occupied
        if disallowed:
            return APIResponse.error(
                f"端口正在使用中，仅允许更新: {', '.join(sorted(allowed_when_occupied))}",
                status_code=400
            )

    ok = device_nics_port_service.repo.update_port(port_id, data)
    if ok:
        updated_port = device_nics_port_service.get_port_by_id(port_id)
        return APIResponse.success(
            data=updated_port.to_dict(),
            message="端口更新成功"
        )
    return APIResponse.error("端口更新失败", status_code=400)


@device_nics_port_bp.route("/<int:device_id>/nics/<int:port_id>", methods=["DELETE"])
@doc(summary="删除单个端口", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "port_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def delete_single_port(device_id: int, port_id: int):
    port = device_nics_port_service.get_port_by_id(port_id)

    if not port or port.device_id != device_id:
        return APIResponse.error(
            f"端口不存在: {port_id}",
            error_code="PORT_NOT_FOUND",
            status_code=404
        )

    if port.port_status == 'occupied':
        return APIResponse.error(
            "端口正在使用中，请先删除相关连接",
            status_code=400
        )

    ok = device_nics_port_service.repo.delete_port(port_id)
    if ok:
        return APIResponse.success(message="端口删除成功")
    return APIResponse.error("端口删除失败", status_code=400)


@device_nics_port_bp.route("/<int:device_id>/nics/batch", methods=["DELETE"])
@doc(summary="批量删除端口", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def batch_delete_nics(device_id: int):
    data = request.get_json(silent=True) or {}
    port_ids = data.get("port_ids") or []
    if not port_ids:
        return APIResponse.error("端口 ID 列表不能为空", status_code=400)

    result = device_nics_port_service.batch_delete_ports(device_id, port_ids)
    deleted_n = len(result.get("deleted", []))
    skipped_n = len(result.get("skipped", []))
    if skipped_n == 0:
        message = f"已删除 {deleted_n} 个端口"
    else:
        message = f"已删除 {deleted_n} 个端口，{skipped_n} 个因占用或无效被跳过"
    return APIResponse.success(data=result, message=message)


_port_bp = Blueprint(
    "device_nics_port_single",
    __name__,
    url_prefix="/api/nics-ports"
)


@_port_bp.route("/<int:port_id>", methods=["GET"])
@doc(summary="根据ID获取端口详情", tags=["设备"], parameters=[{"name": "port_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceNicPortResponse", 404: "ApiError"})
@login_required
@rate_limit_api
@api_exception_handler
def get_port_by_id(port_id: int):
    port = device_nics_port_service.get_port_by_id(port_id)

    if not port:
        return APIResponse.error(
            f"端口不存在: {port_id}",
            error_code="PORT_NOT_FOUND",
            status_code=404
        )

    return APIResponse.success(data=port.to_dict(), message="获取端口信息成功")


_template_bp = Blueprint(
    "nic_templates",
    __name__,
    url_prefix="/api/nic-templates"
)


@_template_bp.route("/", methods=["GET"])
@doc(summary="获取网卡模板列表", tags=["设备"], responses={200: "ApiResponse"})
@login_required
@rate_limit_api
@api_exception_handler
def get_nic_templates():
    templates = [
        {
            "key": "dual_1g_electrical",
            "name": "双1G电口网卡",
            "port_count": 2,
            "description": "2个1G RJ45电口",
            "ports": [
                {"port_type": "RJ45", "speed": "1G"},
                {"port_type": "RJ45", "speed": "1G"}
            ]
        },
        {
            "key": "quad_10g_optical",
            "name": "四10G光口网卡",
            "port_count": 4,
            "description": "4个10G SFP+光口",
            "ports": [{"port_type": "SFP+", "speed": "10G"}] * 4
        },
        {
            "key": "dual_25g_optical",
            "name": "双25G光口网卡",
            "port_count": 2,
            "description": "2个25G SFP28光口",
            "ports": [{"port_type": "SFP28", "speed": "25G"}] * 2
        },
        {
            "key": "dual_100g_optical",
            "name": "双100G光口网卡",
            "port_count": 2,
            "description": "2个100G QSFP28光口",
            "ports": [{"port_type": "QSFP28", "speed": "100G"}] * 2
        },
        {
            "key": "quad_100g_optical",
            "name": "四100G光口网卡",
            "port_count": 4,
            "description": "4个100G QSFP28光口",
            "ports": [{"port_type": "QSFP28", "speed": "100G"}] * 4
        },
        {
            "key": "quad_1g_electrical",
            "name": "四1G电口网卡",
            "port_count": 4,
            "description": "4个1G RJ45电口",
            "ports": [
                {"port_type": "RJ45", "speed": "1G"},
                {"port_type": "RJ45", "speed": "1G"},
                {"port_type": "RJ45", "speed": "1G"},
                {"port_type": "RJ45", "speed": "1G"}
            ]
        },
        {
            "key": "custom",
            "name": "自由配置",
            "port_count": 0,
            "description": "自定义端口数量、类型和速率",
            "is_custom": True
        }
    ]

    return APIResponse.success(
        data={'templates': templates},
        message="获取网卡模板成功"
    )


@device_nics_port_bp.route("/<int:chassis_id>/children/nics", methods=["POST"])
@doc(summary="为机箱子节点批量创建网卡端口", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/NicPortIncrementalBatch"}}}}, parameters=[{"name": "chassis_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required('device:update')
@api_exception_handler
@transactional
def batch_create_children_nics(chassis_id: int):
    from app.models.device import Device

    data = request.get_json()
    ports_template = data.get('ports', [])
    if not ports_template:
        return APIResponse.error("端口模板不能为空", status_code=400)

    node_ids = device_nics_port_service.get_child_device_ids(chassis_id)
    if not node_ids:
        return APIResponse.success(
            data={'created': 0}, message="机箱暂无子节点"
        )

    result = device_nics_port_service.batch_create_for_devices(
        node_ids, ports_template
    )

    return APIResponse.success(
        data=result,
        message=f"已为 {result['created']} 台子节点创建端口"
    )


all_blueprints = [device_nics_port_bp, _port_bp, _template_bp]
