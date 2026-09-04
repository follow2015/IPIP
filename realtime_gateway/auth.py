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
from . import redis_bus

logger = logging.getLogger(__name__)


def verify_token(token: str) -> dict | None:
    """校验 JWT token，返回 payload 或 None。

    与 Flask 侧 app/utils/auth.py 的 AuthenticationManager.verify_token 对齐：
    - 共享 JWT_SECRET_KEY 和 JWT_ALGORITHM
    - payload 中必须有 user_id 字段
    - 过期/无效 token 返回 None
    """
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
    """从 ASGI scope 中提取 token。

    优先从 URL 查询参数提取，其次从 Authorization 请求头提取。

    Args:
        scope: ASGI 连接 scope 字典

    Returns:
        token 字符串，或 None
    """
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


def extract_ticket(scope: dict) -> str | None:
    """从 ASGI scope 提取 ?ticket= 一次性票据（优先于 token）。

    Args:
        scope: ASGI 连接 scope 字典

    Returns:
        ticket 字符串，或 None
    """
    query_string = scope.get("query_string", b"")
    if query_string:
        from urllib.parse import parse_qs

        params = parse_qs(query_string.decode())
        tickets = params.get("ticket")
        if tickets:
            return tickets[0]
    return None


async def verify_sse_ticket(ticket: str) -> dict | None:
    """校验 SSE 一次性票据。

    与 verify_token 的区别：
    - 要求 payload.type == "sse_ticket"
    - 通过 Redis SETNX 强制一次性消费（防重放），键为 jti、TTL 取票据剩余有效期

    Redis 不可用时**拒绝**（fail-closed，N1 修复）：原实现降级放行，导致一次性
    消费与防重放保护失效——票据虽仍经 JWT 签名与 60s TTL 校验（故非鉴权绕过），
    但该 60s 窗口内同一票据可被重复用于建立多条 SSE 连接。安全默认值应为拒绝。

    权衡说明：网关依赖 Redis 投递 SSE 事件，Redis 完全宕机时 SSE 本已不可用，
    故拒绝不会造成额外可用性损失；若为瞬时抖动，客户端重新申请票据即可恢复。

    Args:
        ticket: JWT 票据字符串

    Returns:
        payload 字典，或 None（校验失败 / 已被消费 / Redis 不可用）
    """
    payload = verify_token(ticket)
    if not payload:
        return None

    if payload.get("type") != "sse_ticket":
        logger.warning("SSE ticket 类型非法: %s", payload.get("type"))
        return None

    jti = payload.get("jti")
    if not jti:
        logger.warning("SSE ticket 缺少 jti，拒绝（一次性消费/防重放保护不可用）")
        return None
    try:
        import time

        r = await redis_bus.get_redis()
        ttl = max(int(payload.get("exp", 0) - time.time()), 1)
        if await r.set(f"sse_ticket:{jti}", "1", nx=True, ex=ttl) is None:
            logger.warning("SSE ticket 已被消费（疑似重放）: jti=%s", jti)
            return None
    except Exception as exc:  # noqa: BLE001
        logger.error("SSE ticket 一次性校验失败（拒绝，fail-closed）: %s", exc)
        return None

    return payload
