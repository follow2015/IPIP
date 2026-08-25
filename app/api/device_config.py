# -*- coding: utf-8 -*-
"""
设备配置管理 API

提供设备配置快照、变更历史、备份和变更请求的 RESTful API 端点。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request
from marshmallow import Schema, fields, validate, EXCLUDE

from app.openapi.doc import doc, public
from app.api.base import APIResponse, api_exception_handler
from app.services.device_config_service import DeviceConfigService
from app.persistence.device_config_backup_repository import DeviceConfigBackupRepository, DeviceConfigChangeRepository
from app.utils import login_required, permission_required, rate_limit_api
from app.utils.idempotency import redis_lock
from app.utils.transactional import transactional
from app.exceptions.validation import ValidationError

logger = get_logger(__name__)

device_config_bp = Blueprint("device_config", __name__)

_device_config_service = DeviceConfigService(DeviceConfigBackupRepository(), DeviceConfigChangeRepository())


class ConfigChangeRequestSchema(Schema):
    """提交配置变更请求Schema"""
    class Meta:
        unknown = EXCLUDE
    change_type = fields.Str(validate=validate.Length(max=50), allow_none=True)
    content = fields.Str(allow_none=True)
    description = fields.Str(validate=validate.Length(max=500), allow_none=True)




@device_config_bp.route("/<int:device_id>/config", methods=["GET"])
@doc(summary="获取设备最新配置快照", tags=["设备配置"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceConfigBackupResponse", 404: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_device_config(device_id):
    """获取设备最新配置快照

    Path Parameters:
        device_id (int): 设备ID
    """
    config = _device_config_service.get_latest_backup(device_id)
    if not config:
        return APIResponse.success(data={})
    return APIResponse.success(data=config.to_dict())


@device_config_bp.route("/<int:device_id>/config/history", methods=["GET"])
@doc(summary="获取配置变更历史", tags=["设备配置"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceConfigBackupResponse", 404: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def get_config_history(device_id):
    """获取配置变更历史

    Path Parameters:
        device_id (int): 设备ID
    """
    history = _device_config_service.get_backup_history(device_id)
    return APIResponse.success(data=[h.to_dict() for h in history])


@device_config_bp.route("/<int:device_id>/config/backup", methods=["POST"])
@doc(summary="触发配置备份", tags=["设备配置"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={201: "DeviceConfigBackupResponse", 400: "ApiError"})
@login_required
@permission_required("device:update")
@api_exception_handler
@redis_lock(prefix="config_backup", key_param="device_id", ttl=300)
@transactional
def backup_device_config(device_id):
    """触发配置备份

    Path Parameters:
        device_id (int): 设备ID
    """
    result = _device_config_service.create_backup(device_id)
    return APIResponse.success(data=result.to_dict(), message="配置备份成功", status_code=201)


@device_config_bp.route("/<int:device_id>/config/change", methods=["POST"])
@doc(summary="提交配置变更请求", tags=["设备配置"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ConfigChangeRequest"}}}}, parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={201: "DeviceConfigChangeResponse", 400: "ApiError"})
@login_required
@permission_required("device:update")
@api_exception_handler
@redis_lock(prefix="config_change", key_param="device_id", ttl=300)
@transactional
def submit_config_change(device_id):
    """提交配置变更请求

    Path Parameters:
        device_id (int): 设备ID

    Request Body: 配置变更参数
    """
    data = request.get_json()
    if data is None:
        raise ValidationError("请求体不能为空")

    schema = ConfigChangeRequestSchema()
    errors = schema.validate(data)
    if errors:
        raise ValidationError(f"参数校验失败: {errors}")

    validated_data = schema.load(data)
    change = _device_config_service.submit_change(device_id, validated_data)
    return APIResponse.success(data=change.to_dict(), message="配置变更请求提交成功", status_code=201)
