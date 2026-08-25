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
    name = db.Column(db.String(255), nullable=False, comment="真实姓名")
    department = db.Column(db.String(100), nullable=True, comment="所属部门")
    contact_phone = db.Column(db.String(20), nullable=True, comment="联系电话")

    roles = relationship(
        "Role", secondary="user_roles", back_populates="users"
    )

    notification_prefs = db.Column(db.JSON, nullable=True, comment="通知偏好设置")

    status = db.Column(db.Integer, default=0, nullable=False, comment="状态")

    @property
    def is_active(self):
        return self.status == UserStatus.ACTIVE

    @property
    def real_name(self):
        return self.name

    def __repr__(self):
        return f"<User {self.username}>"

    def to_dict(self, include_sensitive=False, exclude=None):
        data = super().to_dict(exclude=['password'])
        data["roles"] = [role.name for role in self.roles]
        data["is_active"] = self.is_active
        data["real_name"] = self.real_name


        if exclude:
            for field in exclude:
                data.pop(field, None)

        return data

    def is_admin(self) -> bool:
        return any(role.name == "admin" for role in self.roles)

    def can_access(self, permission: str) -> bool:
        from app.utils.auth import permission_manager

        for role in self.roles:
            if permission_manager.has_permission(role.name, permission):
                return True
        return False
