# -*- coding: utf-8 -*-
"""
用户Repository实现

提供用户相关的数据访问方法。
"""
from app.utils.logging import get_logger
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from app.utils.time_utils import now_utc_naive

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.rbac import Role, UserRole
from app.persistence.base import SQLAlchemyRepository, QueryOptimizationMixin
from app.core.enums import UserStatus
from app.exceptions.data_access import QueryExecutionError, RecordNotFoundError
from app.core.pagination_limits import ensure_offset_within_limit
from app.utils.query_optimizer import monitor_query_performance

logger = get_logger(__name__)


class UserRepository(SQLAlchemyRepository, QueryOptimizationMixin):
    """用户Repository实现

    提供用户相关的数据访问方法，包括用户查询、创建、更新等操作。
    User 模型使用多对多角色关系（roles），所有角色过滤均通过 JOIN 实现。
    """

    def __init__(self, session=None):
        super().__init__(User, session)


    def find_by_username(self, username: str) -> Optional[User]:
        """根据用户名查找用户"""
        try:
            return self.session.query(User).filter(User.username == username).first()
        except SQLAlchemyError as e:
            self.logger.error(f"根据用户名查找用户失败 (username={username}): {e}")
            raise QueryExecutionError("查找用户失败", original_error=e)

    def find_by_email(self, email: str) -> Optional[User]:
        """根据邮箱查找用户"""
        try:
            return self.session.query(User).filter(User.email == email).first()
        except SQLAlchemyError as e:
            self.logger.error(f"根据邮箱查找用户失败 (email={email}): {e}")
            raise QueryExecutionError("查找用户失败", original_error=e)

    def find_email_conflict(self, email: str, username: str) -> Optional[User]:
        """查邮箱是否已被**其它账号**占用（排除同用户名的"自己"）。

        B-44 盲区收口：原调用点是 ``ldap_identity_service._resolve_email`` 里的
        ``self._db_session().query(User)`` —— 接收者为**调用表达式**，台账门禁的
        字符级匹配结构上看不见（盘点 §4 的最后 1 处）。收进本仓储后该读回到
        persistence 层，盲区**结构性消失**（而非被绕开）。

        ⚠️ **不要"简化"成 `check_email_exists`**：后者按 **id** 排除，本方法按
        **username** 排除。调用方在建号**之前**调用，新账号此时还没有 id，只能靠
        用户名排除自己（口径与原实现 ``User.username != username`` 一致）。
        ⚠️ ``users.email`` **无唯一约束** ⇒ 本查重是防重复邮箱的**唯一防线**
        （非锦上添花），去掉它两个 LDAP 账号可共享同一邮箱。

        返回冲突行（None = 无冲突）；DB 错照本仓储惯例抛 `QueryExecutionError`
        —— 调用方按"不确定"处理（邮箱留空但不阻断登录，**该口径留在调用方**）。
        """
        try:
            return (
                self.session.query(User)
                .filter(User.email == email, User.username != username)
                .first()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"查询邮箱冲突失败 (email={email}): {e}")
            raise QueryExecutionError("查询邮箱冲突失败", original_error=e)

    def find_by_openid(self, openid: str) -> Optional[User]:
        """根据微信OpenID查找用户"""
        try:
            return self.session.query(User).filter(User.openid == openid).first()
        except SQLAlchemyError as e:
            self.logger.error(f"根据OpenID查找用户失败 (openid={openid}): {e}")
            raise QueryExecutionError("查找用户失败", original_error=e)


    def find_by_role(self, role_name: str, active_only: bool = True) -> List[User]:
        """根据角色名称查找用户

        Args:
            role_name:   角色名称（Role.name）
            active_only: 是否只返回激活用户（status=0）

        Returns:
            List[User]
        """
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

    def exists_active_with_role(self, role_name: str) -> bool:
        """是否存在拥有该角色的**活跃**用户（B-44 收敛：告警兜底角色可用性判断）。

        与 `find_by_role` 的关系：同一条 join（User→UserRole→Role）与同一活跃口径
        （``status == UserStatus.ACTIVE``），但**只判存在**（``first() is not None``）
        —— 原调用点是"兜底角色有没有人能收告警"的热路径（带 5 分钟进程内缓存），
        拉整行没有必要。

        ⚠️ **刻意不包 `QueryExecutionError`**（与 `find_by_role` 不同）：原调用点
        不捕获 DB 异常、由上层告警流程决定处置，换仓储不得改变异常类型。
        """
        return (
            self.session.query(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .filter(Role.name == role_name, User.status == UserStatus.ACTIVE)
            .first()
            is not None
        )

    def get_by_id(self, user_id: int) -> Optional[User]:
        """按主键取用户（B-44 收敛：rbac 的用户-角色管理）。

        ``Session.get`` 与原 ``query(...).get()`` 同语义（主键直取、
        走 identity map）；User 无软删列，与``find_by_id``无口径分歧。
        """
        return self.session.get(User, user_id)

    def find_role_by_name_or_id(self, target_id) -> Optional[Role]:
        """按角色名取角色；名字未命中且 target_id 是数字时按 ID 回退。

        B-44 收敛（通知收件人解析）：`ops_alert_bridge` 传角色名（"admin"），
        `escalation_service` 传数字 role_id（前端 InputNumber）—— name=str(id)
        几乎必然查不到，会造成升级通知 0 收件人且静默不重试，故保留 name
        miss 后按 id 回退的两段语义（与原实现一致，勿"统一"成单一匹配）。
        """
        role = self.session.query(Role).filter_by(name=str(target_id)).first()
        if not role and str(target_id).isdigit():
            role = self.session.get(Role, int(target_id))
        return role

    def list_active_ids_for_role(self, role_id: int) -> List[int]:
        """取某角色下全部**活跃**用户的 ID（UserRole join User，B-44 收敛）。

        原实现是两次查询（UserRole 取 user_id 集合 → User 按 IN + ACTIVE 过滤），
        合并为一条 join —— 结果集等价（同角色、同活跃口径），少一次往返。
        """
        rows = (
            self.session.query(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .filter(UserRole.role_id == role_id, User.status == UserStatus.ACTIVE)
            .all()
        )
        return [r[0] for r in rows]

    def list_all_active_ids(self) -> List[int]:
        """取全部**活跃**用户 ID（B-44 收敛：broadcast 通知的全员投递）。"""
        rows = (
            self.session.query(User.id)
            .filter(User.status == UserStatus.ACTIVE)
            .all()
        )
        return [r[0] for r in rows]

    def find_admins(self) -> List[User]:
        """查找所有激活的管理员用户"""
        return self.find_by_role("admin", active_only=True)

    def find_first_active(self) -> Optional[User]:
        """取第一个激活用户（B-44 收敛；AI 诊断的"系统用户"占位）

        ⚠️ 过滤条件用 ``status == UserStatus.ACTIVE``，**不能**写
        ``User.is_active.is_(True)`` —— `is_active` 是模型上的 `@property`
        （不是 hybrid_property）：类上访问返回 property 对象，``.is_()`` 立即抛
        AttributeError（原实现因此恒返回 None、被外层 except 吞掉，见
        `tests/services/test_ai_system_user_resolution.py`）。
        """
        try:
            return (
                self.session.query(User)
                .filter(User.status == UserStatus.ACTIVE)
                .order_by(User.id.asc())
                .first()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"查找首个激活用户失败: {e}")
            raise QueryExecutionError("查找用户失败", original_error=e)

    def count_admins(self) -> int:
        """统计激活的管理员用户数量"""
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
        """检查用户名是否已存在"""
        try:
            query = self.session.query(User).filter(User.username == username)
            if exclude_id:
                query = query.filter(User.id != exclude_id)
            return self.session.query(query.exists()).scalar()
        except SQLAlchemyError as e:
            self.logger.error(f"检查用户名存在性失败 (username={username}): {e}")
            raise QueryExecutionError("检查用户名存在性失败", original_error=e)

    def check_email_exists(self, email: str, exclude_id: int = None) -> bool:
        """检查邮箱是否已存在"""
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
        """搜索用户（支持关键词、角色、状态过滤）

        Args:
            keyword:   匹配用户名、邮箱、真实姓名
            role:      角色名称过滤（Role.name），通过 JOIN 实现
            status:    状态过滤（0=激活, 1=停用）
            page:      页码
            page_size: 每页数量

        Returns:
            Dict 包含 data / page / page_size / total_count / total_pages 等
        """
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
            ensure_offset_within_limit(offset)
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
        """分页查找用户"""
        try:
            query = self.session.query(User).options(selectinload(User.roles))

            if filters:
                query = self._apply_filters(query, filters)

            total_count = query.count()
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page = max(1, min(page, total_pages))
            offset = (page - 1) * page_size
            ensure_offset_within_limit(offset)
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
        """获取所有用户"""
        try:
            query = self.session.query(User).options(selectinload(User.roles))
            if active_only:
                query = query.filter(User.status == UserStatus.ACTIVE)
            return query.order_by(User.created_at.desc()).all()
        except SQLAlchemyError as e:
            self.logger.error(f"获取所有用户失败: {e}")
            raise QueryExecutionError("获取所有用户失败", original_error=e)

    def find_active_users(self, limit: int = None) -> List[User]:
        """查找激活用户"""
        try:
            query = self.session.query(User).filter(User.status == UserStatus.ACTIVE)
            if limit:
                query = query.limit(limit)
            return query.all()
        except SQLAlchemyError as e:
            self.logger.error(f"查找激活用户失败: {e}")
            raise QueryExecutionError("查找用户失败", original_error=e)

    def find_recent_users(self, days: int = 7, limit: int = 10) -> List[User]:
        """查找最近注册的用户"""
        try:
            since_date = now_utc_naive() - timedelta(days=days)
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
        """获取用户统计信息

        角色统计通过 UserRole + Role JOIN 实现，不依赖不存在的 User.role 列。
        """
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
        """激活用户"""
        user = self.find_by_id(user_id)
        if not user:
            raise RecordNotFoundError("users", {"id": user_id})
        return self.update(user_id, {"status": 0})

    def deactivate_user(self, user_id: int) -> Optional[User]:
        """停用用户"""
        user = self.find_by_id(user_id)
        if not user:
            raise RecordNotFoundError("users", {"id": user_id})
        return self.update(user_id, {"status": 1})

    def update_password(self, user_id: int, hashed_password: str) -> Optional[User]:
        """更新用户密码"""
        user = self.find_by_id(user_id)
        if not user:
            raise RecordNotFoundError("users", {"id": user_id})
        return self.update(user_id, {"password": hashed_password}, allowed=["password"])

    def delete(self, user_id: int) -> bool:
        """硬删除用户

        Args:
            user_id: 用户ID

        Returns:
            bool: 成功返回True
        """
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
        """统计除指定用户外的管理员数量

        Args:
            exclude_user_id: 要排除的用户ID

        Returns:
            int: 其他管理员数量
        """
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
