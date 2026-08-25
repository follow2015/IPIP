# -*- coding: utf-8 -*-
"""
通知 API 端点

P0-b：轮询模式（无长连接），提供未读计数、列表、标记已读等端点。
P2：新增通知偏好设置端点。
"""
from flask import Blueprint, request

from app.api.base import APIResponse
from app.openapi.doc import doc
from app.services.notification_service import notification_service
from app.utils.auth import login_required
from app.utils.transactional import transactional

router = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@router.route("/unread-count", methods=["GET"])
@doc(summary="获取未读通知数", tags=["通知"], responses={200: "ApiResponse"})
@login_required
def unread_count():
    from flask import g
    count = notification_service.get_unread_count(g.current_user["user_id"])
    return APIResponse.success(data={"unread_count": count})


@router.route("", methods=["GET"])
@doc(summary="获取通知列表", tags=["通知"], responses={200: "ApiResponse"})
@login_required
def notification_list():
    from flask import g
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    unread_only = request.args.get("unread_only", "false").lower() == "true"

    result = notification_service.get_notifications(
        user_id=g.current_user["user_id"],
        page=page,
        per_page=min(per_page, 100),
        unread_only=unread_only,
    )
    return APIResponse.success(data=result)


@router.route("/mark-read", methods=["POST"])
@doc(summary="标记通知已读", tags=["通知"], responses={200: "ApiResponse"})
@login_required
@transactional
def mark_read():
    from flask import g
    data = request.get_json(silent=True) or {}
    notification_ids = data.get("notification_ids")

    count = notification_service.mark_read(
        user_id=g.current_user["user_id"],
        notification_ids=notification_ids,
    )
    return APIResponse.success(data={"marked_count": count})


@router.route("/<int:notification_id>/ack", methods=["POST"])
@doc(summary="确认通知", tags=["通知"], responses={200: "ApiResponse"})
@login_required
@transactional
def ack_notification(notification_id):
    from flask import g
    success = notification_service.mark_acked(
        user_id=g.current_user["user_id"],
        notification_id=notification_id,
    )
    if not success:
        return APIResponse.error("确认失败：通知不存在或无需确认", "NOT_FOUND", 404)
    return APIResponse.success(message="已确认")


@router.route("/read", methods=["DELETE"])
@doc(summary="清除已读通知", tags=["通知"], responses={200: "ApiResponse"})
@login_required
@transactional
def delete_read_notifications():
    from flask import g
    count = notification_service.delete_read(g.current_user["user_id"])
    return APIResponse.success(data={"deleted_count": count}, message=f"已清除 {count} 条已读通知")


@router.route("/preferences", methods=["GET"])
@doc(summary="获取通知偏好", tags=["通知"], responses={200: "ApiResponse"})
@login_required
def get_preferences():
    from flask import g
    prefs = notification_service.get_preferences(g.current_user["user_id"])
    return APIResponse.success(data=prefs)


@router.route("/preferences", methods=["PUT"])
@doc(summary="更新通知偏好", tags=["通知"], responses={200: "ApiResponse"})
@login_required
@transactional
def update_preferences():
    from flask import g
    data = request.get_json(silent=True) or {}
    if not data:
        return APIResponse.error("请求体不能为空", "BAD_REQUEST", 400)
    prefs = notification_service.update_preferences(g.current_user["user_id"], data)
    return APIResponse.success(data=prefs)
