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
  S1 加固：Flask 提供 POST /api/sse/ticket 签发 60s 一次性票据，前端连接
  网关前先换票；`?token=` 回退路径保留但不推荐使用。

  P0#4 加固（审计 docs/ipip-full-audit-20260915.md）：
  - **类型白名单**：`?token=` 路径只接受 `type=access`。修复前任意类型都能
    建连——refresh 令牌（"记住我" 下有效期 30 天）可当长期凭据用；sse_ticket
    走 `?token=` 还能跳过 Redis SETNX 一次性消费，防重放保护整体失效。
  - **撤销查询**：与 Flask 侧 `cache_manager.is_token_revoked` 查同一个 Redis
    键。修复前 logout / 凭据泄漏处置对网关完全无效——令牌被撤销后事件流照旧
    推送，最长持续到令牌自然过期。
"""
import hashlib
import logging
import os

import jwt

from . import config
from . import redis_bus

logger = logging.getLogger(__name__)


DEFAULT_ALLOWED_TOKEN_TYPES: tuple = ("access",)

SSE_TICKET_TOKEN_TYPES: tuple = ("sse_ticket",)


CACHE_KEY_PREFIX_ENV = "CACHE_KEY_PREFIX"
CACHE_KEY_PREFIX_DEFAULT = "ipip:"          # 与 RedisCacheStorage 的默认值一致
_MD5_TOKEN_THRESHOLD = 50                   # 与 StandardCacheKeyGenerator 一致


def _revoked_cache_key(token: str) -> str:
    """复算 Flask 侧 ``cache_manager.revoke_token`` 写入的 Redis 键。

    网关是独立进程：直接 import ``app.utils.cache`` 会把 app 包（进而 Flask
    运行时）拖进网关的模块导入路径，因此这里按同一规则复算。推导链与 Flask
    侧逐字节一致，由 ``tests/test_p0_gateway_revocation_key_contract.py``
    以「Flask 侧真实实现」为期望值钉住 —— 若两侧漂移，撤销查询会静默变成
    「永远查不到」（有安全代码、无安全效果），比不修更危险。

    推导链：
      StandardCacheKeyGenerator.token_revoked_key →
        "token:revoked:" + (md5(token) if len(token) > 50 else token)
      RedisCacheStorage._make_key →
        f"{CACHE_KEY_PREFIX.rstrip(':')}:{key}"

    注意前缀取自**环境变量**（存储层的真实取值规则），不是
    ``config.CACHE_KEY_PREFIX`` —— 后者当前并不被存储层消费，两个来源可以
    不一致，故必须镜像存储层。
    """
    if len(token) > _MD5_TOKEN_THRESHOLD:
        token_part = hashlib.md5(token.encode("utf-8")).hexdigest()
    else:
        token_part = token

    key = f"token:revoked:{token_part}"
    prefix = (os.getenv(CACHE_KEY_PREFIX_ENV, CACHE_KEY_PREFIX_DEFAULT) or "").rstrip(":")
    return f"{prefix}:{key}" if prefix else key


async def is_token_revoked(token: str) -> bool:
    """令牌是否已被撤销（logout / 泄漏处置写入 Flask 侧撤销集合）。

    fail-closed：Redis 不可用时返回 True（判定为已撤销 → 拒绝建连）。
    与同文件 ``verify_sse_ticket`` 的 N1 修复同一条原则——网关的事件投递本就
    依赖 Redis，Redis 整体不可用时 SSE 已无意义，拒绝不会造成额外可用性损失；
    反之若放行，撤销保护在故障期间静默失效，且客户端只看到一条永不产出事件的
    流，故障对运维完全不可见。
    """
    try:
        r = await redis_bus.get_redis()
        return bool(await r.exists(_revoked_cache_key(token)))
    except Exception as exc:  # noqa: BLE001 - 任何 Redis 异常都按「已撤销」处理
        logger.error("令牌撤销查询失败，判定为已撤销（fail-closed）: %s", exc)
        return True


async def verify_token(
    token: str, allowed_types: tuple = DEFAULT_ALLOWED_TOKEN_TYPES
) -> dict | None:
    """校验 JWT token，返回 payload 或 None。

    与 Flask 侧 ``AuthenticationManager.verify_token``（签名 + 撤销集合）加上
    ``sse_login_required`` / ``login_required`` 的**类型白名单**对齐，即校验
    链路是：解码 → 类型白名单 → 撤销查询。

    Args:
        token: JWT 字符串
        allowed_types: 允许的 ``type`` claim 取值。默认只接受 access；
            一次性票据路径显式传 ``SSE_TICKET_TOKEN_TYPES``。

    拒绝顺序说明（与 Flask 侧的差异）：Flask 先查撤销再解码；网关刻意**先解码**
    ——网关是面向公网的回退入口，若先查 Redis，伪造/损坏令牌的洪泛会被放大成
    Redis EXISTS 洪泛。两条路径的拒绝结论完全一致，只是无谓往返被省掉。
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
    except jwt.ExpiredSignatureError:
        logger.debug("JWT 已过期")
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT 校验失败: %s", exc)
        return None

    if "user_id" not in payload:
        logger.warning("JWT payload 缺少 user_id 字段")
        return None

    token_type = payload.get("type")
    if token_type not in allowed_types:
        logger.warning(
            "JWT 类型不被接受: type=%s allowed=%s", token_type, tuple(allowed_types)
        )
        return None

    if await is_token_revoked(token):
        logger.warning(
            "JWT 已被撤销，拒绝建连: user_id=%s type=%s",
            payload.get("user_id"), token_type,
        )
        return None

    return payload


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
    payload = await verify_token(ticket, allowed_types=SSE_TICKET_TOKEN_TYPES)
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
