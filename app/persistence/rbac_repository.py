# -*- coding: utf-8 -*-
"""RBAC 仓储

提供 Role / Permission 的数据访问方法。
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import distinct
from sqlalchemy.orm import selectinload

from app.models.rbac import Role, Permission, RolePermission, UserRole
from app.models.user import User
from app.persistence.base import BaseRepository


class RoleRepository(BaseRepository):
    """角色仓储"""

    def __init__(self, session=None):
        super().__init__(Role, session=session)

    def find_by_name(self, name: str) -> Optional[Role]:
        """按名称查找角色。"""
        return self._base_query().filter_by(name=name).first()

    def find_active_roles_by_user(self, user_id: int) -> List[Role]:
        """查询用户的所有启用角色（status == 0），供 data_scope_service 使用。"""
        return (
            self.session.query(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user_id, Role.status == 0)
            .all()
        )

    def find_user_ids_by_role_id(self, role_id: int) -> List[int]:
        """查询角色下的全部去重 user_id，供 escalation_service 使用。"""
        rows = (
            self.session.query(UserRole.user_id)
            .filter(UserRole.role_id == role_id)
            .distinct()
            .all()
        )
        return [r.user_id for r in rows]

    def find_by_name_exclude_id(self, name: str, exclude_id: int) -> Optional[Role]:
        """按名称查找角色，排除指定 ID。"""
        return self._base_query().filter(
            Role.name == name, Role.id != exclude_id
        ).first()

    def find_by_id_with_relations(self, role_id: int) -> Optional[Role]:
        """按 ID 查找角色，预加载权限和用户关系。"""
        return (
            self.session.query(Role)
            .options(selectinload(Role.permissions), selectinload(Role.users))
            .filter_by(id=role_id)
            .first()
        )

    def search_roles(
        self, search: str = "", status: Optional[int] = None,
        page: int = 1, per_page: int = 20,
    ) -> Dict[str, Any]:
        """搜索角色（支持关键词 + 状态过滤 + 分页）。"""
        query = self.session.query(Role).options(
            selectinload(Role.permissions), selectinload(Role.users)
        )
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                Role.name.ilike(pattern)
                | Role.display_name.ilike(pattern)
                | Role.description.ilike(pattern)
            )
        if status is not None:
            query = query.filter(Role.status == status)

        pagination = query.order_by(Role.id.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return pagination


class PermissionRepository(BaseRepository):
    """权限仓储"""

    def __init__(self, session=None):
        super().__init__(Permission, session=session)

    def find_by_code(self, code: str) -> Optional[Permission]:
        """按编码查找权限。"""
        return self._base_query().filter_by(code=code).first()

    def find_user_ids_by_permission_code(self, code: str) -> List[int]:
        """查询拥有指定权限编码的全部去重 user_id，供 data_scope_service 使用。"""
        perm = self.find_by_code(code)
        if not perm:
            return []
        rows = (
            self.session.query(UserRole.user_id)
            .join(RolePermission, RolePermission.role_id == UserRole.role_id)
            .filter(RolePermission.permission_id == perm.id)
            .distinct()
            .all()
        )
        return [r.user_id for r in rows]

    def find_distinct_categories(self) -> List[str]:
        """获取所有不重复的权限分类。"""
        rows = self.session.query(distinct(Permission.category)).all()
        return [c[0] for c in rows if c[0]]

    def search_permissions(
        self, search: str = "", category: str = "",
        page: int = 1, per_page: int = 50,
    ) -> Dict[str, Any]:
        """搜索权限（支持关键词 + 分类过滤 + 分页）。"""
        query = self._base_query()
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                Permission.code.ilike(pattern)
                | Permission.name.ilike(pattern)
                | Permission.description.ilike(pattern)
            )
        if category:
            query = query.filter(Permission.category == category)

        pagination = query.order_by(Permission.id.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return pagination
