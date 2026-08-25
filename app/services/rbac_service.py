# -*- coding: utf-8 -*-
"""RBAC 权限管理服务

业务逻辑层：所有数据访问经由 RoleRepository / PermissionRepository，
API 层不再直接使用 db.session 或 Model.query。
"""
from typing import Any, Dict, List, Optional

from app.exceptions.validation import ValidationError
from app.models.rbac import Role, Permission
from app.models.user import User
from app.persistence.rbac_repository import RoleRepository, PermissionRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)

_SYSTEM_ROLES = {"admin", "operator", "viewer", "user"}


def _invalidate_role_permission_cache(role_name: str):
    try:
        from app.utils.cache import cache_manager
        from app.utils.auth import PermissionManager
        normalized = PermissionManager._normalize_role(role_name)
        cache_manager.delete(f"role_permissions:{normalized}")
        cache_manager.invalidate_pattern(f"permission:{normalized}:*")
        cache_manager.invalidate_pattern(f"check_permissions:{normalized}:*")
        cache_manager.invalidate_pattern("user_permissions:*")
        logger.info("已清除角色 %s 的全部权限缓存", normalized)
    except Exception as e:
        logger.warning("清除角色权限缓存失败: %s", e)


class RbacService:

    def __init__(self, role_repository: RoleRepository, permission_repository: PermissionRepository):
        self.role_repository = role_repository
        self.permission_repository = permission_repository


    def list_roles(
        self, page: int = 1, per_page: int = 20,
        search: str = "", status: Optional[int] = None,
    ) -> Dict[str, Any]:
        pagination = self.role_repository.search_roles(
            search=search, status=status, page=page, per_page=per_page,
        )
        roles_data = []
        for role in pagination.items:
            role_dict = role.to_dict()
            role_dict["permission_count"] = len(role.permissions)
            role_dict["user_count"] = len(role.users)
            roles_data.append(role_dict)
        return {
            "data": roles_data,
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
        }

    def get_role(self, role_id: int) -> Optional[Role]:
        return self.role_repository.find_by_id_with_relations(role_id)

    def create_role(self, data: Dict[str, Any]) -> Role:
        name = data.get("name", "").strip()
        display_name = data.get("display_name", "").strip()

        if not name or not display_name:
            raise ValidationError("角色名称和显示名称不能为空")

        if self.role_repository.find_by_name(name):
            raise ValidationError("角色名称已存在")

        role = Role(
            name=name,
            display_name=display_name,
            description=data.get("description", ""),
            status=data.get("status", 0),
        )
        self.role_repository.session.add(role)
        logger.info("创建角色成功: %s", name)
        return role

    def update_role(self, role_id: int, data: Dict[str, Any]) -> Optional[Role]:
        role = self.role_repository.find_by_id(role_id)
        if not role:
            return None

        new_name = data.get("name", role.name).strip()
        if new_name != role.name:
            conflict = self.role_repository.find_by_name_exclude_id(new_name, role_id)
            if conflict:
                raise ValidationError("角色名称已存在")

        role.name = new_name
        role.display_name = data.get("display_name", role.display_name)
        role.description = data.get("description", role.description)
        role.status = data.get("status", role.status)

        _invalidate_role_permission_cache(role.name)
        logger.info("更新角色成功: %s", role.name)
        return role

    def delete_role(self, role_id: int) -> bool:
        role = self.role_repository.find_by_id(role_id)
        if not role:
            return False

        if role.name in _SYSTEM_ROLES:
            raise ValidationError("系统默认角色不能删除")

        if role.users:
            raise ValidationError("该角色下还有用户，无法删除")

        self.role_repository.session.delete(role)
        _invalidate_role_permission_cache(role.name)
        logger.info("删除角色成功: %s", role.name)
        return True

    def batch_delete_roles(self, ids: List[int]) -> Dict[str, Any]:
        deleted = 0
        failed = []

        for role_id in ids:
            role = self.role_repository.find_by_id(role_id)
            if not role:
                failed.append({"id": role_id, "reason": "角色不存在"})
                continue
            if role.name in _SYSTEM_ROLES:
                failed.append({"id": role_id, "reason": "系统默认角色不可删除"})
                continue
            if role.users:
                failed.append({"id": role_id, "reason": "角色下存在用户"})
                continue
            try:
                self.role_repository.session.begin_nested()
                role_name = role.name
                self.role_repository.session.delete(role)
                self.role_repository.session.flush()
                _invalidate_role_permission_cache(role_name)
                deleted += 1
            except Exception as e:
                self.role_repository.session.rollback()
                failed.append({"id": role_id, "reason": str(e)})

        logger.info("批量删除角色: 成功=%d, 失败=%d", deleted, len(failed))
        return {"deleted": deleted, "failed_count": len(failed), "failed": failed}


    def get_role_permissions(self, role_id: int) -> List[Dict[str, Any]]:
        role = self.role_repository.find_by_id(role_id)
        if not role:
            return []
        return [p.to_dict() for p in role.permissions]

    def update_role_permissions(
        self, role_id: int, permission_codes: List[str]
    ) -> Dict[str, Any]:
        role = self.role_repository.find_by_id(role_id)
        if not role:
            return None

        valid_perms = []
        invalid_codes = []
        for code in permission_codes:
            perm = self.permission_repository.find_by_code(code)
            if perm:
                valid_perms.append(perm)
            else:
                invalid_codes.append(code)
        if invalid_codes:
            raise ValidationError(
                f"以下权限编码不存在: {', '.join(invalid_codes)}"
            )

        role.permissions.clear()
        for perm in valid_perms:
            role.permissions.append(perm)

        _invalidate_role_permission_cache(role.name)
        logger.info("更新角色权限成功: %s", role.name)
        return {"permissions": [p.code for p in role.permissions]}


    def list_permissions(
        self, page: int = 1, per_page: int = 50,
        search: str = "", category: str = "",
    ) -> Dict[str, Any]:
        pagination = self.permission_repository.search_permissions(
            search=search, category=category, page=page, per_page=per_page,
        )
        return {
            "data": [p.to_dict() for p in pagination.items],
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
        }

    def list_permission_categories(self) -> List[str]:
        return self.permission_repository.find_distinct_categories()


    def get_user_roles(self, user_id: int) -> List[Dict[str, Any]]:
        user = self.role_repository.session.query(User).get(user_id)
        if not user:
            return []
        return [r.to_dict() for r in user.roles]

    def update_user_roles(
        self, user_id: int, role_ids: List[int]
    ) -> Dict[str, Any]:
        user = self.role_repository.session.query(User).get(user_id)
        if not user:
            return None

        valid_roles = []
        invalid_ids = []
        for rid in role_ids:
            role = self.role_repository.find_by_id(rid)
            if role:
                valid_roles.append(role)
            else:
                invalid_ids.append(rid)
        if invalid_ids:
            raise ValidationError(
                f"以下角色ID不存在: {', '.join(str(i) for i in invalid_ids)}"
            )

        user.roles.clear()
        for role in valid_roles:
            user.roles.append(role)

        for role in valid_roles:
            _invalidate_role_permission_cache(role.name)

        from app.utils.cache import cache_manager
        cache_manager.invalidate_pattern(f"user_permissions:{user_id}:*")

        logger.info("更新用户角色成功: user_id=%d", user_id)
        return {"roles": [r.to_dict() for r in user.roles]}


rbac_service = RbacService(RoleRepository(), PermissionRepository())
