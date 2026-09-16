# -*- coding: utf-8 -*-
"""
认证管理器：JWT 签发 / 校验 / 刷新轮换 / 撤销 / 登录（本地 + LDAP + 微信）。

原 app/utils/auth.py 主体，审计 P1-11 迁出工具层 —— 它承担完整的认证授权职责并反向
依赖 models/services，不是"工具"。此处仅做模块搬迁，逻辑零改动。

模块级 `config` / `cache_manager` / `password_manager` / `logger` 必须保持**进程内规范
单例**（测试通过 `monkeypatch.setattr(auth_mod.auth_manager, ...)` /
`setattr(auth_mod.config, ...)` 打补丁，各持一份会让补丁静默失效）。
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from flask import request

from app.utils.cache import cache_manager
from app.utils.logging import get_logger
from app.utils.security.password import password_manager
from config import get_config

logger = get_logger(__name__)
config = get_config()

class AuthenticationManager:
    """认证管理器

    提供用户认证、令牌生成和验证功能。
    """

    def __init__(self):
        """初始化认证管理器"""
        self.secret_key = config.JWT_SECRET_KEY
        self.algorithm = config.JWT_ALGORITHM
        self.access_token_expires = config.JWT_ACCESS_TOKEN_EXPIRES
        self.refresh_token_expires = config.JWT_REFRESH_TOKEN_EXPIRES
        self.password_manager = password_manager
        self._ldap_service_cache = None
        self._ldap_identity_cache = None

    def hash_password(self, password: str) -> str:
        """加密密码

        Args:
            password: 明文密码

        Returns:
            str: 加密后的密码
        """
        return self.password_manager.hash_password(password)

    def verify_password(self, password: str, hashed_password: str) -> bool:
        """验证密码

        Args:
            password: 明文密码
            hashed_password: 加密后的密码

        Returns:
            bool: 密码正确返回True
        """
        return self.password_manager.verify_password(password, hashed_password)

    def generate_token(
        self,
        user_id: int,
        username: str = None,
        roles: list = None,
        token_type: str = "access",
        auth_type: str = "web",
        openid: str = None,
        expires_delta: "timedelta" = None,
        device_fingerprint: str = None,
    ) -> str:
        """生成JWT令牌

        Args:
            user_id: 用户ID
            username: 用户名（微信登录时可为None）
            roles: 用户角色列表
            token_type: 令牌类型（access或refresh）
            auth_type: 认证类型（web=本地密码 / wx=微信 / ldap=企业目录透传）
            openid: 微信OpenID（微信登录时必需）
            expires_delta: 自定义有效期（秒），None 时按 token_type 取默认值
                          （access=1h / refresh=7d；"记住我"登录传 30d）
            device_fingerprint: 设备指纹（仅写入 refresh token 的 dfp claim）。
                              换浏览器/换设备后 UA 变化 → 指纹不匹配 → 刷新被拒

        Returns:
            str: JWT令牌
        """
        import uuid

        if expires_delta is None:
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

        if device_fingerprint and token_type == "refresh":
            payload["dfp"] = device_fingerprint

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

    def generate_sse_ticket(
        self,
        user_id: int,
        username: str = None,
        roles: list = None,
        auth_type: str = "web",
        openid: str = None,
        expires_delta: timedelta = None,
        device_id: int = None,
    ) -> str:
        """生成 SSE 一次性票据（短有效期、type=sse_ticket）。

        用于替代 SSE URL 中的长期 access token，避免凭据明文出现在代理访问日志 /
        浏览器历史 / Referer。票据不写入撤销缓存与 refresh set，依赖短 TTL +
        网关（realtime_gateway）一次性消费（Redis SETNX 防重放）。

        Args:
            device_id: s2——可选绑定设备。传入时写入 dev claim，网关
                /sse/switch/{id} 据此比对设备归属；不传则不绑定设备
                （仅可用于全局事件流，设备路由会被 403 拒绝）。
                注意：调用方须先完成设备数据域校验，本方法只做 claim 写入。
        """
        import uuid

        if expires_delta is None:
            expires_delta = timedelta(seconds=60)

        expires_at = datetime.now(timezone.utc) + expires_delta
        payload = {
            "user_id": user_id,
            "roles": roles or ["user"],
            "type": "sse_ticket",
            "auth_type": auth_type,
            "exp": expires_at,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
        }
        if auth_type == "wx":
            payload["openid"] = openid
            payload["user_identifier"] = openid
        else:
            payload["username"] = username
            payload["user_identifier"] = username

        if device_id is not None:
            payload["dev"] = int(device_id)

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        logger.info(
            "生成 SSE 票据 (user_id=%s, auth_type=%s)", user_id, auth_type
        )
        return token

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证JWT令牌

        验证流程（按顺序）：
        1. 检查令牌是否在撤销列表中
        2. 验证令牌签名
        3. 检查令牌是否过期

        被撤销的令牌会立即返回 None，不进行后续验证。

        Args:
            token: JWT令牌

        Returns:
            Optional[Dict]: 令牌payload，验证失败返回None
        """
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

    def refresh_token(
        self, refresh_token: str, device_fingerprint: str = None
    ) -> Optional[Dict[str, str]]:
        """刷新访问令牌（含重用检测与设备绑定）

        Args:
            refresh_token: 刷新令牌
            device_fingerprint: 调用方 User-Agent 派生的设备指纹。
                与签发时绑定的 dfp 不一致则拒绝（换浏览器/换设备须重新登录）

        Returns:
            Optional[Dict]: 包含新的访问令牌和刷新令牌，失败返回None
        """
        if cache_manager.is_token_revoked(refresh_token):
            self._handle_refresh_token_reuse(refresh_token)
            return None

        payload = self.verify_token(refresh_token)
        if not payload:
            return None

        if payload.get("type") != "refresh":
            logger.warning("令牌类型错误，期望refresh令牌")
            return None

        bound_dfp = payload.get("dfp")
        if bound_dfp and device_fingerprint is not None and bound_dfp != device_fingerprint:
            logger.warning(
                "refresh token 设备指纹不匹配，拒绝刷新（疑似跨设备盗用）: "
                "user_id=%s", payload.get("user_id"))
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
                token_type="access", auth_type=auth_type
            )
            new_refresh_token = self.generate_token(
                user_id, username=username, roles=roles,
                token_type="refresh", auth_type=auth_type,
                device_fingerprint=bound_dfp,
            )

        self.revoke_token(refresh_token)
        self._mark_refresh_token_rotated(payload)

        try:
            from app.services.switch_events import _get_redis
            r = _get_redis()
            if r:
                rkey = f"user_refresh_tokens:{user_id}"
                r.srem(rkey, refresh_token)
        except Exception:
            pass  # 非关键操作，失败不影响主流程

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token
        }

    def revoke_token(self, token: str) -> bool:
        """撤销令牌

        将令牌加入撤销列表，TTL 设置为令牌的剩余有效时间。
        如果令牌已过期，则不需要撤销（返回 True 表示操作成功）。

        Args:
            token: JWT令牌

        Returns:
            bool: 撤销成功返回True，失败返回False
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False},  # 不验证过期时间，因为我们需要处理已过期的令牌
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
        self, username: str, password: str, user_service,
        remember: bool = False, device_fingerprint: str = None
    ) -> Optional[Dict[str, Any]]:
        """认证用户（用户名密码方式）

        Args:
            username: 用户名
            password: 密码
            user_service: 用户服务实例
            remember: 「记住我」勾选——True 时刷新令牌有效期延长至
                      JWT_REFRESH_TOKEN_REMEMBER_EXPIRES（默认 30 天），
                      False 保持默认 7 天
            device_fingerprint: 调用方设备指纹，绑定到 refresh token
                      （刷新时校验，换浏览器/换设备须重新登录）

        Returns:
            Optional[Dict]: 认证成功返回用户信息和令牌，失败返回None
        """
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

            logger.info("用户认证成功: %s", username)
            return self._issue_login(
                user, auth_type="web", remember=remember,
                device_fingerprint=device_fingerprint,
            )
        except Exception as e:
            logger.error("用户认证失败: %s", e, exc_info=True)
            return None

    def _issue_login(
        self, user, *, auth_type: str = "web",
        remember: bool = False, device_fingerprint: str = None,
    ) -> Dict[str, Any]:
        """为用户签发登录令牌并组装登录响应 —— 本系统唯一的令牌签发出口。

        本地密码（web）与 LDAP（ldap）两条认证路径共用此出口，保证 refresh 有效期、
        设备指纹绑定、响应结构三者在两条路径上完全一致（避免「LDAP 登录少了设备绑定」
        这类只在一条路径上出现的缺口）。
        """
        user_roles = [role.name for role in user.roles]

        access_token = self.generate_token(
            user.id,
            username=user.username,
            roles=user_roles,
            token_type="access",
            auth_type=auth_type,
        )
        refresh_token = self.generate_token(
            user.id,
            username=user.username,
            roles=user_roles,
            token_type="refresh",
            auth_type=auth_type,
            expires_delta=(
                timedelta(seconds=getattr(
                    config, "JWT_REFRESH_TOKEN_REMEMBER_EXPIRES",
                    self.refresh_token_expires))
                if remember else None
            ),
            device_fingerprint=device_fingerprint,
        )

        return {
            "user": user.to_dict(),
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": self.access_token_expires,
            "auth_type": auth_type,
        }

    AUTH_ROUTE_LOCAL = "local"
    AUTH_ROUTE_LDAP = "ldap"

    def get_ldap_service(self):
        """惰性构造并缓存 LDAP 认证服务。

        未启用 LDAP 的部署不会 import ldap3（惰性 import 在服务内部），因此不增加
        存量部署的启动负担；实例无共享可变状态，可跨线程复用。
        """
        svc = getattr(self, "_ldap_service_cache", None)
        if svc is None:
            from app.services.ldap_auth_service import LdapAuthService

            svc = LdapAuthService.from_config(config)
            self._ldap_service_cache = svc
        return svc

    def get_ldap_identity_service(self):
        """惰性构造并缓存目录身份落库服务（T3.5）。"""
        svc = getattr(self, "_ldap_identity_cache", None)
        if svc is None:
            from app.services.ldap_identity_service import LdapIdentityService

            svc = LdapIdentityService()
            self._ldap_identity_cache = svc
        return svc

    def ldap_bypass_users(self) -> frozenset:
        """应急本地通道白名单（``LDAP_BYPASS_USERS``，逗号分隔，大小写不敏感）。"""
        raw = getattr(config, "LDAP_BYPASS_USERS", "") or ""
        return frozenset(
            part.strip().lower() for part in str(raw).split(",") if part.strip()
        )

    def is_ldap_bypass_user(self, username) -> bool:
        """该用户名是否在应急本地通道白名单内。"""
        name = str(username or "").strip().lower()
        return bool(name) and name in self.ldap_bypass_users()

    def resolve_auth_route(self, user, ldap_service=None, username=None) -> str:
        """决定一次登录走本地密码还是 LDAP —— 认证路由的唯一决策点。

        规则（顺序即优先级）：
        0. 用户名在 ``LDAP_BYPASS_USERS`` 应急白名单内 → 恒走本地密码（T3.6）。
           这一条必须排在最前：域控整体不可用时，白名单账号是唯一能进系统的口子。
        1. 账号显式 ``auth_source='ldap'`` → 恒走 LDAP。**即便 LDAP 未启用或域控
           不可达也绝不回落本地密码**：回落等于把「关掉域控即可用本地口令登录」变成
           一条降级通路（WBS 关键约束 1：不可降级）。
        2. 账号 ``auth_source='local'``（含存量行与全部本地账号）→ 本地密码。
        3. 本地查无此账号 → LDAP 已启用则交给目录判定（目录会给出 user_not_found）；
           否则回到本地路径（执行 dummy hash，保持「用户不存在」的响应时序）。
        """
        name = username if username is not None else getattr(user, "username", None)
        if self.is_ldap_bypass_user(name):
            return self.AUTH_ROUTE_LOCAL
        source = getattr(user, "auth_source", None) or "local"
        if source == "ldap":
            return self.AUTH_ROUTE_LDAP
        if user is not None:
            return self.AUTH_ROUTE_LOCAL
        svc = ldap_service if ldap_service is not None else self.get_ldap_service()
        return self.AUTH_ROUTE_LDAP if getattr(svc, "enabled", False) else self.AUTH_ROUTE_LOCAL

    def authenticate_user(
        self, username: str, password: str, user_service,
        remember: bool = False, device_fingerprint: str = None,
    ) -> Optional[Dict[str, Any]]:
        """统一登录入口（T3.4）：按账号 ``auth_source`` 路由到本地密码或 LDAP。

        对外语义与 ``authenticate_password`` 完全一致（成功返回同结构 dict，失败
        ``None``），上层路由无须感知两条认证路径的差异。故障域差异只体现在日志里。
        """
        try:
            user = user_service.get_by_username(username)
        except Exception as e:
            logger.error("登录前查询用户失败: %s", e, exc_info=True)
            return None

        bypass = self.is_ldap_bypass_user(username)
        route = self.resolve_auth_route(user, username=username)

        if route == self.AUTH_ROUTE_LDAP:
            result, reason = self._authenticate_ldap(
                username, password, user,
                remember=remember, device_fingerprint=device_fingerprint,
            )
        else:
            result = self.authenticate_password(
                username, password, user_service,
                remember=remember, device_fingerprint=device_fingerprint,
            )
            reason = "ok" if result is not None else "local_credentials_rejected"

        self._audit_login(
            username, user,
            auth_type=("ldap" if route == self.AUTH_ROUTE_LDAP else "web"),
            success=result is not None, reason=reason, bypass=bypass,
        )
        return result

    def _audit_login(
        self, username: str, user, *, auth_type: str, success: bool,
        reason: str = "", bypass: bool = False,
    ) -> None:
        """登录审计（T3.7）—— 本系统唯一的登录留痕入口。

        设计要点：
        - **只在企业身份集成启用时记录**：LDAP 关闭的存量部署登录行为完全不变
          （不新增写入、不改变性能特征）；开启后 LDAP 与本地两条路径都记，便于
          回答「这次登录到底走了哪条路」。
        - 一次登录**只产生一条记录**：应急通道用独立 action 覆盖，不再重复记一条
          auth.login（否则事后统计登录次数会翻倍）。
        - 失败原因只写 `detail.reason`（如 invalid_credentials/unreachable），
          终端用户看到的仍是统一话术（防账号枚举）。
        - 审计写失败**绝不影响登录结论**，但会留显眼错误日志，避免"以为有留痕其实没有"。
        """
        try:
            if not getattr(self.get_ldap_service(), "enabled", False):
                return

            from app.services.audit_service import AuditService

            ip_address = None
            try:
                from flask import has_request_context, request

                if has_request_context():
                    ip_address = request.remote_addr
            except Exception:  # noqa: BLE001 - 无请求上下文时正常记 None
                ip_address = None

            if bypass:
                action = "auth.ldap_bypass"
            else:
                action = "auth.login" if success else "auth.login.failed"

            user_id = getattr(user, "id", None)
            detail = {
                "username": username,
                "auth_type": auth_type,
                "result": "success" if success else "failure",
                "reason": reason or ("ok" if success else "unknown"),
                "bypass": bool(bypass),
            }
            if bypass:
                detail["note"] = "账号在 LDAP_BYPASS_USERS 白名单内，走本地口令认证"

            AuditService().log(
                user_id=user_id,
                action=action,
                resource="user",
                resource_id=user_id,
                detail=detail,
                ip_address=ip_address,
            )
            log = logger.warning if bypass else logger.info
            log(
                "登录审计[%s]: username=%s auth_type=%s reason=%s ip=%s",
                action, username, auth_type, detail["reason"], ip_address,
            )
        except Exception as exc:  # noqa: BLE001 - 审计失败不影响登录结论
            logger.error(
                "登录审计写入失败: username=%s action=%s error=%s",
                username, "auth.ldap_bypass" if bypass else "auth.login", exc,
                exc_info=True,
            )

    def _authenticate_ldap(
        self, username: str, password: str, user,
        remember: bool = False, device_fingerprint: str = None,
    ) -> tuple:
        """LDAP 透传 Bind 认证，成功后按本地账号签发会话（T3.4 + T3.5）。

        Returns:
            tuple: ``(登录响应 dict | None, 失败原因码)``。原因码供审计记录
            （T3.7），取值即 T3.3 的 status 常量，或身份落库阶段的
            no_role_mapped / not_provisioned / local_disabled / identity_error。

        两条铁律：
        - **不回落**：除 ``ok`` 以外的任何结果（凭据错/不可达/账号禁用/配置不全）
          一律返回 ``None``，绝不改判本地密码。
        - **失败原因只进日志与审计**：对终端用户沿用统一的「用户名或密码错误」话术，
          避免「用户不存在 / 密码错」的差异被用来做账号枚举（统一话术在 API 层）。

        组→角色（T3.5）：仅当配置了 ``LDAP_GROUP_ROLE_MAP`` 时角色才由目录托管；
        未配置则角色仍由管理员在本地维护，登录不改动既有角色。
        """
        from app.services.ldap_identity_service import LdapIdentityError
        from app.services.ldap_auth_service import STATUS_OK

        result = self.get_ldap_service().authenticate(username, password)
        if result.status != STATUS_OK:
            logger.warning(
                "LDAP 认证失败: username=%s status=%s detail=%s",
                username, result.status, result.message,
            )
            return None, result.status

        try:
            identity = self.get_ldap_identity_service()
            roles: list[str] = []
            if identity.role_management_enabled():
                roles = identity.resolve_roles(result.groups)
                if not roles:
                    logger.warning(
                        "LDAP 账号未映射到任何角色，拒绝登录: username=%s groups=%s",
                        username, list(result.groups),
                    )
                    return None, "no_role_mapped"

            if user is None:
                if not identity.auto_provision_enabled():
                    logger.warning(
                        "LDAP 认证通过但本地无对应账号，自动建号未启用: username=%s dn=%s",
                        username, result.dn,
                    )
                    return None, "not_provisioned"
                user = identity.provision_user(
                    username=username, dn=result.dn or "",
                    display_name=result.display_name or "",
                    email=result.email or "", role_names=roles,
                )
            else:
                if not user.is_active:
                    logger.warning("LDAP 用户已在本地禁用: %s", username)
                    return None, "local_disabled"
                if roles and identity.sync_roles_on_login():
                    identity.sync_user_roles(user, roles)
        except LdapIdentityError as exc:
            logger.error("LDAP 身份落库失败，拒绝登录: username=%s error=%s", username, exc)
            return None, "identity_error"
        except Exception as exc:  # noqa: BLE001 - 配置/DB 异常一律 fail-close
            logger.error(
                "LDAP 身份落库异常，拒绝登录: username=%s error=%s",
                username, exc, exc_info=True,
            )
            return None, "identity_exception"

        logger.info("LDAP 认证成功: username=%s dn=%s", username, result.dn)
        return self._issue_login(
            user, auth_type="ldap", remember=remember,
            device_fingerprint=device_fingerprint,
        ), STATUS_OK

    def logout(self, token: str) -> bool:
        """用户登出 — 撤销当前令牌及该用户的所有刷新令牌

        即使 access_token 已过期，仍需撤销 refresh_token 以防被盗用。
        """
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
        """撤销指定用户的所有刷新令牌"""
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

    @staticmethod
    def compute_device_fingerprint(user_agent: str) -> str:
        """由 User-Agent 派生设备指纹（弱绑定）。

        换浏览器/换设备 → UA 变化 → 指纹变化 → refresh 被拒，须重新登录。
        同一浏览器升级小版本也会强制重登，属接受的权衡（安全优先）。
        """
        if not user_agent:
            return "ua-empty"
        return hashlib.sha256(user_agent.encode("utf-8")).hexdigest()[:16]

    def _mark_refresh_token_rotated(self, payload: dict) -> None:
        """轮换后为旧令牌 jti 写标记，TTL = 旧令牌剩余有效期。

        重用检测据此区分「已轮换令牌被重放（疑似盗用，触发全链撤销）」
        与「登出撤销后的令牌误用（仅拒绝）」。
        """
        try:
            jti = payload.get("jti")
            if not jti:
                return
            exp = payload.get("exp")
            ttl = int(exp - datetime.now(timezone.utc).timestamp()) if exp else 86400
            cache_manager.set(f"auth:refresh_rotated:{jti}", "1", ttl=max(ttl, 1))
        except Exception as e:
            logger.warning("写 refresh 轮换标记失败: %s", e)

    def _handle_refresh_token_reuse(self, token: str) -> None:
        """已撤销的 refresh token 再次出现的处理。

        带轮换标记 → 判定凭据泄漏（重放攻击）：撤销该用户全部刷新令牌并告警；
        无标记 → 登出/过期后的正常无效请求，仅记录不扩大撤销。
        """
        try:
            decoded = jwt.decode(
                token, self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False},
            )
        except jwt.InvalidTokenError:
            return  # 非本系统签发的令牌，无需处理

        user_id = decoded.get("user_id")
        jti = decoded.get("jti")
        rotated = bool(jti) and bool(
            cache_manager.exists(f"auth:refresh_rotated:{jti}"))
        if rotated and user_id:
            logger.warning(
                "检测到 refresh token 重用（疑似凭据泄漏），"
                "已撤销该用户全部刷新令牌: user_id=%s, jti=%s", user_id, jti)
            self._revoke_all_refresh_tokens(user_id)
        else:
            logger.info("已撤销的 refresh token 被再次使用: user_id=%s", user_id)

    def authenticate(
        self, username: str, password: str, user_service
    ) -> Optional[Dict[str, Any]]:
        """认证用户（用户名密码方式）— 委托给统一入口 authenticate_user

        Args:
            username: 用户名
            password: 密码
            user_service: 用户服务实例

        Returns:
            Optional[Dict]: 认证成功返回用户信息和令牌，失败返回None
        """
        return self.authenticate_user(username, password, user_service)

    def authenticate_wechat(
        self, openid: str, user_service
    ) -> Optional[Dict[str, Any]]:
        """认证用户（微信方式）

        Args:
            openid: 微信OpenID
            user_service: 用户服务实例

        Returns:
            Optional[Dict]: 认证成功返回用户信息和令牌，失败返回None
        """
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


auth_manager = AuthenticationManager()
