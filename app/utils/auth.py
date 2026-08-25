# -*- coding: utf-8 -*-
"""
认证和授权模块

提供用户认证、JWT令牌管理和权限检查功能。
"""
from app.utils.logging import get_logger
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Dict, List, Optional

import jwt
import hashlib
from flask import g, request

from app.utils.cache import cache_manager
from app.utils.security.password import password_manager
from config import get_config

logger = get_logger(__name__)
config = get_config()

RBAC_CACHE_TTL = 300


def _stable_hash(obj) -> str:
    return hashlib.sha256(repr(obj).encode("utf-8")).hexdigest()


def get_current_user_id() -> Optional[int]:
    current_user = getattr(g, 'current_user', None)
    if isinstance(current_user, dict):
        return current_user.get('user_id')
    return None


class AuthenticationManager:

    def __init__(self):
        self.secret_key = config.JWT_SECRET_KEY
        self.algorithm = config.JWT_ALGORITHM
        self.access_token_expires = config.JWT_ACCESS_TOKEN_EXPIRES
        self.refresh_token_expires = config.JWT_REFRESH_TOKEN_EXPIRES
        self.password_manager = password_manager

    def hash_password(self, password: str) -> str:
        return self.password_manager.hash_password(password)

    def verify_password(self, password: str, hashed_password: str) -> bool:
        return self.password_manager.verify_password(password, hashed_password)

    def generate_token(
        self,
        user_id: int,
        username: str = None,
        roles: list = None,
        token_type: str = "access",
        auth_type: str = "web",
        openid: str = None,
    ) -> str:
        import uuid

        if token_type == "refresh":
            expires_delta = timedelta(seconds=self.refresh_token_expires)
        else:
            expires_delta = timedelta(seconds=self.access_token_expires)

        expires_at = datetime.now(timezone.utc) + expires_delta

        payload = {
            "user_id": user_id,
            "roles": roles or ["user"],
            "type": token_type,
            "auth_type": auth_type,
            "exp": expires_at,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
        }

        if auth_type == "wx":
            if not openid:
                raise ValueError("微信登录必须提供openid")
            payload["openid"] = openid
            payload["user_identifier"] = openid
        else:
            if not username:
                raise ValueError("Web登录必须提供username")
            payload["username"] = username
            payload["user_identifier"] = username

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        if isinstance(token, bytes):
            token = token.decode("utf-8")

        cache_data = {
            "user_id": user_id,
            "roles": roles,
            "auth_type": auth_type
        }
        if auth_type == "wx":
            cache_data["openid"] = openid
        else:
            cache_data["username"] = username

        cache_manager.cache_token(
            token, cache_data,
            ttl=int(expires_delta.total_seconds())
        )

        if token_type == "refresh":
            try:
                from app.services.switch_events import _get_redis
                r = _get_redis()
                if r:
                    rkey = f"user_refresh_tokens:{user_id}"
                    r.sadd(rkey, token)
                    r.expire(rkey, int(expires_delta.total_seconds()))
            except Exception as e:
                logger.warning("记录 refresh token 失败: user_id=%d, error=%s", user_id, e)

        identifier = openid if auth_type == "wx" else username
        logger.info(
            f"生成{token_type}令牌 (user_id={user_id}, "
            f"auth_type={auth_type}, "
            f"identifier={identifier})")

        return token

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            if cache_manager.is_token_revoked(token):
                token_preview = token[:20] + "..." \
                    if len(token) > 20 else token
                logger.warning("令牌已被撤销: token=%s", token_preview)
                return None

            payload = jwt.decode(
                token, self.secret_key,
                algorithms=[self.algorithm]
            )

            return payload

        except jwt.ExpiredSignatureError:
            token_preview = token[:20] + "..." if len(token) > 20 else token
            logger.warning("令牌已过期: token=%s", token_preview)
            return None

        except jwt.InvalidTokenError as e:
            token_preview = token[:20] + "..." if len(token) > 20 else token
            logger.warning("无效的令牌: token=%s, error=%s", token_preview, str(e))
            return None

        except Exception as e:
            token_preview = token[:20] + "..." if len(token) > 20 else token
            logger.error(
                f"令牌验证失败: token={token_preview}, error={str(e)}",
                exc_info=True
            )
            return None

    def refresh_token(self, refresh_token: str) -> Optional[Dict[str, str]]:
        payload = self.verify_token(refresh_token)
        if not payload:
            return None

        if payload.get("type") != "refresh":
            logger.warning("令牌类型错误，期望refresh令牌")
            return None

        user_id = payload["user_id"]
        roles = payload.get("roles", ["user"])
        auth_type = payload.get("auth_type", "web")

        if auth_type == "wx":
            openid = payload.get("openid")
            if not openid:
                logger.warning("微信令牌缺少openid")
                return None

            new_access_token = self.generate_token(
                user_id, roles=roles,
                token_type="access", auth_type="wx",
                openid=openid
            )
            new_refresh_token = self.generate_token(
                user_id, roles=roles,
                token_type="refresh", auth_type="wx",
                openid=openid
            )
        else:
            username = payload.get("username")
            if not username:
                logger.warning("Web令牌缺少username")
                return None

            new_access_token = self.generate_token(
                user_id, username=username, roles=roles,
                token_type="access", auth_type="web"
            )
            new_refresh_token = self.generate_token(
                user_id, username=username, roles=roles,
                token_type="refresh", auth_type="web"
            )

        self.revoke_token(refresh_token)

        try:
            from app.services.switch_events import _get_redis
            r = _get_redis()
            if r:
                rkey = f"user_refresh_tokens:{user_id}"
                r.srem(rkey, refresh_token)
        except Exception:
            pass

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token
        }

    def revoke_token(self, token: str) -> bool:
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False},
            )

            user_id = payload.get("user_id")
            token_type = payload.get("type", "unknown")
            auth_type = payload.get("auth_type", "unknown")

            exp = payload.get("exp")
            if not exp:
                logger.warning(
                    f"令牌缺少过期时间: user_id={user_id}, type={token_type}"
                )
                return False

            exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
            now = datetime.now(timezone.utc)

            if exp_datetime <= now:
                logger.info(
                    f"令牌已过期，无需撤销: user_id={user_id}, "
                    f"type={token_type}, auth_type={auth_type}, "
                    f"expired_at={exp_datetime.isoformat()}"
                )
                return True

            ttl = int((exp_datetime - now).total_seconds())

            if ttl < 1:
                logger.info(
                    f"令牌即将过期，无需撤销: user_id={user_id}, "
                    f"type={token_type}, auth_type={auth_type}, ttl={ttl}s"
                )
                return True

            success = cache_manager.revoke_token(token, ttl=ttl)

            if success:
                logger.info(
                    f"令牌已撤销: user_id={user_id}, "
                    f"type={token_type}, auth_type={auth_type}, ttl={ttl}s"
                )
                return True
            else:
                logger.error(
                    f"撤销令牌失败（缓存操作失败）: user_id={user_id}, "
                    f"type={token_type}, auth_type={auth_type}"
                )
                return False

        except jwt.InvalidTokenError as e:
            logger.warning(
                f"无法撤销无效的令牌: {str(e)}"
            )
            return False
        except Exception as e:
            logger.error(
                f"撤销令牌时发生异常: {str(e)}",
                exc_info=True
            )
            return False

    def authenticate_password(
        self, username: str, password: str, user_service
    ) -> Optional[Dict[str, Any]]:
        try:
            user = user_service.get_by_username(username)
            if not user:
                self.verify_password(password, self.password_manager.DUMMY_HASH)
                logger.warning("用户不存在: %s", username)
                return None

            if not self.verify_password(password, user.password):
                logger.warning("密码错误: %s", username)
                return None

            if not user.is_active:
                logger.warning("用户已禁用: %s", username)
                return None

            user_roles = [role.name for role in user.roles]

            access_token = self.generate_token(
                user.id,
                username=user.username,
                roles=user_roles,
                token_type="access",
                auth_type="web",
            )
            refresh_token = self.generate_token(
                user.id,
                username=user.username,
                roles=user_roles,
                token_type="refresh",
                auth_type="web",
            )

            logger.info(
                f"用户认证成功: {username}"
            )

            return {
                "user": user.to_dict(),
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": self.access_token_expires,
                "auth_type": "web",
            }
        except Exception as e:
            logger.error("用户认证失败: %s", e, exc_info=True)
            return None

    def logout(self, token: str) -> bool:
        try:
            payload = self.verify_token(token)
            if payload:
                user_id = payload.get("user_id")
                self.revoke_token(token)
                self._revoke_all_refresh_tokens(user_id)
                auth_type = payload.get("auth_type", "web")
                logger.info("用户登出成功: user_id=%d, auth_type=%s", user_id, auth_type)
                return True

            try:
                decoded = jwt.decode(
                    token, self.secret_key,
                    algorithms=[self.algorithm],
                    options={"verify_exp": False},
                )
                user_id = decoded.get("user_id")
                if user_id:
                    self._revoke_all_refresh_tokens(user_id)
                    logger.info("过期 token 登出: user_id=%d，已撤销 refresh_token", user_id)
                    return True
            except jwt.InvalidTokenError:
                pass

            logger.warning("尝试登出无法解码的令牌")
            return False

        except Exception as e:
            logger.error("登出过程发生错误: %s", str(e))
            return False

    def _revoke_all_refresh_tokens(self, user_id: int) -> None:
        try:
            from app.services.switch_events import _get_redis
            r = _get_redis()
            if not r:
                return

            key = f"user_refresh_tokens:{user_id}"
            token_ids = r.smembers(key)
            for tid in token_ids:
                self.revoke_token(tid)
            r.delete(key)
        except Exception as e:
            logger.warning("撤销刷新令牌失败: user_id=%d, error=%s", user_id, e)

    def authenticate(
        self, username: str, password: str, user_service
    ) -> Optional[Dict[str, Any]]:
        return self.authenticate_password(username, password, user_service)

    def authenticate_wechat(
        self, openid: str, user_service
    ) -> Optional[Dict[str, Any]]:
        try:
            user = user_service.get_by_openid(openid)
            if not user:
                logger.warning("微信用户不存在: %s", openid)
                return None

            if not user.is_active:
                logger.warning("微信用户已禁用: %s", openid)
                return None

            user_roles = [role.name for role in user.roles]

            access_token = self.generate_token(
                user.id, roles=user_roles,
                token_type="access", auth_type="wx",
                openid=openid
            )
            refresh_token = self.generate_token(
                user.id, roles=user_roles,
                token_type="refresh", auth_type="wx",
                openid=openid
            )

            logger.info("微信用户认证成功: %s", openid)

            return {
                "user": user.to_dict(),
                "access_token": access_token,
                "refresh_token": refresh_token,
                "auth_type": "wx",
                "openid": openid,
            }
        except Exception as e:
            logger.error("微信用户认证失败: %s", e, exc_info=True)
            return None


class PermissionManager:

    ROLES = {
        "admin": "管理员",
        "operator": "操作员",
        "viewer": "查看者",
        "user": "普通用户"
    }

    NUMERIC_ROLE_MAP = {
        "0": "admin",
        "1": "user",
        "2": "operator",
        "3": "viewer"
    }

    PERMISSIONS = {
        "room:view": "查看机房",
        "room:create": "创建机房",
        "room:update": "更新机房",
        "room:delete": "删除机房",
        "cabinet:view": "查看机柜",
        "cabinet:create": "创建机柜",
        "cabinet:update": "更新机柜",
        "cabinet:delete": "删除机柜",
        "device:view": "查看设备",
        "device:create": "创建设备",
        "device:update": "更新设备",
        "device:delete": "删除设备",
        "customer:view": "查看客户",
        "customer:create": "创建客户",
        "customer:update": "更新客户",
        "customer:delete": "删除客户",
        "user:view": "查看用户",
        "user:create": "创建用户",
        "user:update": "更新用户",
        "user:delete": "删除用户",
        "user:permission": "管理用户权限",
        "user:role": "管理用户角色",
        "user:log": "管理用户登录日志",
        "network:view": "查看网络",
        "network:create": "创建网络",
        "network:update": "更新网络",
        "network:delete": "删除网络",
        "network:scan": "网络扫描",
        "switch:view": "查看交换机",
        "switch:create": "创建交换机",
        "switch:update": "更新交换机",
        "switch:delete": "删除交换机",
        "switch:config": "配置交换机",
        "ip:view": "查看IP",
        "ip:update": "更新IP",
        "ip:scan": "IP扫描",
        "system:config": "系统配置",
        "system:logs": "查看日志",
        "system:backup": "备份恢复",
        "system:scan": "系统扫描",
        "system:stats": "查看统计",
        "asset:view": "查看资产",
        "asset:create": "创建资产",
        "asset:update": "更新资产",
        "asset:delete": "删除资产",
        "monitor:view": "查看监控",
        "monitor:config": "配置监控",
        "monitor:alert": "管理告警",
        "monitor:report": "查看报表",
        "maintenance:view": "查看维护",
        "maintenance:create": "创建维护",
        "maintenance:update": "更新维护",
        "maintenance:delete": "删除维护",
        "security:read": "查看安全设置",
        "security:config": "配置安全设置",
        "security:session": "管理会话",
        "rbac:view": "查看角色权限",
        "rbac:create": "创建角色",
        "rbac:update": "更新角色",
        "rbac:delete": "删除角色",
        "audit:view": "查看审计日志",
        "import:view": "查看导入导出",
    }

    ROLE_PERMISSIONS = {
        "admin": [
            "room:view",
            "room:create",
            "room:update",
            "room:delete",
            "cabinet:view",
            "cabinet:create",
            "cabinet:update",
            "cabinet:delete",
            "device:view",
            "device:create",
            "device:update",
            "device:delete",
            "customer:view",
            "customer:create",
            "customer:update",
            "customer:delete",
            "user:view",
            "user:create",
            "user:update",
            "user:delete",
            "user:permission",
            "user:role",
            "user:log",
            "network:view",
            "network:create",
            "network:update",
            "network:delete",
            "network:scan",
            "switch:view",
            "switch:create",
            "switch:update",
            "switch:delete",
            "switch:config",
            "ip:view",
            "ip:update",
            "ip:scan",
            "system:config",
            "system:logs",
            "system:backup",
            "system:scan",
            "system:stats",
            "asset:view",
            "asset:create",
            "asset:update",
            "asset:delete",
            "monitor:view",
            "monitor:config",
            "monitor:alert",
            "monitor:report",
            "maintenance:view",
            "maintenance:create",
            "maintenance:update",
            "maintenance:delete",
            "security:read",
            "security:config",
            "security:session",
            "rbac:view",
            "rbac:create",
            "rbac:update",
            "rbac:delete",
            "audit:view",
            "import:view",
        ],
        "operator": [
            "room:view",
            "room:create",
            "room:update",
            "cabinet:view",
            "cabinet:create",
            "cabinet:update",
            "device:view",
            "device:create",
            "device:update",
            "customer:view",
            "customer:create",
            "customer:update",
            "user:view",
            "network:view",
            "network:create",
            "network:update",
            "network:scan",
            "switch:view",
            "switch:create",
            "switch:update",
            "switch:config",
            "ip:view",
            "ip:update",
            "ip:scan",
            "system:scan",
            "system:stats",
            "monitor:view",
            "monitor:config",
        ],
        "viewer": [
            "room:view",
            "cabinet:view",
            "device:view",
            "customer:view",
            "user:view",
            "network:view",
            "switch:view",
            "ip:view",
            "system:stats",
        ],
        "user": [
            "room:view",
            "cabinet:view",
            "device:view",
            "network:view",
            "switch:view",
            "ip:view",
            "system:stats",
        ],
    }

    @classmethod
    def _normalize_role(cls, role: str) -> str:
        if role in cls.NUMERIC_ROLE_MAP:
            return cls.NUMERIC_ROLE_MAP[role]
        return role

    @classmethod
    def has_permission(cls, role: str, permission: str) -> bool:
        normalized_role = cls._normalize_role(role)

        cache_key = f"permission:{normalized_role}:{permission}"

        from app.utils.cache import cache_manager
        cached_result = cache_manager.get(cache_key)
        if cached_result is not None:
            return cached_result

        try:
            from app.models.rbac import Role, Permission, RolePermission
            from extensions import db

            role_obj = Role.query.filter_by(name=normalized_role).first()
            if not role_obj:
                result = False
            else:
                perm_codes = (
                    db.session.query(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .filter(RolePermission.role_id == role_obj.id)
                    .all()
                )
                result = permission in {code for (code,) in perm_codes}
        except Exception as e:
            logger.critical("RBAC 权限查询异常，拒绝访问(fail-close): %s", e, exc_info=True)
            result = False

        cache_manager.set(cache_key, result, ttl=RBAC_CACHE_TTL)

        return result

    @classmethod
    def get_role_permissions(cls, role: str) -> List[str]:
        normalized_role = cls._normalize_role(role)

        cache_key = f"role_permissions:{normalized_role}"

        from app.utils.cache import cache_manager
        cached_permissions = cache_manager.get(cache_key)
        if cached_permissions is not None:
            return cached_permissions

        try:
            from app.models.rbac import Role, Permission, RolePermission
            from extensions import db

            role_obj = Role.query.filter_by(name=normalized_role).first()
            if not role_obj:
                permissions = []
            else:
                perm_codes = (
                    db.session.query(Permission.code)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .filter(RolePermission.role_id == role_obj.id)
                    .all()
                )
                permissions = [code for (code,) in perm_codes]
        except Exception as e:
            logger.critical("RBAC 角色权限查询异常，返回空权限(fail-close): %s", e, exc_info=True)
            permissions = []

        cache_manager.set(cache_key, permissions, ttl=RBAC_CACHE_TTL)

        return permissions

    @classmethod
    def check_permissions(
        cls, role: str,
        required_permissions: List[str]
    ) -> bool:
        normalized_role = cls._normalize_role(role)

        permissions_hash = _stable_hash(tuple(sorted(required_permissions)))
        cache_key = f"check_permissions:{normalized_role}:{permissions_hash}"

        from app.utils.cache import cache_manager
        cached_result = cache_manager.get(cache_key)
        if cached_result is not None:
            return cached_result

        role_permissions = cls.get_role_permissions(normalized_role)
        result = all(perm in role_permissions for perm in required_permissions)

        cache_manager.set(cache_key, result, ttl=RBAC_CACHE_TTL)

        return result

    @classmethod
    def check_user_permissions(
        cls, user,
        required_permissions: List[str]
    ) -> bool:
        user_id = user.id if hasattr(user, 'id') else \
            getattr(user, 'user_id', 0)
        sorted_perms = tuple(sorted(required_permissions))
        permissions_hash = _stable_hash(sorted_perms)
        cache_key = f"user_permissions:{user_id}:{permissions_hash}"

        from app.utils.cache import cache_manager
        cached_result = cache_manager.get(cache_key)
        if cached_result is not None:
            return cached_result

        result = True
        for permission in required_permissions:
            has_perm = False
            for role in user.roles:
                if cls.has_permission(role.name, permission):
                    has_perm = True
                    break
            if not has_perm:
                result = False
                break

        cache_manager.set(cache_key, result, ttl=RBAC_CACHE_TTL)

        return result


auth_manager = AuthenticationManager()
permission_manager = PermissionManager()


def login_required(f):

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


def sse_login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.api.base import APIResponse, ErrorCode
        auth_header = request.headers.get("Authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
            else:
                return APIResponse.error("无效的认证令牌格式", ErrorCode.AUTHENTICATION_ERROR, 401)
        else:
            token = request.args.get("token")
            if not token:
                return APIResponse.error("缺少认证令牌", ErrorCode.AUTHENTICATION_ERROR, 401)

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


def permission_required(*permissions):

    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            from app.api.base import APIResponse, ErrorCode
            from app.models.user import User

            user_id = g.current_user.get("user_id")
            user = User.query.get(user_id)

            if not user:
                return APIResponse.error("用户不存在", ErrorCode.AUTHENTICATION_ERROR, 401)

            if not permission_manager.check_user_permissions(
                user, list(permissions)
            ):
                return APIResponse.error("权限不足", ErrorCode.AUTHORIZATION_ERROR, 403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def role_required(*roles):

    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            from app.api.base import APIResponse, ErrorCode
            from app.models.user import User

            user_id = g.current_user.get("user_id")
            user = User.query.get(user_id)

            if not user:
                return APIResponse.error("用户不存在", ErrorCode.AUTHENTICATION_ERROR, 401)

            user_role_names = {role.name for role in user.roles}
            if not any(role_name in user_role_names for role_name in roles):
                return APIResponse.error("权限不足", ErrorCode.AUTHORIZATION_ERROR, 403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator
