# -*- coding: utf-8 -*-
"""
JWT 校验模块

浏览器原生 EventSource API 不支持自定义请求头（无法带 Authorization: Bearer），
因此同时支持两种方式：
1. ?token=xxx URL 查询参数（SSE 专用，浏览器 EventSource 场景）
2. Authorization: Bearer xxx 请求头（非浏览器客户端或 fetch-event-source 场景）

JWT claims 与 Flask 主应用一致：payload 中包含 user_id 字段，
使用相同的 JWT_SECRET_KEY + HS256 算法签发和校验。

安全说明：
  长期 JWT 直接放 URL 有泄露风险（代理访问日志、Referer）。
  P1 加固方向：Flask 加 POST /api/notifications/sse-ticket 端点，
  签发几十秒有效期的一次性 ticket，前端连接网关前先换票。
  本次先用长期 JWT 跑通主流程。
"""
import logging

import jwt

from . import config

logger = logging.getLogger(__name__)


def verify_token(token: str) -> dict | None:
    if not config.JWT_SECRET_KEY:
        logger.error("JWT_SECRET_KEY 未配置，网关鉴权不可用")
        return None

    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM],
        )
        if "user_id" not in payload:
            logger.warning("JWT payload 缺少 user_id 字段")
            return None
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("JWT 已过期")
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT 校验失败: %s", exc)
        return None


def extract_token_from_request(scope: dict) -> str | None:
    query_string = scope.get("query_string", b"")
    if query_string:
        from urllib.parse import parse_qs
        params = parse_qs(query_string.decode())
        tokens = params.get("token")
        if tokens:
            return tokens[0]

    for header_name, header_value in scope.get("headers", []):
        if header_name == b"authorization":
            value = header_value.decode()
            parts = value.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1]

    return None
