# -*- coding: utf-8 -*-
"""
设备存储管理 API 路由

全部数据访问通过 DeviceStorageService 完成，不直接执行裸 SQL。
与 device_connection.py 保持一致的架构风格：Blueprint / APIResponse / 统一权限装饰器。
"""
from flask import Blueprint, request
from marshmallow import Schema, fields, validate, EXCLUDE

from app.openapi.doc import doc, public
from app.services.device_storage_service import device_storage_service
from app.api.base import APIResponse, api_exception_handler
from app.utils import login_required, permission_required, rate_limit_api
from app.utils.transactional import transactional
from app.exceptions.validation import ValidationError

device_storage_bp = Blueprint(
    "device_storage", __name__, url_prefix="/api"
)


class StorageAddSchema(Schema):
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
    class Meta:
        unknown = EXCLUDE
    storage_config = fields.List(fields.Dict(), allow_none=True)


class StorageUpdateSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    storage_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    capacity = fields.Str(validate=validate.Length(max=50), allow_none=True)
    interface_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    manufacturer = fields.Str(validate=validate.Length(max=100), allow_none=True)
    model = fields.Str(validate=validate.Length(max=100), allow_none=True)
    serial_number = fields.Str(validate=validate.Length(max=100), allow_none=True)


class StorageSerialCheckSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    serial_number = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    exclude_id = fields.Int(allow_none=True)


class StorageBatchDeleteSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    storage_ids = fields.List(fields.Int(), required=True)


@device_storage_bp.route("/advanced/devices/<int:device_id>/storage/grouped", methods=["GET"])
@doc(summary="获取设备硬盘分组统计", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceStorageResponse", 404: "ApiError"})
@login_required
@permission_required('device:view')
@rate_limit_api
@api_exception_handler
def get_device_storage_grouped(device_id):
    try:
        data = device_storage_service.get_device_storage(device_id, grouped=True)
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="DEVICE_NOT_FOUND", status_code=404)
    return APIResponse.success(data=data, message="获取硬盘分组统计成功")


@device_storage_bp.route("/devices/<int:device_id>/storage", methods=["GET"])
@doc(summary="获取设备硬盘列表", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "grouped", "in": "query", "schema": {"type": "string"}}], responses={200: "DeviceStorageResponse", 404: "ApiError"})
@login_required
@permission_required('device:view')
@rate_limit_api
@api_exception_handler
def get_device_storage(device_id):
    grouped = request.args.get("grouped", "false").lower() == "true"
    try:
        data = device_storage_service.get_device_storage(device_id, grouped=grouped)
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="DEVICE_NOT_FOUND", status_code=404)
    return APIResponse.success(data=data, message="获取存储列表成功")


@device_storage_bp.route("/devices/<int:device_id>/storage", methods=["POST"])
@doc(summary="为设备添加硬盘", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/StorageAdd"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={201: "DeviceStorageResponse", 400: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def add_device_storage(device_id):
    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    storage_list = data.get("storage_list")
    if not storage_list:
        if not data.get("storage_type") and not data.get("template_id"):
            return APIResponse.error("存储类型或配件模板不能同时为空", status_code=400)
        if not data.get("capacity") and not data.get("template_id"):
            return APIResponse.error("容量或配件模板不能同时为空", status_code=400)

    try:
        device_storage_service.add_device_storage(
            device_id=device_id,
            storage_type=data.get("storage_type", ""),
            capacity=data.get("capacity", ""),
            count=data.get("count", 1),
            interface_type=data.get("interface_type"),
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            serial_number=data.get("serial_number"),
            storage_list=storage_list,
            template_id=data.get("template_id"),
        )
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="STORAGE_VALIDATION_ERROR", status_code=400)

    return APIResponse.success(message="硬盘添加成功", status_code=201)


@device_storage_bp.route("/devices/<int:device_id>/storage/config", methods=["PUT"])
@doc(summary="整机覆盖写入存储配置", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/StorageOverwrite"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def update_device_storage_config(device_id):
    data = request.get_json()
    if data is None:
        return APIResponse.error("请求数据不能为空", status_code=400)

    try:
        device_storage_service.update_device_storage_config(
            device_id, data.get("storage_config", [])
        )
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="STORAGE_VALIDATION_ERROR", status_code=400)

    return APIResponse.success(message="存储配置更新成功")


@device_storage_bp.route("/storage/<int:storage_id>", methods=["PUT"])
@doc(summary="更新单条硬盘信息", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/StorageUpdate"}}}}, parameters=[{"name": "storage_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceStorageResponse", 400: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def update_storage(storage_id):
    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    try:
        device_storage_service.update_device_storage(
            storage_id=storage_id,
            storage_type=data.get("storage_type"),
            capacity=data.get("capacity"),
            interface_type=data.get("interface_type"),
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            serial_number=data.get("serial_number"),
        )
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="STORAGE_VALIDATION_ERROR", status_code=400)

    return APIResponse.success(message="硬盘信息更新成功")


@device_storage_bp.route("/storage/<int:storage_id>", methods=["DELETE"])
@doc(summary="删除单条硬盘记录", tags=["设备"], parameters=[{"name": "storage_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def delete_storage(storage_id):
    try:
        device_storage_service.delete_device_storage(storage_id)
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="STORAGE_NOT_FOUND", status_code=404)

    return APIResponse.success(message="硬盘记录删除成功")


@device_storage_bp.route("/devices/<int:device_id>/storage", methods=["DELETE"])
@doc(summary="删除设备的全部硬盘记录", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def delete_device_storage_all(device_id):
    count = device_storage_service.delete_device_storage_by_device_id(device_id)

    return APIResponse.success(
        data={"deleted_count": count},
        message=f"已删除设备全部硬盘记录，共 {count} 条",
    )


@device_storage_bp.route("/devices/<int:device_id>/storage/batch", methods=["DELETE"])
@doc(summary="批量删除硬盘", tags=["设备"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required('device:update')
@rate_limit_api
@api_exception_handler
@transactional
def batch_delete_storage(device_id):
    data = request.get_json(silent=True) or {}
    storage_ids = data.get("storage_ids") or []
    if not storage_ids:
        return APIResponse.error("硬盘 ID 列表不能为空", status_code=400)

    result = device_storage_service.batch_delete_storage(storage_ids)
    return APIResponse.success(
        data=result,
        message=f"已删除 {len(result.get('deleted', []))} 条硬盘",
    )


@device_storage_bp.route("/advanced/storage/validate-serial", methods=["POST"])
@doc(summary="校验硬盘序列号唯一性", tags=["设备"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/StorageSerialCheck"}}}}, responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required('device:view')
@rate_limit_api
@api_exception_handler
def validate_serial_number():
    data = request.get_json(silent=True) or {}
    serial_number = data.get("serial_number")
    exclude_id    = data.get("exclude_id")

    result = device_storage_service.validate_serial_number(serial_number, exclude_id=exclude_id)

    return APIResponse.success(
        data={"available": result["is_valid"], "message": result["message"]},
        message="校验完成",
    )
