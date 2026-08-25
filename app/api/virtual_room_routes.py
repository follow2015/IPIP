# -*- coding: utf-8 -*-
"""虚拟机房 API 路由"""
from app.utils.logging import get_logger

from flask import Blueprint, request
from marshmallow import Schema, fields, validate

from app.api.base import APIResponse
from app.services.virtual_room_service import VirtualRoomService
from app.persistence.virtual_room_repository import VirtualRoomRepository
from app.openapi.doc import doc
from app.utils.auth import login_required, permission_required
from app.core.enums import NotificationTypeCode
from app.utils.transactional import transactional

logger = get_logger(__name__)

virtual_room_bp = Blueprint("virtual_rooms", __name__)

_service = VirtualRoomService(VirtualRoomRepository())




class VirtualRoomCreateSchema(Schema):
    """虚拟机房创建参数

    device_ids 允许为空（支持"先建空壳，后续通过 /members 接口添加成员"的工作流）。
    full_scan 对空成员有 early return（status=skipped, reason=no_switches），
    不会产生无意义的 Redis key 和进度记录。
    """
    name = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    description = fields.Str(validate=validate.Length(max=500), load_default="")
    device_ids = fields.List(fields.Int(), load_default=[])


class VirtualRoomUpdateSchema(Schema):
    """虚拟机房更新参数"""
    name = fields.Str(validate=validate.Length(min=1, max=255))
    description = fields.Str(validate=validate.Length(max=500))


class VirtualRoomMembersSchema(Schema):
    """虚拟机房成员更新参数"""
    device_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))




@virtual_room_bp.route("/", methods=["GET"])
@doc(summary="查询虚拟机房列表", tags=["虚拟机房"], responses={200: "VirtualRoomResponse"})
@login_required
@permission_required("switch:view")
def list_virtual_rooms():
    """查询虚拟机房列表"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    items, total = _service.get_paginated(page=page, per_page=per_page)
    return APIResponse.paginated(items, page, per_page, total)


@virtual_room_bp.route("/<int:virtual_room_id>", methods=["GET"])
@doc(summary="查询虚拟机房详情", tags=["虚拟机房"], responses={200: "VirtualRoomResponse", 404: "ApiError"})
@login_required
@permission_required("switch:view")
def get_virtual_room(virtual_room_id):
    """查询虚拟机房详情"""
    vr = _service.get_by_id(virtual_room_id)
    if not vr:
        return APIResponse.error("虚拟机房不存在", error_code="NOT_FOUND", status_code=404)
    return APIResponse.success(data=vr.to_dict(include_relations=True))


@virtual_room_bp.route("/", methods=["POST"])
@doc(summary="创建虚拟机房", tags=["虚拟机房"], responses={201: "VirtualRoomResponse", 400: "ApiError"})
@login_required
@permission_required("switch:create")
@transactional
def create_virtual_room():
    """创建虚拟机房"""
    schema = VirtualRoomCreateSchema()
    data = schema.load(request.get_json())
    try:
        vr = _service.create(data)
        return APIResponse.success(data=vr.to_dict(include_relations=True), message="虚拟机房创建成功", status_code=201)
    except Exception as e:
        return APIResponse.error(str(e), error_code="CREATE_FAILED", status_code=400)


@virtual_room_bp.route("/<int:virtual_room_id>", methods=["PUT"])
@doc(summary="更新虚拟机房", tags=["虚拟机房"], responses={200: "VirtualRoomResponse", 404: "ApiError"})
@login_required
@permission_required("switch:update")
@transactional
def update_virtual_room(virtual_room_id):
    """更新虚拟机房基本信息"""
    schema = VirtualRoomUpdateSchema()
    data = schema.load(request.get_json())
    try:
        vr = _service.update(virtual_room_id, data)
        return APIResponse.success(data=vr.to_dict(include_relations=True), message="虚拟机房更新成功")
    except Exception as e:
        return APIResponse.error(str(e), error_code="UPDATE_FAILED", status_code=400)


@virtual_room_bp.route("/<int:virtual_room_id>", methods=["DELETE"])
@doc(summary="删除虚拟机房", tags=["虚拟机房"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("switch:delete")
@transactional
def delete_virtual_room(virtual_room_id):
    """删除虚拟机房"""
    try:
        _service.delete(virtual_room_id)
        return APIResponse.success(message="虚拟机房删除成功")
    except Exception as e:
        return APIResponse.error(str(e), error_code="DELETE_FAILED", status_code=400)


@virtual_room_bp.route("/<int:virtual_room_id>/members", methods=["PUT"])
@doc(summary="更新虚拟机房成员", tags=["虚拟机房"], responses={200: "VirtualRoomResponse", 404: "ApiError"})
@login_required
@permission_required("switch:update")
@transactional
def update_virtual_room_members(virtual_room_id):
    """更新虚拟机房成员（全量替换）"""
    schema = VirtualRoomMembersSchema()
    data = schema.load(request.get_json())
    try:
        vr = _service.update_members(virtual_room_id, data["device_ids"])
        return APIResponse.success(data=vr.to_dict(include_relations=True), message="成员更新成功")
    except Exception as e:
        return APIResponse.error(str(e), error_code="UPDATE_FAILED", status_code=400)




@virtual_room_bp.route("/<int:virtual_room_id>/scan", methods=["POST"])
@doc(summary="触发虚拟机房扫描", tags=["虚拟机房"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("switch:config")
def scan_virtual_room(virtual_room_id):
    """触发虚拟机房扫描（异步）"""
    vr = _service.get_by_id(virtual_room_id)
    if not vr:
        return APIResponse.error("虚拟机房不存在", error_code="NOT_FOUND", status_code=404)

    from app.services.network_scanner_service import ScanOrchestrator, get_scan_progress
    from app.utils.cache import cache_manager

    scope = f"vr:{virtual_room_id}"
    existing_progress = get_scan_progress(scope)
    if existing_progress:
        phase = existing_progress.get("phase")
        completed = existing_progress.get("completed", 0)
        total = existing_progress.get("total", 0)
        if phase != "完成" and not (total > 0 and completed >= total):
            return APIResponse.error("已有扫描任务在进行中", error_code="SCAN_RUNNING", status_code=400)

    device_ids = _service.get_member_device_ids(virtual_room_id)
    redis_client = (
        cache_manager.primary_storage.redis_client
        if cache_manager.primary_storage else None
    )
    SCAN_LOCK_TTL = 7200
    acquired_locks = []
    if redis_client:
        for did in device_ids:
            lock_key = f"scan_lock:{did}"
            if redis_client.exists(lock_key):
                lock_scope = redis_client.get(lock_key)
                if lock_scope:
                    lock_scope_str = lock_scope if isinstance(lock_scope, str) else lock_scope.decode()
                    progress = get_scan_progress(lock_scope_str)
                    if progress and progress.get("phase") != "完成" and not (
                        progress.get("total", 0) > 0
                        and progress.get("completed", 0) >= progress.get("total", 0)
                    ):
                        for lk in acquired_locks:
                            redis_client.delete(lk)
                        return APIResponse.error(
                            f"以下交换机正在被其他扫描任务占用: [{did}]",
                            error_code="SCAN_CONFLICT",
                            status_code=400,
                        )
                redis_client.delete(lock_key)
            if redis_client.set(lock_key, scope, nx=True, ex=SCAN_LOCK_TTL):
                acquired_locks.append(lock_key)
            else:
                for lk in acquired_locks:
                    redis_client.delete(lk)
                return APIResponse.error(
                    f"交换机 {did} 正在被其他扫描任务占用",
                    error_code="SCAN_CONFLICT",
                    status_code=400,
                )

    from flask import current_app
    app_ref = current_app._get_current_object()

    def _async_scan():
        try:
            with app_ref.app_context():
                _vr = _service.get_by_id(virtual_room_id)
                _vr_name = _vr.name if _vr else f"虚拟机房#{virtual_room_id}"
                orchestrator = ScanOrchestrator()
                result = orchestrator.full_scan(virtual_room_id=virtual_room_id)
                if isinstance(result, dict) and result.get("reason") == "missing_n2n_connections":
                    from app.services.switch_events import emit_global_event
                    emit_global_event("room_scan_complete", {
                        "scope": scope,
                        "virtual_room_id": virtual_room_id,
                        "room_id": None,
                        "error": result.get("message", "缺少N2N连接"),
                        "reason": "missing_n2n_connections",
                    })
                    from app.services.notification_service import notification_service
                    notification_service.notify(
                    type=NotificationTypeCode.VIRTUAL_ROOM_SCAN_FAILED,
                    severity="warning",
                    title="虚拟机房扫描失败",
                    content=f"虚拟机房「{_vr_name}」缺少N2N连接，无法完成扫描",
                        payload={"virtual_room_id": virtual_room_id, "scope": scope, "reason": "missing_n2n_connections"},
                        source_module="scan",
                        target_type="broadcast",

                        idempotency_key=f"vr_scan_n2n:{virtual_room_id}:{int(__import__('time').time())}",
                    )
                    from app.services.scan_redis import ScanRedis, get_scan_redis_client
                    redis_client = get_scan_redis_client()
                    if redis_client:
                        sr = ScanRedis(redis_client)
                        sr.progress_set(scope, {
                            "scope": scope,
                            "room_id": 0,
                            "total": 0,
                            "completed": 0,
                            "failed": 1,
                            "phase": "failed",
                            "reason": "missing_n2n_connections",
                            "elapsed_seconds": 0,
                            "eta_seconds": 0,
                        })
                    return
                from app.services.switch_events import emit_global_event
                emit_global_event("room_scan_complete", {
                    "scope": scope,
                    "virtual_room_id": virtual_room_id,
                    "room_id": None,
                })
                from app.services.notification_service import notification_service
                notification_service.notify(
                    type=NotificationTypeCode.VIRTUAL_ROOM_SCAN_COMPLETE,
                    severity="info",
                    title="虚拟机房扫描完成",
                    content=f"虚拟机房「{_vr_name}」的网络扫描已完成",
                    payload={"virtual_room_id": virtual_room_id, "scope": scope},
                    source_module="scan",
                    target_type="broadcast",

                    idempotency_key=f"vr_scan_complete:{virtual_room_id}:{int(__import__('time').time())}",
                )
        except Exception as e:
            logger.error("异步虚拟机房扫描 %d 失败: %s", virtual_room_id, e)
            try:
                with app_ref.app_context():
                    from app.services.network_scanner_service import ScanOrchestrator as _Orchestrator
                    from app.services.scan_redis import ScanRedis
                    redis_client = _Orchestrator._get_redis_client()
                    if redis_client:
                        sr = ScanRedis(redis_client)
                        for did in device_ids:
                            lock_key = f"scan_lock:{did}"
                            try:
                                redis_client.delete(lock_key)
                            except Exception:
                                logger.warning("清理 scan_lock 失败: device_id=%d", did, exc_info=True)
                        progress_key = f"ipm:scan_progress:{scope}"
                        try:
                            redis_client.delete(progress_key)
                        except Exception:
                            logger.warning("清理扫描进度 key 失败: scope=%s", scope, exc_info=True)
                    from app.services.switch_events import emit_global_event
                    fail_progress = {
                        "scope": scope,
                        "room_id": 0,
                        "total": 0,
                        "completed": 0,
                        "failed": 1,
                        "phase": "完成",
                        "elapsed_seconds": 0,
                        "eta_seconds": 0,
                    }
                    if redis_client:
                        sr = ScanRedis(redis_client)
                        sr.progress_set(scope, fail_progress)
                    emit_global_event("scan_progress", fail_progress)
                    emit_global_event("room_scan_complete", {
                        "scope": scope,
                        "virtual_room_id": virtual_room_id,
                        "room_id": None,
                        "error": str(e),
                    })
                    from app.services.notification_service import notification_service
                    _vr_err = _service.get_by_id(virtual_room_id)
                    _vr_err_name = _vr_err.name if _vr_err else f"虚拟机房#{virtual_room_id}"
                    notification_service.notify(
                        type=NotificationTypeCode.VIRTUAL_ROOM_SCAN_FAILED,
                        severity="warning",
                        title="虚拟机房扫描异常",
                        content=f"虚拟机房「{_vr_err_name}」扫描异常: {str(e)[:200]}",
                        payload={"virtual_room_id": virtual_room_id, "scope": scope},
                        source_module="scan",
                        target_type="broadcast",

                        idempotency_key=f"vr_scan_err:{virtual_room_id}:{int(__import__('time').time())}",
                    )
            except Exception:
                logger.warning("异步虚拟机房扫描 %d 失败后清理/通知失败", virtual_room_id, exc_info=True)

    from app.utils.concurrency.task_executor import task_executor
    task_executor.submit("scan_virtual_room", _async_scan)
    return APIResponse.success(message="虚拟机房扫描已启动")


@virtual_room_bp.route("/<int:virtual_room_id>/scan/progress", methods=["GET"])
@doc(summary="查询虚拟机房扫描进度", tags=["虚拟机房"], responses={200: "ApiResponse"})
@login_required
def scan_virtual_room_progress(virtual_room_id):
    """查询虚拟机房扫描进度"""
    scope = f"vr:{virtual_room_id}"
    from app.services.network_scanner_service import get_scan_progress
    progress = get_scan_progress(scope)
    return APIResponse.success(data={"progress": progress})
