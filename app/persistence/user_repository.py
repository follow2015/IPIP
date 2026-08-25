# -*- coding: utf-8 -*-
"""
用户Repository实现

提供用户相关的数据访问方法。
"""
from app.utils.logging import get_logger
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.rbac import Role, UserRole
from app.persistence.base import SQLAlchemyRepository, QueryOptimizationMixin
from app.core.enums import UserStatus
from app.exceptions.data_access import QueryExecutionError, RecordNotFoundError
from app.utils.query_optimizer import monitor_query_performance

logger = get_logger(__name__)


class UserRepository(SQLAlchemyRepository, QueryOptimizationMixin):

    def __init__(self, session=None):
        super().__init__(User, session)


    def find_by_username(self, username: str) -> Optional[User]:
        try:
            return self.session.query(User).filter(User.username == username).first()
        except SQLAlchemyError as e:
            self.logger.error(f"根据用户名查找用户失败 (username={username}): {e}")
            raise QueryExecutionError("查找用户失败", original_error=e)

    def find_by_email(self, email: str) -> Optional[User]:
        try:
            return self.session.query(User).filter(User.email == email).first()
        except SQLAlchemyError as e:
            self.logger.error(f"根据邮箱查找用户失败 (email={email}): {e}")
            raise QueryExecutionError("查找用户失败", original_error=e)

    def find_by_openid(self, openid: str) -> Optional[User]:
        try:
            return self.session.query(User).filter(User.openid == openid).first()
        except SQLAlchemyError as e:
            self.logger.error(f"根据OpenID查找用户失败 (openid={openid}): {e}")
            raise QueryExecutionError("查找用户失败", original_error=e)


    def find_by_role(self, role_name: str, active_only: bool = True) -> List[User]:
        try:
            query = (
                self.session.query(User)
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .filter(Role.name == role_name)
            )
            if active_only:
                query = query.filter(User.status == UserStatus.ACTIVE)
            return query.all()
        except SQLAlchemyError as e:
            self.logger.error(f"根据角色查找用户失败 (role={role_name}): {e}")
            raise QueryExecutionError("查找用户失败", original_error=e)

    def find_admins(self) -> List[User]:
        return self.find_by_role("admin", active_only=True)

    def count_admins(self) -> int:
        try:
            return (
                self.session.query(func.count(User.id))
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .filter(Role.name == "admin", User.status == UserStatus.ACTIVE)
                .scalar()
            ) or 0
        except SQLAlchemyError as e:
            self.logger.error(f"统计管理员数量失败: {e}")
            raise QueryExecutionError("统计管理员数量失败", original_error=e)


    def check_username_exists(self, username: str, exclude_id: int = None) -> bool:
        try:
            query = self.session.query(User).filter(User.username == username)
            if exclude_id:
                query = query.filter(User.id != exclude_id)
            return self.session.query(query.exists()).scalar()
        except SQLAlchemyError as e:
            self.logger.error(f"检查用户名存在性失败 (username={username}): {e}")
            raise QueryExecutionError("检查用户名存在性失败", original_error=e)

    def check_email_exists(self, email: str, exclude_id: int = None) -> bool:
        if not email:
            return False
        try:
            query = self.session.query(User).filter(User.email == email)
            if exclude_id:
                query = query.filter(User.id != exclude_id)
            return self.session.query(query.exists()).scalar()
        except SQLAlchemyError as e:
            self.logger.error(f"检查邮箱存在性失败 (email={email}): {e}")
            raise QueryExecutionError("检查邮箱存在性失败", original_error=e)


    @monitor_query_performance
    def search_users(
        self,
        keyword: str = None,
        role: str = None,
        status: int = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        try:
            query = self.session.query(User).options(selectinload(User.roles))

            if keyword:
                query = query.filter(
                    or_(
                        User.username.ilike(f"%{keyword}%"),
                        User.email.ilike(f"%{keyword}%"),
                        User.name.ilike(f"%{keyword}%"),
                    )
                )

            if role:
                query = (
                    query
                    .join(UserRole, UserRole.user_id == User.id)
                    .join(Role, Role.id == UserRole.role_id)
                    .filter(Role.name == role)
                )

            if status is not None:
                query = query.filter(User.status == status)

            query = query.order_by(User.created_at.desc())

            count_query = query.statement.with_only_columns(func.count()).order_by(None)
            total_count = self.session.execute(count_query).scalar()

            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page = max(1, min(page, total_pages))
            offset = (page - 1) * page_size
            data = query.limit(page_size).offset(offset).all()

            return {
                "data": data,
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
                "keyword": keyword,
                "role": role,
                "status": status,
            }
        except SQLAlchemyError as e:
            self.logger.error(f"搜索用户失败: {e}")
            raise QueryExecutionError("搜索用户失败", original_error=e)

    def find_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        try:
            query = self.session.query(User).options(selectinload(User.roles))

            if filters:
                query = self._apply_filters(query, filters)

            total_count = query.count()
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page = max(1, min(page, total_pages))
            offset = (page - 1) * page_size
            data = query.limit(page_size).offset(offset).all()

            return {
                "data": data,
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            }
        except SQLAlchemyError as e:
            self.logger.error(f"分页查找用户失败: {e}")
            raise QueryExecutionError("分页查找用户失败", original_error=e)

    def get_all_users(self, active_only: bool = False) -> List[User]:
        try:
            query = self.session.query(User).options(selectinload(User.roles))
            if active_only:
                query = query.filter(User.status == UserStatus.ACTIVE)
            return query.order_by(User.created_at.desc()).all()
        except SQLAlchemyError as e:
            self.logger.error(f"获取所有用户失败: {e}")
            raise QueryExecutionError("获取所有用户失败", original_error=e)

    def find_active_users(self, limit: int = None) -> List[User]:
        try:
            query = self.session.query(User).filter(User.status == UserStatus.ACTIVE)
            if limit:
                query = query.limit(limit)
            return query.all()
        except SQLAlchemyError as e:
            self.logger.error(f"查找激活用户失败: {e}")
            raise QueryExecutionError("查找用户失败", original_error=e)

    def find_recent_users(self, days: int = 7, limit: int = 10) -> List[User]:
        try:
            since_date = datetime.now() - timedelta(days=days)
            return (
                self.session.query(User)
                .filter(User.created_at >= since_date)
                .order_by(User.created_at.desc())
                .limit(limit)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"查找最近注册用户失败: {e}")
            raise QueryExecutionError("查找最近注册用户失败", original_error=e)


    @monitor_query_performance
    def get_user_statistics(self) -> Dict[str, Any]:
        try:
            from sqlalchemy import case

            stats = self.session.query(
                func.count(User.id).label("total_users"),
                func.sum(case((User.status == UserStatus.ACTIVE, 1), else_=0)).label("active_users"),
                func.sum(case((User.status == UserStatus.INACTIVE, 1), else_=0)).label("inactive_users"),
            ).first()

            role_stats = (
                self.session.query(Role.name, func.count(User.id))
                .join(UserRole, UserRole.role_id == Role.id)
                .join(User, User.id == UserRole.user_id)
                .group_by(Role.name)
                .all()
            )
            role_statistics = {name: count for name, count in role_stats}

            return {
                "total_users": stats.total_users or 0,
                "active_users": stats.active_users or 0,
                "inactive_users": stats.inactive_users or 0,
                "role_statistics": role_statistics,
            }
        except SQLAlchemyError as e:
            self.logger.error(f"获取用户统计信息失败: {e}")
            raise QueryExecutionError("获取用户统计信息失败", original_error=e)


    def activate_user(self, user_id: int) -> Optional[User]:
        user = self.find_by_id(user_id)
        if not user:
            raise RecordNotFoundError("users", {"id": user_id})
        return self.update(user_id, {"status": 0})

    def deactivate_user(self, user_id: int) -> Optional[User]:
        user = self.find_by_id(user_id)
        if not user:
            raise RecordNotFoundError("users", {"id": user_id})
        return self.update(user_id, {"status": 1})

    def update_password(self, user_id: int, hashed_password: str) -> Optional[User]:
        user = self.find_by_id(user_id)
        if not user:
            raise RecordNotFoundError("users", {"id": user_id})
        return self.update(user_id, {"password": hashed_password}, allowed=["password"])

    def delete(self, user_id: int) -> bool:
        try:
            user = self.session.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            self.session.delete(user)
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            self.logger.error(f"删除用户失败 (user_id={user_id}): {e}")
            raise QueryExecutionError("删除用户失败", original_error=e)

    def count_other_admins(self, exclude_user_id: int) -> int:
        try:
            return (
                self.session.query(func.count(User.id))
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .filter(Role.name == "admin", User.status == UserStatus.ACTIVE, User.id != exclude_user_id)
                .scalar()
            ) or 0
        except SQLAlchemyError as e:
            self.logger.error(f"统计管理员数量失败: {e}")
            raise QueryExecutionError("统计管理员数量失败", original_error=e)
