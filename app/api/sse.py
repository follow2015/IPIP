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

from flask import Blueprint, g

from app.api.base import APIResponse, api_exception_handler
from app.utils.auth import auth_manager, login_required

logger = logging.getLogger(__name__)

sse_bp = Blueprint("sse", __name__)

SSE_TICKET_TTL_SECONDS = int(os.environ.get("SSE_TICKET_TTL_SECONDS", "60"))


@sse_bp.route("/ticket", methods=["POST"])
@login_required
@api_exception_handler
def issue_sse_ticket():
    """签发 SSE 一次性票据。

    需已登录（Authorization: Bearer <access_token>）。
    返回的 ticket 有效期 SSE_TICKET_TTL_SECONDS 秒，且只能消费一次（网关侧强制）。
    """
    user = g.current_user
    ticket = auth_manager.generate_sse_ticket(
        user_id=user["user_id"],
        username=user.get("username"),
        roles=user.get("roles", ["user"]),
        auth_type=user.get("auth_type", "web"),
        openid=user.get("openid"),
        expires_delta=timedelta(seconds=SSE_TICKET_TTL_SECONDS),
    )
    return APIResponse.success(data={"ticket": ticket})
