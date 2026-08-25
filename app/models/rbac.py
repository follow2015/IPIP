# -*- coding: utf-8 -*-
"""
RBAC模型

定义基于角色的访问控制（RBAC）数据模型。
"""
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from extensions import db


class Role(BaseModel):
    """角色模型"""

    __tablename__ = "roles"
    __table_args__ = (
        Index("idx_role_name", "name"),
        Index("idx_role_status", "status"),
        UniqueConstraint("name", name="uk_role_name"),
        {"comment": "角色信息表"},
    )

    name = db.Column(db.String(50), nullable=False, comment="角色名称")
    display_name = db.Column(db.String(100), nullable=False, comment="角色显示名称")
    description = db.Column(db.Text, nullable=True, comment="角色描述")

    status = db.Column(db.Integer, default=0, nullable=False, comment="状态")

    data_scope = db.Column(
        db.String(16),
        nullable=False,
        server_default="all",
        comment="数据权限范围: all/responsible_person/room/custom",
    )
    data_scope_config = db.Column(
        db.JSON,
        nullable=True,
        comment="data_scope 配置: room 模式 {room_ids:[...]} | custom 模式 {device_ids:[...]}",
    )

    users = relationship(
        "User", secondary="user_roles", back_populates="roles"
    )
    permissions = relationship(
        "Permission", secondary="role_permissions", back_populates="roles"
    )

    def __repr__(self):
        return f"<Role {self.name}>"

    def to_dict(self, include_relations=False):
        """转换为字典

        Args:
            include_relations: 是否包含关联数据

        Returns:
            dict: 角色数据字典
        """
        data = super().to_dict()

        if include_relations:
            data["permissions"] = [
                permission.to_dict() for permission in self.permissions
            ]
            data["user_count"] = len(self.users)

        return data


class Permission(BaseModel):
    """权限模型"""

    __tablename__ = "permissions"
    __table_args__ = (
        Index("idx_permission_code", "code"),
        Index("idx_permission_category", "category"),
        UniqueConstraint("code", name="uk_permission_code"),
        {"comment": "权限信息表"},
    )

    code = db.Column(db.String(50), nullable=False, comment="权限编码")
    name = db.Column(db.String(100), nullable=False, comment="权限名称")
    category = db.Column(db.String(50), nullable=True, comment="权限分类")
    description = db.Column(db.Text, nullable=True, comment="权限描述")

    roles = relationship(
        "Role", secondary="role_permissions", back_populates="permissions"
    )

    def __repr__(self):
        return f"<Permission {self.code}>"

    def to_dict(self):
        """转换为字典

        Returns:
            dict: 权限数据字典
        """
        return super().to_dict()


class UserRole(BaseModel):
    """用户角色关联模型"""

    __tablename__ = "user_roles"
    __table_args__ = (
        Index("idx_user_role_user_id", "user_id"),
        Index("idx_user_role_role_id", "role_id"),
        UniqueConstraint("user_id", "role_id", name="uk_user_role"),
        {"comment": "用户角色关联表"},
    )

    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="用户ID"
    )
    role_id = db.Column(
        db.BigInteger,
        db.ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        comment="角色ID"
    )

    def __repr__(self):
        return f"<UserRole user_id={self.user_id}, role_id={self.role_id}>"


class RolePermission(BaseModel):
    """角色权限关联模型"""

    __tablename__ = "role_permissions"
    __table_args__ = (
        Index("idx_role_permission_role_id", "role_id"),
        Index("idx_role_permission_permission_id", "permission_id"),
        UniqueConstraint(
            "role_id", "permission_id",
            name="uk_role_permission"),
        {"comment": "角色权限关联表"},
    )

    role_id = db.Column(
        db.BigInteger,
        db.ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        comment="角色ID"
    )
    permission_id = db.Column(
        db.BigInteger,
        db.ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        comment="权限ID"
    )

    def __repr__(self):
        return f"<RolePermission role_id={self.role_id}, " \
               f"permission_id={self.permission_id}>"
