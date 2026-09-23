# -*- coding: utf-8 -*-
"""
机房 API

提供机房管理的 RESTful API 端点。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request
from marshmallow import Schema

from app.exceptions import PresetResponseError
from app.exceptions.base import BaseAppException
from app.exceptions.validation import ValidationError
from app.exceptions.business import LayoutMarkerVersionConflict, ResourceConflictError
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




from app.schemas.room import (
    RoomChannelCreateSchema,
    RoomChannelUpdateSchema,
    RoomCreateSchema,
    RoomLayoutMarkerCreateSchema,
    RoomLayoutMarkerUpdateSchema,
    RoomUpdateSchema,
)

def _get_room_or_404(room_id: int):
    """获取机房，不存在时返回 (None, error_response)"""
    room = _room_service.get_by_id(room_id)
    if not room:
        return None, APIResponse.error(
            message="机房不存在", error_code="ROOM_NOT_FOUND", status_code=404
        )
    return room, None




@room_bp.route("/", methods=["GET"])
@doc(summary="获取机房列表", tags=["机房"], parameters=[{"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "per_page", "in": "query", "schema": {"type": "integer", "default": 20}}, {"name": "search", "in": "query", "schema": {"type": "string"}}, {"name": "building", "in": "query", "schema": {"type": "string"}}, {"name": "floor", "in": "query", "schema": {"type": "string"}}, {"name": "status", "in": "query", "schema": {"type": "integer"}}], responses={200: "RoomResponse", 500: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def list_rooms():
    """获取机房列表（支持分页、搜索与楼栋/楼层/状态筛选）

    Query Parameters:
        page (int): 页码，默认 1
        per_page (int): 每页数量，默认 20，最大 100
        search (str): 搜索关键词，模糊匹配名称/位置（可选）
        building (str): 按楼栋筛选（可选，前端 FilterBar 联想下拉）
        floor (str): 按楼层筛选（可选）
        status (int): 按状态筛选（可选；不传默认只看正常机房）
    """
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search = request.args.get("search", type=str)
    building = request.args.get("building", type=str)
    floor = request.args.get("floor", type=str)
    status = request.args.get("status", type=int)

    filters: dict = {"status": status} if status is not None else {"status": 0}
    if building:
        filters["building"] = building
    if floor:
        filters["floor"] = floor

    try:
        if search:
            result = _room_service.room_repository.search(
                search_fields=["name", "location"],
                keyword=search,
                filters=filters,
                page=page,
                page_size=per_page,
            )
            rooms = result.get("data", [])
            total = result.get("total_count", 0)
        else:
            rooms, total = _room_service.get_paginated(page=page, per_page=per_page, filters=filters)

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


@room_bp.route("/overview", methods=["GET"])
@doc(summary="跨机房总览", tags=["机房"], responses={200: "RoomOverviewResponse", 500: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def get_rooms_overview():
    """获取跨机房总览（按 building 分组）

    汇总各机房的机柜数、U 位利用率、功率利用率与状态分布；同一楼栋的机房聚在一起，
    未填 building 的归入"未分组"并排在最后（设计文档 §2.3 / §3.3）。
    """
    try:
        return APIResponse.success(
            data={"groups": _room_service.get_overview()},
            message="获取机房总览成功",
        )
    except Exception as e:
        logger.error(f"获取机房总览失败: {e}", exc_info=True)
        return APIResponse.error(
            message="获取机房总览失败", error_code="ROOM_OVERVIEW_ERROR", status_code=500
        )


@room_bp.route("/buildings", methods=["GET"])
@doc(summary="获取楼栋列表", tags=["机房"], responses={200: "RoomBuildingsResponse", 500: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def get_room_buildings():
    """获取当前已使用的楼栋去重值（供机房表单的联想选项，设计文档 §2.4）"""
    try:
        return APIResponse.success(
            data={"buildings": _room_service.get_buildings()},
            message="获取楼栋列表成功",
        )
    except Exception as e:
        logger.error(f"获取楼栋列表失败: {e}", exc_info=True)
        return APIResponse.error(
            message="获取楼栋列表失败", error_code="ROOM_BUILDINGS_ERROR", status_code=500
        )


@room_bp.route("/floors", methods=["GET"])
@doc(
    summary="获取楼层列表",
    tags=["机房"],
    parameters=[
        {
            "name": "building",
            "in": "query",
            "required": False,
            "schema": {"type": "string"},
            "description": "限定楼栋；不传则返回全部楼栋出现过的楼层",
        }
    ],
    responses={200: "RoomFloorsResponse", 500: "ApiError"},
)
@login_required
@permission_required("room:view")
@rate_limit_api
def get_room_floors():
    """获取当前已使用的楼层去重值（供表单联想与总览页楼层筛选）

    支持 `?building=A栋` 联动过滤：A 栋与 B 栋各自的"3层"含义不同，
    不限定楼栋会让下拉里出现无法区分的重复项。
    """
    try:
        building = request.args.get("building") or None
        return APIResponse.success(
            data={"floors": _room_service.get_floors(building)},
            message="获取楼层列表成功",
        )
    except Exception as e:
        logger.error(f"获取楼层列表失败: {e}", exc_info=True)
        return APIResponse.error(
            message="获取楼层列表失败", error_code="ROOM_FLOORS_ERROR", status_code=500
        )


@room_bp.route("/name-options", methods=["GET"])
@doc(summary="机房名称联想选项", tags=["机房"], responses={200: "ApiResponse", 500: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def get_room_name_options():
    """机房名称联想选项（[{name, room_count}]，实施计划 D3 名称强联想）

    前端据此提示"将并入「X」机房组（现有 N 条记录）"；不在选项中的名称视为新建组。
    """
    try:
        return APIResponse.success(
            data={"options": _room_service.get_room_name_options()},
            message="获取名称联想选项成功",
        )
    except Exception as e:
        logger.error(f"获取名称联想选项失败: {e}", exc_info=True)
        return APIResponse.error(
            message="获取名称联想选项失败", error_code="ROOM_NAME_OPTIONS_ERROR", status_code=500
        )


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
    except ResourceConflictError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_NUMBER_CONFLICT", status_code=409
        ) from e
    except BaseAppException:
        raise
    except Exception as e:
        logger.error(f"创建机房失败: {e}", exc_info=True)
        raise PresetResponseError(
            message="创建机房失败", error_code="ROOM_CREATE_ERROR", status_code=500
        ) from e


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
    except ResourceConflictError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_NUMBER_CONFLICT", status_code=409
        ) from e
    except BaseAppException:
        raise
    except Exception as e:
        logger.error(f"更新机房失败: {e}", exc_info=True)
        raise PresetResponseError(
            message="更新机房失败", error_code="ROOM_UPDATE_ERROR", status_code=500
        ) from e


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
    except ResourceConflictError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_DELETE_CONFLICT", status_code=409
        ) from e
    except Exception as e:
        logger.error(f"删除机房失败: {e}", exc_info=True)
        raise PresetResponseError(
            message="删除机房失败", error_code="ROOM_DELETE_ERROR", status_code=500
        ) from e


@room_bp.route("/<int:room_id>/force", methods=["DELETE"])
@doc(
    summary="强制删除机房",
    tags=["机房"],
    parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
    responses={200: "ApiResponse", 404: "ApiError", 500: "ApiError"},
)
@login_required
@permission_required("room:force_delete")
@rate_limit_api
@transactional
def force_delete_room(room_id):
    """强制删除机房：跳过依赖检查，级联物理删除机柜、设备及其全部关联数据

    [WARN] **不可恢复**。

    为什么用独立端点而不是 `DELETE /rooms/{id}?force=true`：权限位不同
    （`room:force_delete` vs `room:delete`）。独立端点让权限由装饰器天然分离，
    不必在函数体里手写条件检查——那种写法一旦漏掉就是越权，而这里漏掉是 403。
    """
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    try:
        counts = _room_service.force_delete(room_id)
        on_commit(lambda: (
            cache_manager.invalidate_pattern("room:*"),
            cache_manager.invalidate_pattern("cabinet:*"),
            cache_manager.invalidate_pattern("device:*"),
            cache_manager.invalidate_pattern("devices:*"),
            emit_resource_change_global("room", "force_delete", ids=[room_id]),
        ))
        return APIResponse.success(
            data={"deleted": counts}, message="机房及其关联数据已强制删除"
        )
    except ValidationError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_FORCE_DELETE_INVALID", status_code=404
        ) from e
    except Exception as e:
        logger.error(f"强制删除机房失败: {e}", exc_info=True)
        raise PresetResponseError(
            message="强制删除机房失败", error_code="ROOM_FORCE_DELETE_ERROR", status_code=500
        ) from e


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




@room_bp.route("/<int:room_id>/channels", methods=["GET"])
@doc(summary="获取机房通道列表", tags=["机房"], parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "RoomChannelResponse", 404: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def get_room_channels(room_id):
    """获取机房下的所有通道配置（按列号升序）"""
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    channels = _room_service.get_channels(room_id)
    return APIResponse.success(
        data=[c.to_dict() for c in channels], message="获取通道列表成功"
    )


@room_bp.route("/<int:room_id>/channels", methods=["POST"])
@doc(summary="新增机房通道", tags=["机房"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/RoomChannelCreate"}}}}, parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={201: "RoomChannelResponse", 404: "ApiError", 409: "ApiError", 500: "ApiError"})
@login_required
@permission_required("room:layout_config")
@rate_limit_api
@transactional
def create_room_channel(room_id):
    """新增通道配置

    Request Body: RoomChannelCreateSchema
    """
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    data = validation_manager.validate_schema(request.json, RoomChannelCreateSchema())
    try:
        channel = _room_service.create_channel(room_id, data)
        on_commit(lambda: (
            cache_manager.invalidate_pattern(f"room:channels:{room_id}"),
            emit_resource_change_global("room_channel", "create", ids=[room_id]),
        ))
        return APIResponse.success(
            data=channel.to_dict(), message="通道创建成功", status_code=201
        )
    except ResourceConflictError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_CHANNEL_CONFLICT", status_code=409
        ) from e
    except BaseAppException:
        raise
    except Exception as e:
        logger.error(f"新增机房通道失败: {e}", exc_info=True)
        raise PresetResponseError(
            message="新增机房通道失败", error_code="ROOM_CHANNEL_CREATE_ERROR", status_code=500
        ) from e


@room_bp.route("/<int:room_id>/channels/<int:channel_id>", methods=["PUT"])
@doc(summary="更新机房通道", tags=["机房"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/RoomChannelUpdate"}}}}, parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "channel_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "RoomChannelResponse", 400: "ApiError", 404: "ApiError", 409: "ApiError", 500: "ApiError"})
@login_required
@permission_required("room:layout_config")
@rate_limit_api
@transactional
def update_room_channel(room_id, channel_id):
    """更新通道配置

    Request Body: RoomChannelUpdateSchema（所有字段可选）
    """
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    data = validation_manager.validate_schema(request.json, RoomChannelUpdateSchema())
    if not data:
        return APIResponse.error(
            message="没有提供有效的更新字段", error_code="ROOM_CHANNEL_NO_UPDATE", status_code=400
        )

    try:
        channel = _room_service.update_channel(room_id, channel_id, data)
        on_commit(lambda: (
            cache_manager.invalidate_pattern(f"room:channels:{room_id}"),
            emit_resource_change_global("room_channel", "update", ids=[room_id]),
        ))
        return APIResponse.success(data=channel.to_dict(), message="通道更新成功")
    except ResourceConflictError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_CHANNEL_CONFLICT", status_code=409
        ) from e
    except BaseAppException:
        raise
    except Exception as e:
        logger.error(f"更新机房通道失败: {e}", exc_info=True)
        raise PresetResponseError(
            message="更新机房通道失败", error_code="ROOM_CHANNEL_UPDATE_ERROR", status_code=500
        ) from e


@room_bp.route("/<int:room_id>/channels/<int:channel_id>", methods=["DELETE"])
@doc(summary="删除机房通道", tags=["机房"], parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "channel_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError", 409: "ApiError", 500: "ApiError"})
@login_required
@permission_required("room:layout_config")
@rate_limit_api
@transactional
def delete_room_channel(room_id, channel_id):
    """删除通道配置"""
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    try:
        _room_service.delete_channel(room_id, channel_id)
        on_commit(lambda: (
            cache_manager.invalidate_pattern(f"room:channels:{room_id}"),
            emit_resource_change_global("room_channel", "delete", ids=[room_id]),
        ))
        return APIResponse.success(message="通道删除成功")
    except ValidationError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_CHANNEL_NOT_FOUND", status_code=404
        ) from e
    except Exception as e:
        logger.error(f"删除机房通道失败: {e}", exc_info=True)
        raise PresetResponseError(
            message="删除机房通道失败", error_code="ROOM_CHANNEL_DELETE_ERROR", status_code=500
        ) from e




@room_bp.route("/<int:room_id>/layout-markers", methods=["GET"])
@doc(summary="获取机房占位标记列表", tags=["机房"], parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "RoomLayoutMarkerResponse", 404: "ApiError"})
@login_required
@permission_required("room:view")
@rate_limit_api
def get_room_layout_markers(room_id):
    """获取机房下的所有占位标记（按行列升序）"""
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    markers = _room_service.get_layout_markers(room_id)
    return APIResponse.success(
        data=[m.to_dict() for m in markers], message="获取占位标记列表成功"
    )


@room_bp.route("/<int:room_id>/layout-markers", methods=["POST"])
@doc(summary="新增机房占位标记", tags=["机房"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/RoomLayoutMarkerCreate"}}}}, parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={201: "RoomLayoutMarkerResponse", 404: "ApiError", 409: "ApiError", 500: "ApiError"})
@login_required
@permission_required("room:layout_config")
@rate_limit_api
@transactional
def create_room_layout_marker(room_id):
    """新增占位标记

    Request Body: RoomLayoutMarkerCreateSchema
    """
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    data = validation_manager.validate_schema(request.json, RoomLayoutMarkerCreateSchema())
    try:
        marker = _room_service.create_layout_marker(room_id, data)
        on_commit(lambda: (
            cache_manager.invalidate_pattern(f"room:markers:{room_id}"),
            emit_resource_change_global("room_layout_marker", "create", ids=[room_id]),
        ))
        return APIResponse.success(
            data=marker.to_dict(), message="占位标记创建成功", status_code=201
        )
    except ResourceConflictError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_MARKER_CONFLICT", status_code=409
        ) from e
    except BaseAppException:
        raise
    except Exception as e:
        logger.error(f"新增机房占位标记失败: {e}", exc_info=True)
        raise PresetResponseError(
            message="新增机房占位标记失败", error_code="ROOM_MARKER_CREATE_ERROR", status_code=500
        ) from e


@room_bp.route("/<int:room_id>/layout-markers/<int:marker_id>", methods=["PUT"])
@doc(summary="更新机房占位标记", tags=["机房"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/RoomLayoutMarkerUpdate"}}}}, parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "marker_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "RoomLayoutMarkerResponse", 400: "ApiError", 404: "ApiError", 409: "ApiError", 500: "ApiError"})
@login_required
@permission_required("room:layout_config")
@rate_limit_api
@transactional
def update_room_layout_marker(room_id, marker_id):
    """更新占位标记

    Request Body: RoomLayoutMarkerUpdateSchema（所有字段可选）
    """
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    data = validation_manager.validate_schema(request.json, RoomLayoutMarkerUpdateSchema())
    if not data:
        return APIResponse.error(
            message="没有提供有效的更新字段", error_code="ROOM_MARKER_NO_UPDATE", status_code=400
        )

    try:
        marker = _room_service.update_layout_marker(room_id, marker_id, data)
        on_commit(lambda: (
            cache_manager.invalidate_pattern(f"room:markers:{room_id}"),
            emit_resource_change_global("room_layout_marker", "update", ids=[room_id]),
        ))
        return APIResponse.success(data=marker.to_dict(), message="占位标记更新成功")
    except ResourceConflictError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_MARKER_CONFLICT", status_code=409
        ) from e
    except BaseAppException:
        raise
    except Exception as e:
        logger.error(f"更新机房占位标记失败: {e}", exc_info=True)
        raise PresetResponseError(
            message="更新机房占位标记失败", error_code="ROOM_MARKER_UPDATE_ERROR", status_code=500
        ) from e


@room_bp.route("/<int:room_id>/layout-markers/batch", methods=["POST"])
@doc(
    summary="批量编辑机房占位标记（乐观锁）",
    tags=["机房"],
    request_body={"content": {"application/json": {"schema": {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["marker_id", "expected_version"],
                    "properties": {
                        "marker_id": {"type": "integer"},
                        "expected_version": {"type": "integer"},
                        "row_number": {"type": "integer"},
                        "col_number": {"type": "integer"},
                        "marker_type": {"type": "string"},
                        "label": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                },
            },
        },
    }}}},
    parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
    responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError", 409: "ApiError"},
)
@login_required
@permission_required("room:layout_config")
@rate_limit_api
@transactional
def batch_update_room_layout_markers(room_id):
    """批量编辑占位标记（WP-7：单一事务 + 乐观锁 CAS，消 lost-update）

    每项携带 expected_version（GET 接口随 marker 下发）。版本判据在 UPDATE
    谓词内——MySQL RR 下先读后比会被事务快照骗过。任一项版本过期 ⇒
    整批回滚并返回 409 ROOM_MARKER_VERSION_CONFLICT（可编程识别，消息
    定位每个冲突标记）。前端收到后应重新拉取布局再合并提交。

    Request Body: {items: [{marker_id, expected_version, ...字段}, ...]}
    """
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    payload = request.get_json(silent=True) or {}
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return APIResponse.error(
            message="请提供非空 items 数组",
            error_code="ROOM_MARKER_BATCH_EMPTY",
            status_code=400,
        )

    UPDATABLE = ("row_number", "col_number", "marker_type", "label", "notes")
    normalized = []
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict) or not isinstance(raw.get("marker_id"), int):
            return APIResponse.error(
                message=f"items[{idx}] 缺少合法的 marker_id",
                error_code="ROOM_MARKER_BATCH_BAD_ITEM",
                status_code=400,
            )
        expected = raw.get("expected_version")
        if not isinstance(expected, int) or expected < 0:
            return APIResponse.error(
                message=f"items[{idx}] 缺少合法的 expected_version（GET 接口下发的 version）",
                error_code="ROOM_MARKER_BATCH_BAD_ITEM",
                status_code=400,
            )
        fields = validation_manager.validate_schema(
            {k: raw[k] for k in UPDATABLE if k in raw},
            RoomLayoutMarkerUpdateSchema(),
        )
        if not fields:
            return APIResponse.error(
                message=f"items[{idx}] 没有提供有效的更新字段",
                error_code="ROOM_MARKER_NO_UPDATE",
                status_code=400,
            )
        normalized.append(
            {"marker_id": raw["marker_id"], "expected_version": expected, "fields": fields}
        )

    try:
        updated = _room_service.batch_update_layout_markers(room_id, normalized)
        on_commit(lambda: (
            cache_manager.invalidate_pattern(f"room:markers:{room_id}"),
            emit_resource_change_global("room_layout_marker", "update", ids=[room_id]),
        ))
        return APIResponse.success(
            data={"updated": [m.to_dict() for m in updated]},
            message="占位标记批量更新成功",
        )
    except LayoutMarkerVersionConflict as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_MARKER_VERSION_CONFLICT", status_code=409
        ) from e
    except ResourceConflictError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_MARKER_CONFLICT", status_code=409
        ) from e
    except ValidationError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_MARKER_NOT_FOUND", status_code=404
        ) from e
    except BaseAppException:
        raise
    except Exception as e:
        logger.error(f"批量更新机房占位标记失败: {e}", exc_info=True)
        raise PresetResponseError(
            message="批量更新占位标记失败",
            error_code="ROOM_MARKER_BATCH_UPDATE_ERROR",
            status_code=500,
        ) from e


@room_bp.route("/<int:room_id>/layout-markers/<int:marker_id>", methods=["DELETE"])
@doc(summary="删除机房占位标记", tags=["机房"], parameters=[{"name": "room_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "marker_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError", 409: "ApiError", 500: "ApiError"})
@login_required
@permission_required("room:layout_config")
@rate_limit_api
@transactional
def delete_room_layout_marker(room_id, marker_id):
    """删除占位标记"""
    _, err = _get_room_or_404(room_id)
    if err:
        return err

    try:
        _room_service.delete_layout_marker(room_id, marker_id)
        on_commit(lambda: (
            cache_manager.invalidate_pattern(f"room:markers:{room_id}"),
            emit_resource_change_global("room_layout_marker", "delete", ids=[room_id]),
        ))
        return APIResponse.success(message="占位标记删除成功")
    except ValidationError as e:
        raise PresetResponseError(
            message=e.message, error_code="ROOM_MARKER_NOT_FOUND", status_code=404
        ) from e
    except Exception as e:
        logger.error(f"删除机房占位标记失败: {e}", exc_info=True)
        raise PresetResponseError(
            message="删除机房占位标记失败", error_code="ROOM_MARKER_DELETE_ERROR", status_code=500
        ) from e


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
        logger.error(f"获取机房列表失败: {e}", exc_info=True)
        return APIResponse.error(message="获取机房列表失败", error_code="ROOM_LIST_ERROR", status_code=500)
