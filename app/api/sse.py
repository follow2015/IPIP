# -*- coding: utf-8 -*-
"""
SSE 票据签发端点。

前端 EventSource 不支持自定义请求头，只能在 URL 携带凭据。
为避免长期 access token 明文进入代理访问日志 / 浏览器历史 / Referer，
改为：前端先以 access token（Authorization 头）调用本端点换取一个
短期（默认 60s）、一次性（single-use）的 SSE ticket，再将其作为 ?ticket= 传入 SSE URL。
网关 realtime_gateway 校验 ticket（共享 JWT_SECRET_KEY，无状态）并强制一次性消费。
"""
import logging
import os
from datetime import timedelta

from flask import Blueprint, g, request

from app.api.base import APIResponse, api_exception_handler
from app.utils import rate_limit_api
from app.utils.auth import auth_manager, login_required
from app.utils.logging import get_logger

logger = get_logger(__name__)

sse_bp = Blueprint("sse", __name__)

SSE_TICKET_TTL_SECONDS = int(os.environ.get("SSE_TICKET_TTL_SECONDS", "60"))


def _device_in_scope(user_id: int, device_id: int) -> bool:
    """判断设备是否落在用户数据域内（s2）。

    Returns:
        True 表示可访问；False 表示越权或校验不可用。

    注意：此处刻意 fail-closed。即便改为 fail-open 放行，签出的票据也不会带
    dev claim，网关设备路由依旧 403——可用性同样受损却额外打开了越权口子，
    故服务异常时直接拒绝签发，让故障显式暴露在换票阶段。
    """
    try:
        from app.services.monitoring.data_scope_service import get_visible_device_ids

        visible = get_visible_device_ids(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "SSE 票据数据域校验失败，拒绝签发 user_id=%s: %s", user_id, exc
        )
        return False

    if visible is None:  # data_scope=all 或超管：无限制
        return True
    return device_id in visible


@sse_bp.route("/ticket", methods=["POST"])
@rate_limit_api
@login_required
@api_exception_handler
def issue_sse_ticket():
    """签发 SSE 一次性票据。

    需已登录（Authorization: Bearer <access_token>）。
    返回的 ticket 有效期 SSE_TICKET_TTL_SECONDS 秒，且只能消费一次（网关侧强制）。

    s2：支持可选 ``?device_id=<id>``。传入时先按数据域校验该设备可见性，
    通过才把 ``dev`` claim 写入票据——网关 /sse/switch/{id} 比对 dev 与路径
    device_id，未绑定设备的票据无法订阅任何设备事件流（fail-closed）。
    """
    user = g.current_user

    device_id = request.args.get("device_id", type=int)
    if device_id is not None and not _device_in_scope(user["user_id"], device_id):
        logger.warning(
            "SSE 票据签发被拒：设备不在数据域内 user_id=%s device_id=%s",
            user["user_id"], device_id,
        )
        return APIResponse.error("无权访问该设备", status_code=403)

    ticket = auth_manager.generate_sse_ticket(
        user_id=user["user_id"],
        username=user.get("username"),
        roles=user.get("roles", ["user"]),
        auth_type=user.get("auth_type", "web"),
        openid=user.get("openid"),
        expires_delta=timedelta(seconds=SSE_TICKET_TTL_SECONDS),
        device_id=device_id,
    )
    return APIResponse.success(data={"ticket": ticket})
