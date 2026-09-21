# -*- coding: utf-8 -*-
"""
权限管理器：RBAC 角色/权限判定（角色继承、缓存、按用户聚合）。

原 app/utils/auth.py 的 PermissionManager，随认证服务一并迁出工具层（审计 P1-11）。
角色/权限数据的**唯一真源是 migrations/seed_rbac.py**；运行时判定直接查库
`role_permissions`，DB 异常 fail-close，不回落硬编码。

注意：模块级 `logger` 的**名字**随模块搬迁由 `app.utils.auth` 变为
`app.services.auth.permission`（下同，全包一致），仅影响日志记录里的 logger 字段。
"""
from typing import List

from app.utils.cache import cache_manager
from app.utils.logging import get_logger

from app.services.auth.context import RBAC_CACHE_TTL, _stable_hash

logger = get_logger(__name__)

class PermissionManager:
    """权限管理器

    提供基于角色的访问控制（RBAC）功能。
    """

    NUMERIC_ROLE_MAP = {
        "0": "admin",
        "1": "user",
        "2": "operator",
        "3": "viewer"
    }

    @classmethod
    def _normalize_role(cls, role: str) -> str:
        """标准化角色名称，处理数字角色"""
        if role in cls.NUMERIC_ROLE_MAP:
            return cls.NUMERIC_ROLE_MAP[role]
        return role

    @classmethod
    def has_permission(cls, role: str, permission: str) -> bool:
        """检查角色是否拥有指定权限（从数据库 role_permissions 表动态读取）

        Args:
            role: 用户角色名称
            permission: 权限标识

        Returns:
            bool: 拥有权限返回True
        """
        normalized_role = cls._normalize_role(role)

        cache_key = f"permission:{normalized_role}:{permission}"

        from app.utils.cache import cache_manager
        cached_result = cache_manager.get(cache_key)
        if cached_result is not None:
            return cached_result

        try:
            from app.persistence.rbac_repository import RoleRepository

            repo = RoleRepository()
            role_obj = repo.find_by_name(normalized_role)
            if not role_obj:
                result = False
            else:
                perm_codes = repo.list_permission_codes(role_obj.id)
                result = permission in set(perm_codes)
        except Exception as e:
            logger.critical("RBAC 权限查询异常，拒绝访问(fail-close): %s", e, exc_info=True)
            result = False

        cache_manager.set(cache_key, result, ttl=RBAC_CACHE_TTL)

        return result

    @classmethod
    def get_role_permissions(cls, role: str) -> List[str]:
        """获取角色的所有权限（从数据库 role_permissions 表动态读取）

        Args:
            role: 用户角色名称

        Returns:
            List[str]: 权限编码列表
        """
        normalized_role = cls._normalize_role(role)

        cache_key = f"role_permissions:{normalized_role}"

        from app.utils.cache import cache_manager
        cached_permissions = cache_manager.get(cache_key)
        if cached_permissions is not None:
            return cached_permissions

        try:
            from app.persistence.rbac_repository import RoleRepository

            repo = RoleRepository()
            role_obj = repo.find_by_name(normalized_role)
            if not role_obj:
                permissions = []
            else:
                permissions = repo.list_permission_codes(role_obj.id)
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
        """检查角色是否拥有所有必需权限

        Args:
            role: 用户角色
            required_permissions: 必需权限列表

        Returns:
            bool: 拥有所有权限返回True
        """
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
        """检查用户是否拥有所有必需权限（基于用户的所有角色）

        Args:
            user: 用户对象
            required_permissions: 必需权限列表

        Returns:
            bool: 拥有所有权限返回True
        """
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


permission_manager = PermissionManager()
