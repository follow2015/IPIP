# -*- coding: utf-8 -*-
"""
Webhook 配置 API 端点

提供 Webhook 渠道配置的 CRUD 和连通性测试功能，仅管理员可访问。
重构：API 层不再直接使用 db.session 或 Model.query，全部经由 WebhookConfigService。
"""
from app.utils.logging import get_logger

import requests
from flask import Blueprint, request, g

from app.api.base import APIResponse
from app.openapi.doc import doc
from app.models.webhook_config import validate_webhook_url
from app.services.webhook_config_service import webhook_config_service
from app.utils.auth import login_required
from app.utils.transactional import transactional
from app.core.enums import ChannelType
from app.exceptions.validation import ValidationError

logger = get_logger(__name__)

router = Blueprint("webhook_configs", __name__, url_prefix="/api/webhook-configs")


def _require_admin():
    """检查当前用户是否为管理员"""
    from app.services.user_service import UserService
    from app.persistence.user_repository import UserRepository
    from app.persistence.user_log_repository import UserLogRepository
    user_service = UserService(UserRepository(), UserLogRepository())
    user = user_service.get_by_id(g.current_user["user_id"])
    if not user or not user.is_admin():
        return False
    return True


@router.route("", methods=["GET"])
@doc(summary="列出 Webhook 配置", tags=["Webhook配置"], responses={200: "ApiResponse"})
@login_required
def list_webhook_configs():
    """列出所有 Webhook 配置（管理员）。"""
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    data = webhook_config_service.list_configs()
    return APIResponse.success(data=data)


@router.route("", methods=["POST"])
@doc(summary="创建 Webhook 配置", tags=["Webhook配置"], responses={200: "ApiResponse"})
@login_required
@transactional
def create_webhook_config():
    """创建 Webhook 配置（管理员）。"""
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    data = request.get_json(silent=True) or {}
    try:
        config = webhook_config_service.create_config(
            data, created_by=g.current_user["user_id"]
        )
    except ValidationError as e:
        error_code = "DUPLICATE_ERROR" if "已存在" in str(e) else "BAD_REQUEST"
        status_code = 409 if "已存在" in str(e) else 400
        return APIResponse.error(str(e), error_code, status_code)
    except ValueError as e:
        return APIResponse.error(str(e), "BAD_REQUEST", 400)

    return APIResponse.success(data=config.to_dict(), message="创建成功")


@router.route("/<int:config_id>", methods=["PUT"])
@doc(summary="更新 Webhook 配置", tags=["Webhook配置"], responses={200: "ApiResponse"})
@login_required
@transactional
def update_webhook_config(config_id):
    """更新 Webhook 配置（管理员）。"""
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    data = request.get_json(silent=True) or {}
    try:
        config = webhook_config_service.update_config(config_id, data)
    except ValueError as e:
        return APIResponse.error(str(e), "BAD_REQUEST", 400)

    if not config:
        return APIResponse.error("配置不存在", "NOT_FOUND", 404)
    return APIResponse.success(data=config.to_dict(), message="更新成功")


@router.route("/<int:config_id>", methods=["DELETE"])
@doc(summary="删除 Webhook 配置", tags=["Webhook配置"], responses={200: "ApiResponse"})
@login_required
@transactional
def delete_webhook_config(config_id):
    """删除 Webhook 配置（管理员）。"""
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    result = webhook_config_service.delete_config(config_id)
    if not result:
        return APIResponse.error("配置不存在", "NOT_FOUND", 404)
    return APIResponse.success(message="删除成功")


@router.route("/<int:config_id>/test", methods=["POST"])
@doc(summary="测试 Webhook 连通性", tags=["Webhook配置"], responses={200: "ApiResponse"})
@login_required
def test_webhook_config(config_id):
    """测试 Webhook 连通性（管理员）。

    发送一条测试消息到 Webhook URL，验证配置是否正确。
    """
    if not _require_admin():
        return APIResponse.error("权限不足", "FORBIDDEN", 403)

    config = webhook_config_service.get_config(config_id)
    if not config:
        return APIResponse.error("配置不存在", "NOT_FOUND", 404)

    try:
        validate_webhook_url(config.url)
    except ValueError as e:
        return APIResponse.success(data={"success": False, "message": str(e)})

    try:
        if config.channel == ChannelType.WECHAT_WORK:
            payload = {
                "msgtype": "text",
                "text": {"content": "[测试消息] Webhook 连通性测试 - 来自 IPIP 通知系统"},
            }
        elif config.channel == ChannelType.FEISHU:
            payload = {
                "msg_type": "text",
                "content": {"text": "[测试消息] Webhook 连通性测试 - 来自 IPIP 通知系统"},
            }
        else:
            payload = {"text": "[测试消息] Webhook 连通性测试 - 来自 IPIP 通知系统"}

        resp = requests.post(config.url, json=payload, timeout=10, allow_redirects=False)
        if resp.status_code == 200:
            return APIResponse.success(
                data={"success": True, "message": "Webhook 连通性测试成功", "response_code": resp.status_code}
            )
        else:
            return APIResponse.success(
                data={"success": False, "message": f"Webhook 返回非 200 状态码: {resp.status_code}", "response_code": resp.status_code}
            )
    except requests.RequestException as e:
        return APIResponse.success(
            data={"success": False, "message": f"Webhook 请求失败: {str(e)}"}
        )
