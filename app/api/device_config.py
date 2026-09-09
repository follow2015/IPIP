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
from app.utils.auth import get_current_user_id
from app.utils.idempotency import redis_lock
from app.utils.transactional import transactional
from app.exceptions.validation import ValidationError

logger = get_logger(__name__)

device_config_bp = Blueprint("device_config", __name__)

_device_config_service = DeviceConfigService(DeviceConfigBackupRepository(), DeviceConfigChangeRepository())


class ConfigChangeRequestSchema(Schema):
    """提交配置变更请求Schema（字段名对齐 DeviceConfigChange 模型）"""
    class Meta:
        unknown = EXCLUDE
    change_summary = fields.Str(
        required=True, validate=validate.Length(min=1, max=500),
        error_messages={"required": "变更摘要不能为空"},
    )
    change_detail = fields.Str(allow_none=True)
    backup_id = fields.Int(allow_none=True)




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
    config = _device_config_service.get_latest_config(device_id)
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
    history = _device_config_service.get_config_history(device_id)
    return APIResponse.success(data=[h.to_dict() for h in history.get("data", [])])


@device_config_bp.route("/<int:device_id>/config/backup", methods=["POST"])
@doc(summary="触发配置备份", tags=["设备配置"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={201: "DeviceConfigBackupResponse", 400: "ApiError"})
@login_required
@permission_required("device:update")
@api_exception_handler
@redis_lock(prefix="config_backup", key_param="device_id", ttl=300)
@transactional
def backup_device_config(device_id):
    """触发配置备份（SSH 实时采集 running-config 后落库）

    Path Parameters:
        device_id (int): 设备ID
    """
    result = _device_config_service.capture_backup_from_device(device_id)
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
    change = _device_config_service.submit_change(
        device_id,
        validated_data.get("change_summary"),
        requested_by=get_current_user_id(),
        backup_id=validated_data.get("backup_id"),
        change_detail=validated_data.get("change_detail"),
    )
    return APIResponse.success(data=change.to_dict(), message="配置变更请求提交成功", status_code=201)


@device_config_bp.route("/<int:device_id>/config/changes", methods=["GET"])
@doc(summary="获取配置变更审批列表", tags=["设备配置"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "DeviceConfigChangeResponse", 404: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def list_config_changes(device_id):
    """获取配置变更审批列表

    Path Parameters:
        device_id (int): 设备ID
    """
    changes = _device_config_service.list_changes(device_id)
    return APIResponse.success(data=[c.to_dict() for c in changes])


@device_config_bp.route("/<int:device_id>/config/changes/<int:change_id>/<action>", methods=["POST"])
@doc(summary="审批配置变更请求", tags=["设备配置"], parameters=[{"name": "device_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "change_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "action", "in": "path", "required": True, "schema": {"type": "string", "enum": ["approve", "reject"]}}], responses={200: "DeviceConfigChangeResponse", 400: "ApiError"})
@login_required
@permission_required("device:update")
@api_exception_handler
@transactional
def review_config_change(device_id, change_id, action):
    """审批配置变更请求

    Path Parameters:
        device_id (int): 设备ID
        change_id (int): 变更请求ID
        action (str): approve 或 reject
    """
    if action not in ("approve", "reject"):
        raise ValidationError("操作类型必须为 approve 或 reject")

    change = _device_config_service.review_change(
        device_id, change_id, action, approved_by=get_current_user_id(),
    )
    message = "已批准" if action == "approve" else "已拒绝"
    return APIResponse.success(data=change.to_dict(), message=message)
