# -*- coding: utf-8 -*-
"""
用户模型

定义用户数据模型。
"""
from sqlalchemy import Index
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from app.core.enums import UserStatus
from extensions import db


class User(BaseModel):
    """用户模型"""

    _UPDATABLE_FIELDS = frozenset([
        "username", "email", "name", "department", "contact_phone",
        "password", "status", "notification_prefs", "openid",
    ])

    __tablename__ = "users"
    __table_args__ = (
        Index("idx_user_email", "email"),
        Index("idx_user_openid", "openid"),
        Index("idx_user_status", "status"),
        Index("idx_user_created_at", "created_at"),
        {"comment": "用户信息表"},
    )

    username = db.Column(db.String(20), unique=True, nullable=False, comment="用户名")
    password = db.Column(db.String(255), nullable=False, comment="密码（加密）")
    email = db.Column(db.String(255), nullable=True, comment="邮箱")
    openid = db.Column(db.String(255), nullable=True, comment="微信OpenID")
    name = db.Column(db.String(255), nullable=False, comment="真实姓名")  # 改为必填
    department = db.Column(db.String(100), nullable=True, comment="所属部门")  # 新增
    contact_phone = db.Column(db.String(20), nullable=True, comment="联系电话")  # 新增

    roles = relationship(
        "Role", secondary="user_roles", back_populates="users"
    )

    notification_prefs = db.Column(db.JSON, nullable=True, comment="通知偏好设置")

    status = db.Column(db.Integer, default=0, nullable=False, comment="状态")

    @property
    def is_active(self):
        """是否激活（兼容属性）"""
        return self.status == UserStatus.ACTIVE

    @property
    def real_name(self):
        """真实姓名（兼容属性）"""
        return self.name

    def __repr__(self):
        return f"<User {self.username}>"

    def to_dict(self, include_sensitive=False, exclude=None):
        """转换为字典

        Args:
            include_sensitive: 是否包含敏感信息（密码等）
            exclude: 要排除的字段列表

        Returns:
            dict: 用户数据字典
        """
        data = super().to_dict(exclude=['password'])
        data["roles"] = [role.name for role in self.roles]
        data["is_active"] = self.is_active
        data["real_name"] = self.real_name


        if exclude:
            for field in exclude:
                data.pop(field, None)

        return data

    def is_admin(self) -> bool:
        """检查是否为管理员

        Returns:
            bool: 是管理员返回True
        """
        return any(role.name == "admin" for role in self.roles)

    def can_access(self, permission: str) -> bool:
        """检查是否拥有指定权限

        Args:
            permission: 权限标识

        Returns:
            bool: 拥有权限返回True
        """
        from app.utils.auth import permission_manager

        for role in self.roles:
            if permission_manager.has_permission(role.name, permission):
                return True
        return False
