# -*- coding: utf-8 -*-
"""
机房 API

提供机房管理的 RESTful API 端点。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request
from marshmallow import Schema, fields, validate

from app.exceptions.validation import ValidationError
from app.services.room_service import RoomService
from app.services.device_service import DeviceService
from app.api.base import APIResponse
from app.utils import (
    login_required,
    permission_required,
    rate_limit_api,
    validation_manager,
)
from app.utils.transactional import transactional, on_commit
from app.openapi.doc import doc, public
from app.persistence.room_repository import RoomRepository
from app.persistence.cabinet_repository import CabinetRepository
from app.persistence.device_repository import DeviceRepository
from app.utils.cache.manager import cache_manager
from app.services.switch_events import emit_resource_change_global

logger = get_logger(__name__)

room_bp = Blueprint("room", __name__)

_room_service = RoomService(
    room_repository=RoomRepository(),
    cabinet_repository=CabinetRepository(),
    device_repository=DeviceRepository(),
)
_device_service = DeviceService(DeviceRepository())




class RoomCreateSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    location = fields.Str(load_default="", validate=validate.Length(max=200))
    contact = fields.Str(load_default="", validate=validate.Length(max=100))
    contact_phone = fields.Str(load_default="", validate=validate.Length(max=50))


class RoomUpdateSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1, max=100))
    location = fields.Str(validate=validate.Length(max=200))
    contact = fields.Str(validate=validate.Length(max=100))
    contact_phone = fields.Str(validate=validate.Length(max=50))




def _get_room_or_404(room_id: int):
    """获取机房，不存在时返回 (None, error_response)"""
    room = _room_service.get_by_id(room_id)
    if not room:
        return None, APIResponse.error(
            message="机房不存在", error_code="ROOM_NOT_FOUND", status_code=404
        )
    return room, None




@room_bp.route("/", methods=["GET"])
@doc(summary="获取机房列表", tags=["机房"], parameters=[{"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "per_page", "in": "query", "schema": {"type": "integer", "default": 20}}, {"name": "search", "in": "query", "schema": {"type": "string"}}], responses={200: "RoomResponse", 500: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def list_rooms():
    """获取机房列表（支持分页、搜索过滤）

    Query Parameters:
        page (int): 页码，默认 1
        per_page (int): 每页数量，默认 20，最大 100
        search (str): 搜索关键词，模糊匹配名称/位置（可选）
    """
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search = request.args.get("search", type=str)

    try:
        if search:
            result = _room_service.room_repository.search(
                search_fields=["name", "location"],
                keyword=search,
                filters={"status": 0},
                page=page,
                page_size=per_page,
            )
            rooms = result.get("data", [])
            total = result.get("total_count", 0)
        else:
            rooms, total = _room_service.get_paginated(page=page, per_page=per_page, filters={"status": 0})

        return APIResponse.paginated(
            data=[room.to_dict() for room in rooms],
            page=page,
            per_page=per_page,
            total=total,
            message="获取机房列表成功",
        )
    except Exception as e:
        logger.error(f"获取机房列表失败: {e}", exc_info=True)
        return APIResponse.error(message="获取机房列表失败", error_code="ROOM_LIST_ERROR", status_code=500)


@room_bp.route("/<int:room_id>", methods=["GET"])
@doc(summary="获取机房详情", tags=["机房"], parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "RoomResponse", 404: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def get_room(room_id):
    """获取单个机房详情"""
    room, err = _get_room_or_404(room_id)
    if err:
        return err
    return APIResponse.success(data=room, message="获取机房信息成功")


@room_bp.route("/", methods=["POST"])
@doc(summary="创建机房", tags=["机房"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/RoomCreate"}}}}, responses={201: "RoomResponse", 409: "ApiError", 500: "ApiError"})
@login_required
@permission_required("room:create")
@rate_limit_api
@transactional
def create_room():
    """创建新机房

    Request Body: RoomCreateSchema
    """
    data = validation_manager.validate_schema(request.json, RoomCreateSchema())
    try:
        room = _room_service.create(data)
        on_commit(lambda: (
            cache_manager.invalidate_pattern("room:list:*"),
            cache_manager.invalidate_pattern("room:name:*"),
            emit_resource_change_global("room", "create", ids=[room.id]),
        ))
        return APIResponse.success(data=room.to_dict(), message="机房创建成功", status_code=201)
    except ValidationError as e:
        return APIResponse.error(message=str(e), error_code="ROOM_VALIDATION_ERROR", status_code=409)
    except Exception as e:
        logger.error(f"创建机房失败: {e}", exc_info=True)
        return APIResponse.error(message="创建机房失败", error_code="ROOM_CREATE_ERROR", status_code=500)


@room_bp.route("/<int:room_id>", methods=["PUT"])
@doc(summary="更新机房信息", tags=["机房"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/RoomUpdate"}}}}, parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "RoomResponse", 400: "ApiError", 404: "ApiError", 409: "ApiError", 500: "ApiError"})
@login_required
@permission_required("room:update")
@rate_limit_api
@transactional
def update_room(room_id):
    """更新机房信息

    Request Body: RoomUpdateSchema（所有字段可选）
    """
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    data = validation_manager.validate_schema(request.json, RoomUpdateSchema())
    if not data:
        return APIResponse.error(message="没有提供有效的更新字段", error_code="ROOM_NO_UPDATE", status_code=400)

    try:
        updated_room = _room_service.update(room_id, data)
        on_commit(lambda: (
            cache_manager.invalidate_pattern(f"room:{room_id}"),
            cache_manager.invalidate_pattern(f"room:active:{room_id}"),
            cache_manager.invalidate_pattern(f"room:stats:{room_id}"),
            cache_manager.invalidate_pattern(f"room:detail_stats:{room_id}"),
            cache_manager.invalidate_pattern("room:list:*"),
            cache_manager.invalidate_pattern("room:name:*"),
            emit_resource_change_global("room", "update", ids=[room_id]),
        ))
        return APIResponse.success(data=updated_room.to_dict(), message="机房更新成功")
    except ValidationError as e:
        return APIResponse.error(message=str(e), error_code="ROOM_VALIDATION_ERROR", status_code=409)
    except Exception as e:
        logger.error(f"更新机房失败: {e}", exc_info=True)
        return APIResponse.error(message="更新机房失败", error_code="ROOM_UPDATE_ERROR", status_code=500)


@room_bp.route("/<int:room_id>", methods=["DELETE"])
@doc(summary="删除机房", tags=["机房"], parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError", 409: "ApiError", 500: "ApiError"})
@login_required
@permission_required("room:delete")
@rate_limit_api
@transactional
def delete_room(room_id):
    """删除机房（软删除）"""
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    try:
        _room_service.delete(room_id)
        on_commit(lambda: (
            cache_manager.invalidate_pattern(f"room:{room_id}"),
            cache_manager.invalidate_pattern(f"room:active:{room_id}"),
            cache_manager.invalidate_pattern(f"room:stats:{room_id}"),
            cache_manager.invalidate_pattern(f"room:detail_stats:{room_id}"),
            cache_manager.invalidate_pattern("room:list:*"),
            cache_manager.invalidate_pattern("room:name:*"),
            emit_resource_change_global("room", "delete", ids=[room_id]),
        ))
        return APIResponse.success(message="机房删除成功")
    except ValidationError as e:
        return APIResponse.error(message=str(e), error_code="ROOM_DELETE_CONFLICT", status_code=409)
    except Exception as e:
        logger.error(f"删除机房失败: {e}", exc_info=True)
        return APIResponse.error(message="删除机房失败", error_code="ROOM_DELETE_ERROR", status_code=500)


@room_bp.route("/batch-delete", methods=["POST"])
@doc(summary="批量删除机房", tags=["机房"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchDelete"}}}}, responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("room:delete")
@rate_limit_api
@transactional
def batch_delete_rooms():
    """批量删除机房

    Request Body:
        ids (List[int]): 机房 ID 列表
    """
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")

    if not isinstance(ids, list) or not ids:
        return APIResponse.error(message="请提供有效的机房 ID 列表", status_code=400)

    deleted, failed = [], []
    for room_id in ids:
        try:
            _room_service.delete(room_id)
            deleted.append(room_id)
            rid = room_id  # 闭包捕获
            on_commit(lambda rid=rid: (
                cache_manager.invalidate_pattern(f"room:{rid}"),
                cache_manager.invalidate_pattern(f"room:active:{rid}"),
                cache_manager.invalidate_pattern(f"room:stats:{rid}"),
                cache_manager.invalidate_pattern(f"room:detail_stats:{rid}"),
                cache_manager.invalidate_pattern("room:list:*"),
                cache_manager.invalidate_pattern("room:name:*"),
                emit_resource_change_global("room", "delete", ids=[rid]),
            ))
        except Exception as e:
            logger.warning(f"批量删除机房 {room_id} 失败: {e}")
            failed.append({"id": room_id, "reason": str(e)})

    message = f"成功删除 {len(deleted)} 个机房"
    if failed:
        message += f"，{len(failed)} 个删除失败"

    return APIResponse.success(
        data={"deleted_count": len(deleted), "failed_count": len(failed), "failed": failed},
        message=message,
    )


@room_bp.route("/<int:room_id>/cabinets", methods=["GET"])
@doc(summary="获取机房下的机柜列表", tags=["机房"], parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "CabinetResponse", 404: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def get_room_cabinets(room_id):
    """获取机房下的所有机柜"""
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    cabinets = _room_service.get_cabinets(room_id)
    return APIResponse.success(
        data=[c.to_dict() for c in cabinets], message="获取机柜列表成功"
    )


@room_bp.route("/<int:room_id>/statistics", methods=["GET"])
@room_bp.route("/<int:room_id>/stats", methods=["GET"])  # 前端兼容别名
@doc(summary="获取机房统计信息", tags=["机房"], parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def get_room_statistics(room_id):
    """获取机房统计信息（/statistics 和 /stats 均可访问）"""
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    stats = _room_service.get_statistics(room_id)
    return APIResponse.success(data=stats, message="获取统计信息成功")


@room_bp.route("/<int:room_id>/devices", methods=["GET"])
@doc(summary="获取机房设备列表", tags=["机房"], parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def get_room_devices(room_id):
    """获取机房内的设备列表"""
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    devices = _device_service.get_devices_by_room(room_id)
    return APIResponse.success(data=devices, message="获取机房设备列表成功")



@room_bp.route("/all", methods=["GET"])
@doc(summary="获取所有机房列表（不分页）", tags=["机房"], responses={200: "RoomResponse", 500: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def get_all_rooms():
    """获取所有机房列表（不分页）
    
    用于下拉选择框等场景
    
    Returns:
        JSON响应，包含所有机房列表
    """
    try:
        rooms = _room_service.get_all_rooms()
        return APIResponse.success(
            data=rooms,
            message="获取机房列表成功"
        )
    except Exception as e:
        logger.error(f"获取所有机房列表失败: {str(e)}")
        return APIResponse.error(message=f"获取机房列表失败: {str(e)}", status_code=500)
