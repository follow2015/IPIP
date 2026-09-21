# -*- coding: utf-8 -*-
"""
HTTP 层鉴权装饰器：login_required / permission_required / role_required 及 SSE 变体。

原 app/utils/auth.py 的装饰器部分，随认证服务一并迁出工具层（审计 P1-11）。

这些装饰器构造的是 **HTTP 响应**（401/403 JSON 或 SSE error 事件），因此 `APIResponse`
/ `ErrorCode` 的导入**刻意保持函数内懒加载**（与搬迁前逐字一致）：
  - 模块级导入会触发 `app/api/__init__.py`（它 eager 导入 13 个蓝图），
    使 `import app.services.auth` 顺带拉起整个 api 包，并可能与
    `app.api.auth -> app.utils.auth` 形成循环；
  - 这也是当前 `app/services/**` 唯一一处对 api 层的依赖，已登记进分层门禁
    `tests/test_architecture_layering.py` 的 R2 台账。真修法是把
    `ErrorCode` / `APIResponse` 下沉到 api 之外的层，属独立任务。
"""
from functools import wraps

from flask import g, request

from app.services.auth.authentication import auth_manager
from app.services.auth.permission import permission_manager

def login_required(f):
    """要求登录的装饰器

    支持Web和微信两种认证方式。
    仅接受 access token，拒绝 refresh token。

    使用方法:
        @login_required
        def my_view():
            pass
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.api.base import APIResponse, ErrorCode
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return APIResponse.error("缺少认证令牌", ErrorCode.AUTHENTICATION_ERROR, 401)

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return APIResponse.error("无效的认证令牌格式", ErrorCode.AUTHENTICATION_ERROR, 401)

        token = parts[1]

        payload = auth_manager.verify_token(token)
        if not payload:
            return APIResponse.error("无效或已过期的令牌", ErrorCode.AUTHENTICATION_ERROR, 401)

        if payload.get("type") != "access":
            return APIResponse.error("无效的令牌类型", ErrorCode.AUTHENTICATION_ERROR, 401)

        auth_type = payload.get("auth_type", "web")
        g.current_user = {
            "user_id": payload["user_id"],
            "roles": payload.get("roles", ["user"]),
            "auth_type": auth_type,
        }

        if auth_type == "wx":
            g.current_user["openid"] = payload.get("openid")
            g.current_user["user_identifier"] = payload.get("openid")
        else:
            g.current_user["username"] = payload.get("username")
            g.current_user["user_identifier"] = payload.get("username")

        return f(*args, **kwargs)

    return decorated_function


def _sse_error_response(message: str, status_code: int = 401):
    """SSE 鉴权失败专用响应：返回 SSE 错误事件而非 JSON。

    浏览器 EventSource 客户端 onmessage 会收到 type=error 事件，
    避免 JSON.parse 失败被吞（I3 修复）。
    """
    import json as _json
    from flask import Response
    event_data = _json.dumps({"type": "error", "message": message}, ensure_ascii=False)
    body = f"data: {event_data}\n\n"
    return Response(body, status=status_code, mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def sse_login_required(f):
    """SSE 端点专用认证装饰器

    EventSource API 不支持自定义 HTTP 头，因此同时支持：
    1. Authorization 请求头（常规方式）
    2. ?ticket=xxx URL 查询参数（一次性票据，SSE 专用方式）

    安全说明（S1 修复）：原实现回退到 ?token= 长期 access token，JWT 出现在 URL
    会被代理访问日志、浏览器历史、Referer 记录，泄露面远大于短期票据。
    现改为只接受 POST /api/sse/ticket 签发的一次性票据（TTL 默认 60s，
    网关侧经 Redis SETNX 强制一次性消费防重放）。前端三处 SSE 客户端
    （services/ai.ts、DeviceEventBus.ts、hooks/useSSEConnection.ts）
    均已改用 ?ticket=，无遗留 ?token= 调用方。

    鉴权失败时返回 SSE 错误事件（而非 JSON），便于前端 EventSource 客户端处理。

    使用方法:
        @sse_login_required
        def sse_view():
            pass
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
            else:
                return _sse_error_response("无效的认证令牌格式", 401)
        else:
            token = request.args.get("ticket")
            if not token:
                return _sse_error_response("缺少认证令牌", 401)

        payload = auth_manager.verify_token(token)
        if not payload:
            return _sse_error_response("无效或已过期的令牌", 401)

        if payload.get("type") not in ("access", "sse_ticket"):
            return _sse_error_response("无效的令牌类型", 401)

        auth_type = payload.get("auth_type", "web")
        g.current_user = {
            "user_id": payload["user_id"],
            "roles": payload.get("roles", ["user"]),
            "auth_type": auth_type,
        }

        if auth_type == "wx":
            g.current_user["openid"] = payload.get("openid")
            g.current_user["user_identifier"] = payload.get("openid")
        else:
            g.current_user["username"] = payload.get("username")
            g.current_user["user_identifier"] = payload.get("username")

        return f(*args, **kwargs)

    return decorated_function


def permission_required(*permissions):
    """要求特定权限的装饰器

    使用方法:
        @permission_required('room:create', 'room:update')
        def my_view():
            pass
    """

    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            from app.api.base import APIResponse, ErrorCode
            from app.persistence.user_repository import UserRepository

            user_id = g.current_user.get("user_id")
            user = UserRepository().find_by_id(user_id)

            if not user:
                return APIResponse.error("用户不存在", ErrorCode.AUTHENTICATION_ERROR, 401)

            if not permission_manager.check_user_permissions(
                user, list(permissions)
            ):
                return APIResponse.error("权限不足", ErrorCode.AUTHORIZATION_ERROR, 403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def sse_permission_required(*permissions):
    """SSE 端点专用权限装饰器。

    与 permission_required 的区别：
    - 内嵌 sse_login_required（支持 ?ticket=xxx 一次性票据查询参数），而非
      login_required（login_required 仅读 Authorization 头，浏览器 EventSource
      无法设置自定义头）。

      N2 修复：docstring 原写「支持 ?token=xxx 长期令牌」，与实际实现不符
      （sse_login_required 自 S1 修复后仅读 ?ticket=）。功能性正确，仅文档误导。
    - 鉴权失败时返回 SSE 错误事件而非 JSON，避免前端 EventSource 客户端 JSON.parse 失败被吞。

    使用方法:
        @sse_permission_required('ai:admin')
        def sse_view():
            pass
    """

    def decorator(f):
        @wraps(f)
        @sse_login_required
        def decorated_function(*args, **kwargs):
            from app.persistence.user_repository import UserRepository

            user_id = g.current_user.get("user_id")
            user = UserRepository().find_by_id(user_id)

            if not user:
                return _sse_error_response("用户不存在", 401)

            if not permission_manager.check_user_permissions(
                user, list(permissions)
            ):
                return _sse_error_response("权限不足", 403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def role_required(*roles):
    """要求特定角色的装饰器

    使用方法:
        @role_required('admin', 'operator')
        def my_view():
            pass
    """

    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            from app.api.base import APIResponse, ErrorCode
            from app.persistence.user_repository import UserRepository

            user_id = g.current_user.get("user_id")
            user = UserRepository().find_by_id(user_id)

            if not user:
                return APIResponse.error("用户不存在", ErrorCode.AUTHENTICATION_ERROR, 401)

            user_role_names = {role.name for role in user.roles}
            if not any(role_name in user_role_names for role_name in roles):
                return APIResponse.error("权限不足", ErrorCode.AUTHORIZATION_ERROR, 403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator

