# -*- coding: utf-8 -*-
"""LDAP 目录身份落库（T3.5）：组→角色映射、角色同步、首次登录自动建号。

职责边界：
- 纯映射规则在 :mod:`app.services.ldap_role_mapper`（无 db / 无 ldap3，可穷举测试）；
- 本模块只负责把映射结果**落到本地账号**：查角色行、建号、改角色、失效缓存。

设计取舍：
1. **不做密码同步**（延续 T3 铁律）：自动建号时写入一个随机不可知口令的哈希，
   该账号只能走 LDAP 登录；口令列存在仅为满足 ``users.password NOT NULL``。
2. **角色管理默认关闭**：只有 ``LDAP_GROUP_ROLE_MAP`` 非空才算「角色由目录托管」。
   未配置映射时，LDAP 只负责认证，角色仍由管理员在本地维护 —— 这样开启 LDAP
   不会因为「映射没配」把存量账号的角色洗成空集（那等于全员锁死）。
3. **空角色集不清空**：``sync_user_roles`` 收到空集合时拒绝执行并告警。
   真要「收回全部角色」应由管理员显式操作，不能让一次目录查询异常顺手完成。
"""
from __future__ import annotations

import secrets
from typing import Any, Iterable, Sequence

from app.core.enums import UserStatus
from app.models.rbac import Role
from app.models.user import User
from app.persistence.rbac_repository import RoleRepository
from app.services.ldap_role_mapper import (
    GroupRoleMapError,
    parse_group_role_map,
    resolve_roles as _resolve_roles,
)
from app.utils.logging import get_logger
from app.utils.security.password import password_manager as default_password_manager

logger = get_logger(__name__)


class LdapIdentityError(Exception):
    """目录身份无法落到本地账号（配置错误 / 用户名超长 / 无可分配角色）。"""


class LdapIdentityService:
    """把一次成功的 LDAP Bind 结果映射成本地账号与会话。"""

    def __init__(
        self,
        *,
        role_repository: Any = None,
        session: Any = None,
        config_obj: Any = None,
        password_manager: Any = None,
    ) -> None:
        if config_obj is None:
            from config import get_config

            config_obj = get_config()
        self._config = config_obj
        self.session = session
        self.role_repository = role_repository if role_repository is not None else RoleRepository(session=session)
        self.password_manager = password_manager or default_password_manager
        self._group_map_cache: dict[str, str] | None = None

    def group_role_map(self) -> dict[str, str]:
        """组→角色映射（惰性解析并缓存；配置在进程启动时固定）。"""
        if self._group_map_cache is None:
            raw = getattr(self._config, "LDAP_GROUP_ROLE_MAP", "") or ""
            self._group_map_cache = parse_group_role_map(raw)
        return self._group_map_cache

    def default_role(self) -> str:
        return str(getattr(self._config, "LDAP_DEFAULT_ROLE", "") or "").strip()

    def role_management_enabled(self) -> bool:
        """角色是否由目录托管（``LDAP_GROUP_ROLE_MAP`` 非空即视为托管）。"""
        return bool(self.group_role_map())

    def auto_provision_enabled(self) -> bool:
        return bool(getattr(self._config, "LDAP_AUTO_PROVISION", False))

    def sync_roles_on_login(self) -> bool:
        return bool(getattr(self._config, "LDAP_SYNC_ROLES_ON_LOGIN", True))

    def resolve_roles(self, groups: Iterable[str]) -> list[str]:
        """按配置把 memberOf 组列表映射为角色名（可能为空列表）。"""
        return _resolve_roles(groups, self.group_role_map(), self.default_role())

    def get_role_objects(self, role_names: Sequence[str]) -> list[Role]:
        """把角色名解析为**存在且启用**的角色行；未知/已停用的名字告警后跳过。

        角色名来自配置，写错一个字母不应该变成「悄悄多授一个角色」，也不应该
        让登录整体失败 —— 故此处只告警跳过，最终是否放行由调用方按集合是否为空决定。
        """
        objects: list[Role] = []
        seen: set[str] = set()
        for name in role_names or ():
            key = str(name).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            try:
                role = self.role_repository.find_by_name(key)
            except Exception as exc:  # noqa: BLE001 - 查角色失败不阻断（按未命中处理）
                logger.error("查询角色失败: role=%s error=%s", key, exc)
                role = None
            if role is None:
                logger.warning("LDAP 组映射到不存在的角色，已跳过: role=%s", key)
                continue
            if getattr(role, "status", 0) != 0:
                logger.warning("LDAP 组映射到已停用的角色，已跳过: role=%s", key)
                continue
            objects.append(role)
        return objects

    def _db_session(self):
        if self.session is not None:
            return self.session
        from extensions import db

        return db.session

    def provision_user(
        self, *, username: str, dn: str = "", display_name: str = "",
        email: str = "", role_names: Sequence[str] = (),
    ) -> User:
        """首次登录自动建号（仅在 ``LDAP_AUTO_PROVISION`` 打开时被调用）。

        Raises:
            LdapIdentityError: 用户名非法/超长，或没有任何可分配角色。
        """
        username = (username or "").strip()
        if not username:
            raise LdapIdentityError("目录返回的用户名为空，无法建号")
        max_len = User.__table__.c.username.type.length or 20
        if len(username) > max_len:
            raise LdapIdentityError(
                f"目录用户名长度 {len(username)} 超过 users.username 上限 {max_len}，"
                "请调整 LDAP_USER_FILTER 或先手工建号"
            )

        roles = self.get_role_objects(role_names)
        if not roles:
            raise LdapIdentityError(
                f"账号 {username} 未映射到任何可用角色，拒绝自动建号"
                "（请检查 LDAP_GROUP_ROLE_MAP / LDAP_DEFAULT_ROLE）"
            )

        session = self._db_session()
        user = User(
            username=username,
            password=self.password_manager.hash_password(secrets.token_urlsafe(48)),
            name=(display_name or username)[:255],
            email=self._resolve_email(email, username),
            auth_source="ldap",
            external_dn=(dn or None),
            status=int(UserStatus.ACTIVE),
        )
        user.roles = list(roles)
        session.add(user)
        session.flush()
        logger.info(
            "LDAP 首次登录自动建号: username=%s roles=%s",
            username, [r.name for r in roles],
        )
        try:
            from app.services.switch_events import emit_resource_change_global

            emit_resource_change_global("user", "create", ids=[user.id])
        except Exception as exc:  # noqa: BLE001 - 事件通知失败不影响建号
            logger.warning("自动建号后发事件失败: %s", exc)
        return user

    def _resolve_email(self, email: str, username: str) -> str | None:
        """邮箱可用才写入：冲突或超长一律留空。

        邮箱只是通讯属性，**绝不能让邮箱冲突阻断企业账号登录**；用户后续可在
        管理界面自行补齐。
        """
        value = (email or "").strip()
        if not value:
            return None
        max_len = User.__table__.c.email.type.length or 255
        if len(value) > max_len:
            logger.warning("目录邮箱超长，忽略: username=%s", username)
            return None
        try:
            taken = (
                self._db_session().query(User)
                .filter(User.email == value, User.username != username)
                .first()
            )
        except Exception as exc:  # noqa: BLE001 - 查重失败时按「不确定」处理
            logger.warning("邮箱查重失败，忽略该邮箱: username=%s error=%s", username, exc)
            return None
        if taken is not None:
            logger.warning("目录邮箱已被其它账号占用，忽略: username=%s email=%s", username, value)
            return None
        return value

    def sync_user_roles(self, user: User, role_names: Sequence[str]) -> bool:
        """把本地账号的角色对齐到目录映射结果。

        Returns:
            bool: 是否发生了变更（False = 无需改动或被拒绝）。
        """
        desired_roles = self.get_role_objects(role_names)
        if not desired_roles:
            logger.warning(
                "角色同步被拒：目录映射结果为空，拒绝清空账号角色: username=%s",
                getattr(user, "username", "?"),
            )
            return False

        current_ids = {r.id for r in (user.roles or [])}
        desired_ids = {r.id for r in desired_roles}
        if current_ids == desired_ids:
            return False

        user.roles = list(desired_roles)
        self._invalidate_user_permissions(getattr(user, "id", None))
        logger.info(
            "LDAP 角色同步: username=%s %s -> %s",
            getattr(user, "username", "?"),
            sorted(current_ids), sorted(desired_ids),
        )
        return True

    @staticmethod
    def _invalidate_user_permissions(user_id: Any) -> None:
        if user_id is None:
            return
        try:
            from app.utils.cache import cache_manager

            cache_manager.invalidate_pattern(f"user_permissions:{user_id}:*")
            cache_manager.invalidate_pattern(f"user:{user_id}:*")
        except Exception as exc:  # noqa: BLE001 - 缓存失效失败不阻断登录
            logger.warning("角色同步后清理权限缓存失败: user_id=%s error=%s", user_id, exc)


__all__ = ["GroupRoleMapError", "LdapIdentityError", "LdapIdentityService"]
