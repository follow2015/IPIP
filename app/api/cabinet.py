# -*- coding: utf-8 -*-
"""
机柜API

提供机柜管理的RESTful API端点。
"""
from app.utils.logging import get_logger
import re
from flask import Blueprint, request, g
import hashlib
from marshmallow import Schema, fields, validate, EXCLUDE

logger = get_logger(__name__)

from app.services import CabinetService
from app.persistence.cabinet_repository import CabinetRepository
from extensions import db as _db
from app.api.base import APIResponse
from app.utils import (
    login_required,
    permission_required,
    rate_limit_api,
    validation_manager,
)
from app.utils.transactional import transactional
from app.exceptions.data_access import RecordNotFoundError
from app.openapi.doc import doc, public

cabinet_bp = Blueprint("cabinet", __name__)
cabinet_service = CabinetService(CabinetRepository())


class CabinetCreateSchema(Schema):
    """创建机柜请求验证Schema"""

    cabinet_number = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    room_id = fields.Int(required=True, validate=validate.Range(min=1))
    location = fields.Str(allow_none=True, validate=validate.Length(max=255))
    row = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1))
    col = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1))
    total_u = fields.Int(validate=validate.Range(min=1, max=100))
    total_power = fields.Int(allow_none=True, validate=validate.Range(min=0))
    customer_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    status = fields.Int(validate=validate.Range(min=0, max=4))
    notes = fields.Str(allow_none=True)
    batch = fields.Bool(load_default=False)


class CabinetUpdateSchema(Schema):
    """更新机柜请求验证Schema"""

    cabinet_number = fields.Str(validate=validate.Length(min=1, max=255))
    room_id = fields.Int(validate=validate.Range(min=1))
    location = fields.Str(allow_none=True, validate=validate.Length(max=255))
    row = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1))
    col = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1))
    total_u = fields.Int(validate=validate.Range(min=1, max=100))
    total_power = fields.Int(allow_none=True, validate=validate.Range(min=0))
    customer_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    status = fields.Int(validate=validate.Range(min=0, max=4))
    notes = fields.Str(allow_none=True)


class UPositionCheckSchema(Schema):
    """检查U位是否可用请求Schema"""
    class Meta:
        unknown = EXCLUDE
    u_position = fields.Int(required=True)
    height_u = fields.Int(allow_none=True)
    exclude_device_id = fields.Int(allow_none=True)


class UAssignSchema(Schema):
    """批量分配U位请求Schema"""
    class Meta:
        unknown = EXCLUDE
    devices = fields.List(fields.Dict(), required=True)


class SmartUAssignSchema(Schema):
    """智能分配U位请求Schema"""
    class Meta:
        unknown = EXCLUDE
    height_u = fields.Int(required=True)
    device_spacing = fields.Int(allow_none=True)
    allocation_strategy = fields.Str(validate=validate.Length(max=50), allow_none=True)
    min_u = fields.Int(allow_none=True)
    max_u = fields.Int(allow_none=True)


class CabinetCapacityValidateSchema(Schema):
    """验证机柜容量请求Schema"""
    class Meta:
        unknown = EXCLUDE
    new_device = fields.Dict(allow_none=True)
    device_spacing = fields.Int(allow_none=True)
    min_height_for_spacing = fields.Int(allow_none=True)
    max_usage_rate = fields.Float(allow_none=True)


class CabinetOptimizeSchema(Schema):
    """优化机柜布局请求Schema"""
    class Meta:
        unknown = EXCLUDE
    strategy = fields.Str(validate=validate.Length(max=50), allow_none=True)
    device_spacing = fields.Int(allow_none=True)


class CabinetCustomerUpdateSchema(Schema):
    """更新机柜客户请求Schema"""
    class Meta:
        unknown = EXCLUDE
    customer_id = fields.Int(allow_none=True)


@cabinet_bp.route("/", methods=["GET"])
@doc(summary="获取机柜列表", tags=["机柜"], parameters=[{"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "per_page", "in": "query", "schema": {"type": "integer", "default": 20}}, {"name": "search", "in": "query", "schema": {"type": "string"}}, {"name": "room_id", "in": "query", "schema": {"type": "integer"}}, {"name": "customer_id", "in": "query", "schema": {"type": "integer"}}, {"name": "status", "in": "query", "schema": {"type": "string"}}], responses={200: "CabinetResponse", 500: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def list_cabinets():
    """获取机柜列表（支持分页、搜索过滤）

    Query Parameters:
        page: 页码（默认1）
        per_page: 每页数量（默认20）
        search: 搜索关键词，模糊匹配机柜编号/位置（可选）
        room_id: 按机房ID过滤（可选）
        customer_id: 按客户ID过滤（可选）
        status: 按状态过滤（可选）
    """
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search = request.args.get("search", type=str)
    room_id = request.args.get("room_id", type=int)
    customer_id = request.args.get("customer_id", type=int)
    status = request.args.get("status", type=str)

    try:
        if search:
            filters = {}
            if room_id:
                filters["room_id"] = room_id
            if customer_id:
                filters["customer_id"] = customer_id
            if status:
                filters["status"] = status
            result = cabinet_service.cabinet_repository.search(
                search_fields=["cabinet_number", "location"],
                keyword=search,
                filters=filters,
                page=page,
                page_size=per_page,
            )
            cabinets = result.get("data", [])
            total = result.get("total_count", 0)
        else:
            filters = {}
            if room_id:
                filters["room_id"] = room_id
            if customer_id:
                filters["customer_id"] = customer_id
            if status:
                filters["status"] = status
            cabinets, total = cabinet_service.get_paginated(page=page, per_page=per_page, filters=filters)

        return APIResponse.paginated(
            data=[cabinet.to_dict() for cabinet in cabinets],
            page=page,
            per_page=per_page,
            total=total,
            message="获取机柜列表成功",
        )
    except Exception as e:
        logger.error("获取机柜列表失败: %s", e)
        return APIResponse.error(message="获取机柜列表失败", error_code="CABINET_LIST_ERROR", status_code=500)


@cabinet_bp.route("/<int:cabinet_id>", methods=["GET"])
@doc(summary="获取机柜详情", tags=["机柜"], parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "CabinetResponse", 404: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def get_cabinet(cabinet_id):
    """获取单个机柜详情

    Args:
        cabinet_id: 机柜ID

    Returns:
        JSON响应，包含机柜详细信息
    """
    cabinet = cabinet_service.get_by_id(cabinet_id)

    if not cabinet:
        return APIResponse.error(message="机柜不存在", error_code="CABINET_NOT_FOUND", status_code=404)

    return APIResponse.success(data=cabinet.to_dict(), message="获取机柜信息成功")


def _parse_cabinet_numbers(input_str: str) -> list:
    """解析机柜编号表达式，支持批量输入

    支持格式：
    - 单个：m11
    - 多个逗号分隔：m11,m13,n10
    - 范围展开：h1-10 → h1,h2,...,h10
    - 混合：m11,m13,h1-3,n10

    Args:
        input_str: 用户输入的机柜编号字符串

    Returns:
        展开后的机柜编号列表
    """
    if not input_str or not input_str.strip():
        return []

    result = []
    parts = [p.strip() for p in re.split(r'[,，\s]+', input_str) if p.strip()]

    for part in parts:
        range_match = re.match(r'^([a-zA-Z]+)(\d+)-(\d+)$', part)
        if range_match:
            prefix = range_match.group(1)
            start = int(range_match.group(2))
            end = int(range_match.group(3))
            width = len(range_match.group(2))
            for i in range(start, end + 1):
                result.append(f"{prefix}{str(i).zfill(width)}")
        else:
            result.append(part)

    return result


@cabinet_bp.route("/", methods=["POST"])
@doc(summary="创建机柜（支持批量）", tags=["机柜"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CabinetCreate"}}}}, responses={201: "CabinetResponse", 400: "ApiError", 409: "ApiError", 500: "ApiError"})
@login_required
@permission_required("cabinet:create")
@rate_limit_api
@transactional
def create_cabinet():
    """创建新机柜（支持批量）

    Request Body:
        cabinet_number: 机柜名称/编号（必需）
        room_id: 机房ID（必需）
        location: 位置（可选）
        total_u: U位数量（可选）
        total_power: 电力容量（可选）
        customer_id: 客户ID（可选）
        status: 状态（可选）
        notes: 描述（可选）
        batch: 是否批量模式（可选，默认false）
            当 batch=true 时，cabinet_number 支持批量解析：
            - 逗号分隔：m11,m13,n10
            - 范围展开：h1-10 → h1,h2,...,h10
            - 混合：m11,m13,h1-3,n10

    Returns:
        JSON响应，包含新创建的机柜信息（单条）或批量创建结果
    """
    data = validation_manager.validate_schema(request.json, CabinetCreateSchema())
    is_batch = data.pop("batch", False)

    try:
        if not is_batch:
            existing = cabinet_service.get_by_cabinet_number(data.get("cabinet_number") or data.get("name"))
            if existing:
                return APIResponse.error(message="机柜名称已存在", error_code="CABINET_NAME_EXISTS", status_code=409)
            cabinet = cabinet_service.create_cabinet(data)
            return APIResponse.success(data=cabinet.to_dict(), message="机柜创建成功", status_code=201)

        cabinet_number_input = data.get("cabinet_number") or data.get("name", "")
        cabinet_numbers = _parse_cabinet_numbers(cabinet_number_input)

        if not cabinet_numbers:
            return APIResponse.error(message="请输入有效的机柜编号", error_code="INVALID_CABINET_NUMBERS", status_code=400)

        created = []
        failed = []
        errors = {}

        for number in cabinet_numbers:
            try:
                item_data = dict(data)
                item_data["cabinet_number"] = number
                if cabinet_service.get_by_cabinet_number(number):
                    failed.append(number)
                    errors[number] = "机柜编号已存在"
                    continue
                cabinet = cabinet_service.create_cabinet(item_data)
                created.append(cabinet.to_dict())
            except Exception as e:
                failed.append(number)
                errors[number] = str(e)

        message = f"成功创建 {len(created)} 个机柜"
        if failed:
            message += f"，{len(failed)} 个失败"

        return APIResponse.success(
            data={
                "created": created,
                "failed": failed,
                "errors": errors,
                "created_count": len(created),
                "failed_count": len(failed),
            },
            message=message,
            status_code=201 if created else 400,
        )
    except Exception as e:
        logger.error("机柜创建失败: %s", e)
        return APIResponse.error(message="机柜创建失败", status_code=500)


@cabinet_bp.route("/<int:cabinet_id>", methods=["PUT"])
@doc(summary="更新机柜信息", tags=["机柜"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CabinetUpdate"}}}}, parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "CabinetResponse", 404: "ApiError", 409: "ApiError"})
@login_required
@permission_required("cabinet:update")
@rate_limit_api
@transactional
def update_cabinet(cabinet_id):
    """更新机柜信息

    Args:
        cabinet_id: 机柜ID

    Request Body:
        name: 机柜名称（可选）
        room_id: 机房ID（可选）
        position: 位置（可选）
        u_count: U位数量（可选）
        power_capacity: 电力容量（可选）
        customer_id: 客户ID（可选）
        status: 状态（可选）
        description: 描述（可选）

    Returns:
        JSON响应，包含更新后的机柜信息
    """
    data = validation_manager.validate_schema(request.json, CabinetUpdateSchema())

    cabinet = cabinet_service.get_by_id(cabinet_id)
    if not cabinet:
        return APIResponse.error(message="机柜不存在", error_code="CABINET_NOT_FOUND", status_code=404)

    if "name" in data:
        existing = cabinet_service.get_by_cabinet_number(data["name"])
        if existing and existing.id != cabinet_id:
            return APIResponse.error(message="机柜名称已存在", error_code="CABINET_NAME_EXISTS", status_code=409)

    updated_cabinet = cabinet_service.update_cabinet(cabinet_id, data)
    return APIResponse.success(data=updated_cabinet.to_dict(), message="机柜更新成功")


@cabinet_bp.route("/<int:cabinet_id>", methods=["DELETE"])
@doc(summary="删除机柜", tags=["机柜"], parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError", 409: "ApiError"})
@login_required
@permission_required("cabinet:delete")
@rate_limit_api
@transactional
def delete_cabinet(cabinet_id):
    """删除机柜

    Args:
        cabinet_id: 机柜ID

    Returns:
        JSON响应
    """
    cabinet = cabinet_service.get_by_id(cabinet_id)
    if not cabinet:
        return APIResponse.error(message="机柜不存在", error_code="CABINET_NOT_FOUND", status_code=404)

    if cabinet.devices:
        return APIResponse.error(message="机柜下还有设备，无法删除", error_code="CABINET_HAS_DEVICES", status_code=409)

    cabinet_service.delete_cabinet(cabinet_id)
    return APIResponse.success(message="机柜删除成功")


@cabinet_bp.route("/<int:cabinet_id>/devices", methods=["GET"])
@doc(summary="获取机柜下的设备列表", tags=["机柜"], parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def get_cabinet_devices(cabinet_id):
    """获取机柜下的所有设备

    Args:
        cabinet_id: 机柜ID

    Returns:
        JSON响应，包含设备列表
    """
    cabinet = cabinet_service.get_by_id(cabinet_id)
    if not cabinet:
        return APIResponse.error(message="机柜不存在", error_code="CABINET_NOT_FOUND", status_code=404)

    devices = cabinet_service.get_devices(cabinet_id)

    return APIResponse.success(data=[device.to_dict() for device in devices], message="获取设备列表成功")


@cabinet_bp.route("/<int:cabinet_id>/utilization", methods=["GET"])
@doc(summary="获取机柜利用率", tags=["机柜"], parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "CabinetUtilizationResponse", 404: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def get_cabinet_utilization(cabinet_id):
    """获取机柜利用率

    Args:
        cabinet_id: 机柜ID

    Returns:
        JSON响应，包含利用率信息
    """
    cabinet = cabinet_service.get_by_id(cabinet_id)
    if not cabinet:
        return APIResponse.error(message="机柜不存在", error_code="CABINET_NOT_FOUND", status_code=404)

    utilization = cabinet_service.get_utilization(cabinet_id)

    return APIResponse.success(data=utilization, message="获取利用率成功")


@cabinet_bp.route("/available", methods=["GET"])
@doc(summary="获取可用机柜列表", tags=["机柜"], parameters=[{"name": "room_id", "in": "query", "schema": {"type": "integer"}}, {"name": "min_available_u", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "all_status", "in": "query", "schema": {"type": "integer", "default": 0}}, {"name": "statuses", "in": "query", "schema": {"type": "string"}}], responses={200: "CabinetResponse"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def get_available_cabinets():
    """获取可用机柜列表

    Query Parameters:
        room_id: 机房ID（可选）
        min_available_u: 最小可用U位数（默认1）
        all_status: 为1时返回所有状态机柜，不限status=1（默认0）
        statuses: 逗号分隔的状态码列表，如"1,2"（可选，优先级高于all_status）

    Returns:
        JSON响应，包含可用机柜列表
    """
    room_id = request.args.get("room_id", type=int)
    min_available_u = request.args.get("min_available_u", 1, type=int)
    all_status = request.args.get("all_status", 0, type=int)
    statuses_str = request.args.get("statuses", type=str)

    statuses = None
    if statuses_str:
        try:
            statuses = [int(s.strip()) for s in statuses_str.split(",") if s.strip()]
        except ValueError:
            statuses = None

    cabinets = cabinet_service.get_available_cabinets(
        room_id=room_id,
        min_available_u=min_available_u,
        all_status=bool(all_status),
        statuses=statuses,
    )

    return APIResponse.success(data=cabinets, message="获取可用机柜成功")


@cabinet_bp.route("/<int:cabinet_id>/layout", methods=["GET"])
@doc(summary="获取机柜布局信息", tags=["机柜"], parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def get_cabinet_layout(cabinet_id):
    """获取机柜布局信息

    Args:
        cabinet_id: 机柜ID

    Returns:
        JSON响应，包含机柜布局信息
    """
    cabinet = cabinet_service.get_by_id(cabinet_id)
    if not cabinet:
        return APIResponse.error(message="机柜不存在", error_code="CABINET_NOT_FOUND", status_code=404)

    layout = cabinet_service.get_cabinet_layout(cabinet_id)

    return APIResponse.success(data=layout, message="获取机柜布局成功")


@cabinet_bp.route("/<int:cabinet_id>/u-positions", methods=["GET"])
@doc(summary="获取机柜可用U位列表", tags=["机柜"], parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def get_available_u_positions(cabinet_id):
    """获取机柜可用U位列表

    Args:
        cabinet_id: 机柜ID

    Returns:
        JSON响应，包含可用U位列表
    """
    cabinet = cabinet_service.get_by_id(cabinet_id)
    if not cabinet:
        return APIResponse.error(message="机柜不存在", error_code="CABINET_NOT_FOUND", status_code=404)

    positions = cabinet_service.get_available_u_positions(cabinet_id)

    return APIResponse.success(data=positions, message="获取可用U位成功")


@cabinet_bp.route("/<int:cabinet_id>/u-positions/check", methods=["POST"])
@doc(summary="检查U位是否可用", tags=["机柜"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/UPositionCheck"}}}}, parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def check_u_position(cabinet_id):
    """检查U位是否可用

    Args:
        cabinet_id: 机柜ID

    Request Body:
        u_position: U位起始位置
        height_u: 设备高度U数
        exclude_device_id: 排除的设备ID（可选）

    Returns:
        JSON响应
    """
    data = request.get_json(silent=True) or {}
    u_position = data.get("u_position")
    height_u = data.get("height_u", 1)
    exclude_device_id = data.get("exclude_device_id")

    if not u_position:
        return APIResponse.error(message="请提供 u_position 参数", error_code="INVALID_PARAMS", status_code=400)

    cabinet = cabinet_service.get_by_id(cabinet_id)
    if not cabinet:
        return APIResponse.error(message="机柜不存在", error_code="CABINET_NOT_FOUND", status_code=404)

    from app.utils.cabinet_utils import CabinetUCalculator

    devices = [d.to_dict() for d in cabinet.devices]
    result = CabinetUCalculator.check_u_position_conflict(
        devices=devices,
        u_position=u_position,
        height_u=height_u,
        exclude_device_id=exclude_device_id
    )

    return APIResponse.success(data=result, message="检查成功")


@cabinet_bp.route("/<int:cabinet_id>/u-positions/batch-allocate", methods=["POST"])
@doc(summary="批量分配U位", tags=["机柜"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/UAssign"}}}}, parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("cabinet:update")
@rate_limit_api
def batch_allocate_u_positions(cabinet_id):
    """批量分配U位

    Args:
        cabinet_id: 机柜ID

    Request Body:
        devices: 设备列表 [{device_id, height_u, preferred_position}, ...]

    Returns:
        JSON响应
    """
    data = request.get_json(silent=True) or {}
    devices_data = data.get("devices", [])

    if not devices_data:
        return APIResponse.error(message="请提供 devices 参数", error_code="INVALID_PARAMS", status_code=400)

    cabinet = cabinet_service.get_by_id(cabinet_id)
    if not cabinet:
        return APIResponse.error(message="机柜不存在", error_code="CABINET_NOT_FOUND", status_code=404)

    from app.utils.cabinet_utils import CabinetUCalculator

    existing_devices = [d.to_dict() for d in cabinet.devices]
    device_dicts = [
        {"device_id": d.get("device_id"), "height_u": d.get("height_u"), "preferred_position": d.get("preferred_position")}
        for d in devices_data
    ]

    result = CabinetUCalculator.batch_allocate_devices(
        devices_to_allocate=device_dicts,
        existing_devices=existing_devices,
        total_u=cabinet.total_u
    )

    return APIResponse.success(data=result, message="批量分配成功")


@cabinet_bp.route("/<int:cabinet_id>/u-positions/usage-map", methods=["GET"])
@doc(summary="获取U位使用情况映射", tags=["机柜"], parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "height_u", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "min_u", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "max_u", "in": "query", "schema": {"type": "integer"}}, {"name": "exclude_device_id", "in": "query", "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def get_u_position_usage_map(cabinet_id):
    """获取U位使用情况映射

    Args:
        cabinet_id: 机柜ID

    Returns:
        JSON响应
    """
    cabinet = cabinet_service.get_by_id(cabinet_id)
    if not cabinet:
        return APIResponse.error(message="机柜不存在", error_code="CABINET_NOT_FOUND", status_code=404)

    height_u = request.args.get('height_u', 1, type=int)
    min_u = request.args.get('min_u', 1, type=int)
    max_u = request.args.get('max_u', cabinet.total_u, type=int)
    exclude_device_id = request.args.get('exclude_device_id', type=int)

    from app.utils.cabinet_utils import CabinetUCalculator

    devices = [d.to_dict() for d in cabinet.devices]
    if exclude_device_id:
        devices = [d for d in devices if d.get('id') != exclude_device_id]

    result = CabinetUCalculator.get_available_u_positions(
        devices, cabinet.total_u,
        height_u=height_u,
        device_spacing=0,
    )

    if min_u > 1 or max_u < cabinet.total_u:
        result['available_positions'] = [
            p for p in result['available_positions']
            if min_u <= p and p + height_u - 1 <= max_u
        ]
        result['reserved_ranges'] = []
        if min_u > 1:
            result['reserved_ranges'].append({'start': 1, 'end': min_u - 1, 'label': '顶部保留'})
        if max_u < cabinet.total_u:
            result['reserved_ranges'].append({'start': max_u + 1, 'end': cabinet.total_u, 'label': '底部保留'})

    return APIResponse.success(data=result, message="获取成功")



@cabinet_bp.route("/<int:cabinet_id>/stats", methods=["GET"])
@doc(summary="获取机柜统计信息", tags=["机柜"], parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError", 500: "ApiError"})
@login_required
def get_cabinet_stats(cabinet_id):
    """获取机柜统计信息
    
    Args:
        cabinet_id: 机柜ID
    
    Returns:
        JSON: 机柜统计信息,包括设备数、U位使用率、功率使用率等
    """
    try:
        from app.services.cabinet_service import CabinetService
        
        cabinet_service = CabinetService(CabinetRepository())
        stats = cabinet_service.get_cabinet_stats(cabinet_id)
        
        if not stats:
            return APIResponse.error(
                message="机柜不存在",
                error_code="NOT_FOUND",
                status_code=404
            )
        
        return APIResponse.success(data=stats, message="获取机柜统计信息成功")
    
    except Exception as e:
        logger.error("获取机柜统计信息失败: %s", e)
        return APIResponse.error(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            status_code=500
        )


@cabinet_bp.route("/<int:cabinet_id>/u-positions/allocate", methods=["POST"])
@doc(summary="智能分配U位", tags=["机柜"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/SmartUAssign"}}}}, parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError", 500: "ApiError"})
@login_required
@permission_required('cabinet:update')
def allocate_u_position(cabinet_id):
    """智能分配U位

    Args:
        cabinet_id: 机柜ID

    Request Body:
        height_u: 设备高度(U)
        device_spacing: 设备间距(U),默认0（设备编辑场景）
        allocation_strategy: 分配策略: bottom_up, top_down, best_fit
        min_u: 可用范围起始U位（保留区域）
        max_u: 可用范围结束U位（保留区域）

    Returns:
        JSON: 分配结果,包含分配的U位
    """
    try:
        data = request.get_json()
        height_u = data.get('height_u')
        allocation_strategy = data.get('allocation_strategy', 'bottom_up')
        device_spacing = data.get('device_spacing', 0)
        min_u = data.get('min_u', 1)
        max_u = data.get('max_u')  # 缺省时由机柜 total_u 决定

        if not height_u:
            return APIResponse.error(
                message="缺少height_u参数",
                error_code="BAD_REQUEST",
                status_code=400
            )

        if max_u is None:
            max_u = cabinet_service.get_by_id(cabinet_id).total_u

        from app.utils.cabinet_utils import CabinetUCalculator, UPositionRange, DeviceConstraint
        cabinet = cabinet_service.get_by_id(cabinet_id)
        if not cabinet:
            return APIResponse.error(message="机柜不存在", error_code="CABINET_NOT_FOUND", status_code=404)

        devices = [d.to_dict() for d in cabinet.devices]

        from app.services.cabinet_service import _parse_strategy
        strategy = _parse_strategy(allocation_strategy)

        if device_spacing > 0:
            free_ranges = CabinetUCalculator.get_free_ranges(
                devices, cabinet.total_u,
                include_spacing=True,
                device_spacing=device_spacing,
            )
        else:
            free_ranges = CabinetUCalculator.get_free_ranges(
                devices, cabinet.total_u,
                include_spacing=False,
            )

        usable = []
        for r in free_ranges:
            start = max(r.start, min_u)
            end = min(r.end, max_u)
            if start <= end:
                usable.append(UPositionRange(start, end))

        suitable = [r for r in usable if r.height >= height_u]
        if not suitable:
            return APIResponse.error(
                message='机柜空间不足，无法分配U位',
                error_code="ALLOCATION_FAILED",
                status_code=400
            )

        constraint = DeviceConstraint(
            min_u_position=min_u,
            max_u_position=max_u,
        )
        result = CabinetUCalculator._select_position_by_strategy(
            suitable, height_u, strategy, constraint
        )

        return APIResponse.success(data={'u_position': result}, message="U位分配成功")

    except Exception as e:
        logger.error("U位分配失败: %s", e)
        return APIResponse.error(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            status_code=500
        )


@cabinet_bp.route("/<int:cabinet_id>/validate-capacity", methods=["POST"])
@doc(summary="验证机柜容量", tags=["机柜"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CabinetCapacityValidate"}}}}, parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError", 500: "ApiError"})
@login_required
def validate_cabinet_capacity(cabinet_id):
    """验证机柜容量和规划合理性
    
    Args:
        cabinet_id: 机柜ID
    
    Request Body:
        new_device: 新设备信息(可选)
        device_spacing: 设备间距(U),默认2
        min_height_for_spacing: 需要间距的最小设备高度,默认2
        max_usage_rate: 最大使用率(%),默认90
    
    Returns:
        JSON: 容量验证结果
    """
    try:
        from app.services.cabinet_service import CabinetService
        
        data = request.get_json(silent=True) or {}
        new_device = data.get('new_device', {})
        device_spacing = data.get('device_spacing', 2)
        min_height_for_spacing = data.get('min_height_for_spacing', 2)
        max_usage_rate = data.get('max_usage_rate', 90.0)
        
        if new_device:
            new_height = new_device.get('height_u', 1)
            capacity_check = CabinetService.check_capacity_with_spacing(
                cabinet_id, new_height, device_spacing, min_height_for_spacing
            )
        else:
            capacity_check = None
        
        usage_info = CabinetService.get_cabinet_usage_with_spacing(cabinet_id, device_spacing)
        
        if not usage_info:
            return APIResponse.error(
                message="机柜不存在",
                error_code="NOT_FOUND",
                status_code=404
            )
        
        is_overloaded = usage_info['usage_rate_with_spacing'] > max_usage_rate
        
        result = {
            'cabinet_id': cabinet_id,
            'usage_info': usage_info,
            'capacity_check': capacity_check,
            'is_overloaded': is_overloaded,
            'max_usage_rate': max_usage_rate,
            'recommendation': '机柜使用率正常' if not is_overloaded else f'机柜使用率超过{max_usage_rate}%,建议优化'
        }
        
        return APIResponse.success(data=result, message="机柜容量验证完成")
    
    except Exception as e:
        logger.error("验证机柜容量失败: %s", e)
        return APIResponse.error(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            status_code=500
        )


@cabinet_bp.route("/<int:cabinet_id>/optimize-layout", methods=["POST"])
@doc(summary="优化机柜布局", tags=["机柜"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CabinetOptimize"}}}}, parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required('cabinet:update')
def optimize_cabinet_layout(cabinet_id):
    """优化机柜布局
    
    Args:
        cabinet_id: 机柜ID
    
    Request Body:
        strategy: 优化策略(可选): compact, balance, power_optimized
        device_spacing: 设备间距(U),默认2
    
    Returns:
        JSON: 优化结果,包含优化建议
    """
    try:
        from app.services.cabinet_service import CabinetService
        
        data = request.get_json(silent=True) or {}
        strategy = data.get('strategy', 'compact')
        device_spacing = data.get('device_spacing', 2)
        
        result = CabinetService.optimize_cabinet_layout(cabinet_id, strategy, device_spacing)
        
        if result['success']:
            return APIResponse.success(data=result, message="机柜布局优化成功")
        else:
            return APIResponse.error(
                message=result.get('message', '机柜布局优化失败'),
                error_code="OPTIMIZATION_FAILED",
                status_code=400
            )
    
    except Exception as e:
        logger.error("优化机柜布局失败: %s", e)
        return APIResponse.error(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            status_code=500
        )


@cabinet_bp.route("/<int:cabinet_id>/customer", methods=["PUT"])
@doc(summary="更新机柜客户", tags=["机柜"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CabinetCustomerUpdate"}}}}, parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 500: "ApiError"})
@login_required
@permission_required('cabinet:update')
@transactional
def update_cabinet_customer(cabinet_id):
    """更新机柜客户
    
    Args:
        cabinet_id: 机柜ID
    
    Request Body:
        customer_id: 客户ID,None表示清除客户
    
    Returns:
        JSON: 更新结果
    """
    try:
        data = request.get_json()
        customer_id = data.get('customer_id')

        result = cabinet_service.update_cabinet_customer(cabinet_id, customer_id)

        return APIResponse.success(
            data={'cabinet_id': cabinet_id, 'customer_id': customer_id},
            message="机柜客户更新成功"
        )
    
    except RecordNotFoundError:
        return APIResponse.error(
            message="机柜不存在",
            error_code="CABINET_NOT_FOUND",
            status_code=404
        )
    except Exception as e:
        logger.error("更新机柜客户失败: %s", e)
        return APIResponse.error(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            status_code=500
        )


@cabinet_bp.route("/by-room/<int:room_id>", methods=["GET"])
@doc(summary="根据机房ID获取机柜列表", tags=["机柜"], parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "CabinetResponse", 500: "ApiError"})
@login_required
def get_cabinets_by_room(room_id):
    """根据机房ID获取机柜列表
    
    Args:
        room_id: 机房ID
    
    Returns:
        JSON: 机柜列表
    """
    try:
        from app.services.cabinet_service import CabinetService
        
        cabinets = CabinetService(CabinetRepository()).get_cabinets_by_room(room_id)
        
        return APIResponse.success(
            data=cabinets,
            message=f"获取机房 {room_id} 的机柜列表成功"
        )
    
    except Exception as e:
        logger.error("获取机房机柜列表失败: %s", e)
        return APIResponse.error(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            status_code=500
        )


@cabinet_bp.route("/count", methods=["GET"])
@doc(summary="获取机柜总数", tags=["机柜"], parameters=[{"name": "room_id", "in": "query", "schema": {"type": "integer"}}], responses={200: "ApiResponse", 500: "ApiError"})
@login_required
def get_cabinet_count():
    """获取机柜总数
    
    Query Parameters:
        room_id: 机房ID(可选),如果提供则返回该机房的机柜数
    
    Returns:
        JSON: 机柜数量
    """
    try:
        from app.services.cabinet_service import CabinetService
        
        room_id = request.args.get('room_id', type=int)
        
        if room_id:
            count = CabinetService.get_cabinet_count_by_room(room_id)
            message = f"机房 {room_id} 的机柜数量"
        else:
            count = CabinetService.get_cabinet_count()
            message = "机柜总数"
        
        return APIResponse.success(
            data={'count': count},
            message=f"获取{message}成功"
        )
    
    except Exception as e:
        logger.error("获取机柜数量失败: %s", e)
        return APIResponse.error(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            status_code=500
        )


@cabinet_bp.route("/batch-delete", methods=["POST"])
@doc(summary="批量删除机柜", tags=["机柜"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchDelete"}}}}, responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("cabinet:delete")
@rate_limit_api
@transactional
def batch_delete_cabinets():
    """批量删除机柜
    
    Request Body:
        ids: 机柜ID列表
    
    Returns:
        JSON响应，包含删除结果
    """
    from app.services.cabinet_service import CabinetService
    
    data = request.get_json()
    if not data or "ids" not in data:
        return APIResponse.error(message="请提供要删除的机柜ID列表", status_code=400)
    
    ids = data.get("ids", [])
    if not isinstance(ids, list):
        return APIResponse.error(message="ID列表格式错误", status_code=400)
    
    cabinet_service = CabinetService(CabinetRepository())
    deleted_count = 0
    failed_ids = []
    
    for cabinet_id in ids:
        try:
            result = cabinet_service.delete_cabinet(cabinet_id)
            if result:
                deleted_count += 1
            else:
                failed_ids.append(cabinet_id)
        except Exception as e:
            logger.error("删除机柜 %d 失败: %s", cabinet_id, str(e))
            failed_ids.append(cabinet_id)
    
    message = f"成功删除 {deleted_count} 个机柜"
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



@cabinet_bp.route("/global-statistics", methods=["GET"])
@doc(summary="获取全局机柜统计汇总", tags=["机柜"], responses={200: "ApiResponse", 500: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def get_global_statistics():
    """获取全局机柜统计汇总
    
    Returns:
        JSON响应，包含全局机柜统计数据
    """
    try:
        stats = cabinet_service.get_global_statistics()
        return APIResponse.success(data=stats, message="获取全局机柜统计成功")
    except Exception as e:
        logger.error("获取全局机柜统计失败: %s", str(e))
        return APIResponse.error(message="服务器内部错误", status_code=500)


@cabinet_bp.route("/<int:cabinet_id>/with-devices", methods=["GET"])
@doc(summary="获取机柜及设备详情", tags=["机柜"], parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "CabinetResponse", 404: "ApiError", 500: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def get_cabinet_with_devices(cabinet_id):
    """获取机柜及设备详情
    
    Args:
        cabinet_id: 机柜ID
    
    Returns:
        JSON响应，包含机柜信息和设备列表
    """
    try:
        cabinet = cabinet_service.get_cabinet_with_devices(cabinet_id)
        if not cabinet:
            return APIResponse.error(message="机柜不存在", status_code=404)
        return APIResponse.success(data=cabinet, message="获取机柜详情成功")
    except Exception as e:
        logger.error("获取机柜详情失败: %s", str(e))
        return APIResponse.error(message="服务器内部错误", status_code=500)


@cabinet_bp.route("/<int:cabinet_id>/exists", methods=["GET"])
@doc(summary="检查机柜是否存在", tags=["机柜"], parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 500: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def cabinet_exists(cabinet_id):
    """检查机柜是否存在
    
    Args:
        cabinet_id: 机柜ID
    
    Returns:
        JSON响应，包含是否存在的结果
    """
    try:
        exists = cabinet_service.cabinet_exists(cabinet_id)
        return APIResponse.success(data={"exists": exists}, message="检查完成")
    except Exception as e:
        logger.error("检查机柜是否存在失败: %s", str(e))
        return APIResponse.error(message="服务器内部错误", status_code=500)


@cabinet_bp.route("/<int:cabinet_id>/update-usage", methods=["POST"])
@doc(summary="更新机柜使用情况", tags=["机柜"], parameters=[{"name": "cabinet_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 500: "ApiError"})
@login_required
@permission_required("cabinet:update")
@rate_limit_api
@transactional
def update_cabinet_usage(cabinet_id):
    """更新机柜使用情况
    
    重新计算机柜的used_u和used_power
    
    Args:
        cabinet_id: 机柜ID
    
    Returns:
        JSON响应，包含更新结果
    """
    try:
        cabinet_service.update_cabinet_usage(cabinet_id)

        return APIResponse.success(message="机柜使用情况更新成功")
    except Exception as e:
        logger.error("更新机柜使用情况失败: %s", str(e))
        return APIResponse.error(message="服务器内部错误", status_code=500)


@cabinet_bp.route("/by-number/<cabinet_number>", methods=["GET"])
@doc(summary="根据编号获取机柜", tags=["机柜"], parameters=[{"name": "cabinet_number", "in": "path", "required": True, "schema": {"type": "string"}}], responses={200: "CabinetResponse", 404: "ApiError", 500: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def get_cabinet_by_number(cabinet_number):
    """根据机柜编号获取机柜
    
    Args:
        cabinet_number: 机柜编号
    
    Returns:
        JSON响应，包含机柜信息
    """
    try:
        cabinet = cabinet_service.get_by_cabinet_number(cabinet_number)
        if not cabinet:
            return APIResponse.error(message="机柜不存在", status_code=404)
        return APIResponse.success(data=cabinet.to_dict(), message="获取机柜成功")
    except Exception as e:
        logger.error("根据编号获取机柜失败: %s", str(e))
        return APIResponse.error(message="服务器内部错误", status_code=500)
