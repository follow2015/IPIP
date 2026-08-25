# -*- coding: utf-8 -*-
"""
设备连接API

提供设备连接管理的RESTful API端点。
"""
from flask import Blueprint, request
from marshmallow import Schema, fields, validate, EXCLUDE

from app.openapi.doc import doc, public
from app.services.device_connection_service import device_connection_service
from app.api.base import APIResponse, api_exception_handler
from app.utils import login_required, permission_required, rate_limit_api
from app.utils.transactional import transactional

device_connection_bp = Blueprint("device_connection", __name__, url_prefix="/api/device-connections")


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


@device_connection_bp.route("/", methods=["POST"])
@doc(summary="创建设备连接", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/DeviceConnectionCreate"}}}}, responses={201: "DeviceConnectionResponse", 400: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def create_connection():
    """创建设备连接
    
    Request Body:
        device_id: 设备ID(必需)
        switch_device_id: 交换机设备ID(必需)
        switch_port_id: 交换机端口ID(可选)
            - device_to_network: 对端交换机端口ID
            - network_to_network: 本机端口ID
        peer_port_id: 对端端口ID(可选,仅network_to_network)
        device_nics_port_id: 设备网卡端口ID(可选)
        link_type: 连接类型(可选,默认device_to_network)
            - device_to_network: 设备到网络设备的连接
            - network_to_network: 网络设备间互联
        connection_type: 连接类型(可选)
        vlan_id: VLAN ID(可选)
        notes: 备注(可选)
    
    Returns:
        JSON响应,包含新创建的连接ID
    """
    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)
    
    if not data.get('device_id'):
        return APIResponse.error("设备ID不能为空", status_code=400)
    if not data.get('switch_device_id'):
        return APIResponse.error("交换机设备ID不能为空", status_code=400)
    
    connection_id = device_connection_service.create_connection(data)
    
    return APIResponse.success(
        data={"id": connection_id},
        message="设备连接创建成功",
        status_code=201
    )


@device_connection_bp.route("/", methods=["GET"])
@doc(summary="获取设备连接列表", tags=["设备"], parameters=[{"name": "device_id", "in": "query", "schema": {"type": "integer"}}, {"name": "switch_device_id", "in": "query", "schema": {"type": "integer"}}], responses={200: "DeviceConnectionResponse", 400: "ApiError"})
@login_required
@rate_limit_api
@api_exception_handler
def get_connections():
    """获取设备连接列表
    
    Query Parameters:
        device_id: 设备ID(可选)
        switch_device_id: 交换机设备ID(可选)
    
    Returns:
        JSON响应,包含连接列表
    """
    device_id = request.args.get('device_id', type=int)
    switch_device_id = request.args.get('switch_device_id', type=int)
    
    if device_id:
        connections = device_connection_service.get_device_connections(device_id)
    elif switch_device_id:
        connections = device_connection_service.get_switch_connections(switch_device_id)
    else:
        return APIResponse.error("请提供 device_id 或 switch_device_id 参数", status_code=400)
    
    return APIResponse.success(data=connections, message="获取连接列表成功")


@device_connection_bp.route("/<int:connection_id>", methods=["GET"])
@doc(summary="获取单个设备连接", tags=["设备"], parameters=[{"name": "connection_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceConnectionResponse", 404: "ApiError"})
@login_required
@rate_limit_api
@api_exception_handler
def get_connection(connection_id):
    """获取单个设备连接
    
    Args:
        connection_id: 连接ID
    
    Returns:
        JSON响应,包含连接详情
    """
    connection = device_connection_service.get_connection(connection_id)
    
    if not connection:
        return APIResponse.error("连接不存在", error_code="CONNECTION_NOT_FOUND", status_code=404)
    
    return APIResponse.success(data=connection, message="获取连接信息成功")


@device_connection_bp.route("/<int:connection_id>", methods=["PUT"])
@doc(summary="更新设备连接", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/DeviceConnectionUpdate"}}}}, parameters=[{"name": "connection_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceConnectionResponse", 400: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def update_connection(connection_id):
    """更新设备连接
    
    Args:
        connection_id: 连接ID
    
    Request Body:
        device_id: 设备ID(可选)
        switch_device_id: 交换机设备ID(可选)
        switch_port_id: 交换机端口ID(可选)
        connection_type: 连接类型(可选)
        vlan_id: VLAN ID(可选)
        notes: 备注(可选)
    
    Returns:
        JSON响应
    """
    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)
    
    device_connection_service.update_connection(connection_id, data)
    
    return APIResponse.success(
        data={"updated": True},
        message="设备连接更新成功"
    )


@device_connection_bp.route("/<int:connection_id>", methods=["DELETE"])
@doc(summary="删除设备连接", tags=["设备"], parameters=[{"name": "connection_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def delete_connection(connection_id):
    """删除设备连接
    
    Args:
        connection_id: 连接ID
    
    Returns:
        JSON响应
    """
    device_connection_service.delete_connection(connection_id)
    
    return APIResponse.success(message="设备连接删除成功")


@device_connection_bp.route("/device/<int:device_id>", methods=["DELETE"])
@doc(summary="删除设备的所有连接", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required('device:delete')
@rate_limit_api
@api_exception_handler
@transactional
def delete_device_connections(device_id):
    """删除设备的所有连接
    
    Args:
        device_id: 设备ID
    
    Returns:
        JSON响应
    """
    count = device_connection_service.delete_device_connections(device_id)
    
    return APIResponse.success(
        data={"deleted_count": count},
        message=f"成功删除设备的所有连接,共 {count} 条"
    )
