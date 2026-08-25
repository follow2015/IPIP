# -*- coding: utf-8 -*-
"""
用户服务模块

提供用户相关的业务逻辑。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional, Tuple

from app.models.user import User
from app.persistence.user_repository import UserRepository
from app.persistence.user_log_repository import UserLogRepository
from app.services.switch_events import emit_resource_change_global
from app.utils.cache import cache_manager, cached
from app.utils.security.password import password_manager
from app.exceptions.data_access import RecordNotFoundError
from app.exceptions.validation import ValidationError
from config import get_config

logger = get_logger(__name__)
config = get_config()


class UserService:

    def __init__(
        self,
        user_repository: UserRepository,
        user_log_repository: UserLogRepository,
    ):
        self.user_repository = user_repository
        self.user_log_repository = user_log_repository
        self.cache_ttl = config.CACHE_TTL_USER_SESSION


    def get_by_id(self, user_id: int) -> Optional[User]:
        return self.user_repository.find_by_id(user_id)

    def get_by_username(self, username: str) -> Optional[User]:
        return self.user_repository.find_by_username(username)

    def get_by_openid(self, openid: str) -> Optional[User]:
        return self.user_repository.find_by_openid(openid)

    def get_by_email(self, email: str) -> Optional[User]:
        return self.user_repository.find_by_email(email)

    def get_all_users(self, active_only: bool = False) -> List[User]:
        return self.user_repository.get_all_users(active_only=active_only)

    def get_paginated(
        self,
        page: int = 1,
        per_page: int = 20,
        filters: Dict[str, Any] = None,
    ) -> Tuple[List[User], int]:
        result = self.user_repository.find_paginated(
            page=page, page_size=per_page, filters=filters or {}
        )
        return result["data"], result["total_count"]

    def search_users(
        self,
        keyword: str = None,
        role: str = None,
        is_active: bool = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        status = None
        if is_active is not None:
            status = 0 if is_active else 1

        result = self.user_repository.search_users(
            keyword=keyword, role=role, status=status,
            page=page, page_size=page_size,
        )
        result["data"] = [u.to_dict(include_sensitive=False) for u in result["data"]]
        return result

    def check_username_exists(self, username: str, exclude_id: int = None) -> bool:
        return self.user_repository.check_username_exists(username, exclude_id)

    def check_email_exists(self, email: str, exclude_id: int = None) -> bool:
        return self.user_repository.check_email_exists(email, exclude_id)


    def create_user(self, data: Dict[str, Any]) -> User:
        if self.check_username_exists(data.get("username")):
            raise ValidationError(f"用户名 '{data.get('username')}' 已存在")

        if data.get("email") and self.check_email_exists(data.get("email")):
            raise ValidationError(f"邮箱 '{data.get('email')}' 已存在")

        password = data.get("password", "")
        from app.services.security_service import SecurityService
        is_valid, msg = SecurityService.validate_password(password)
        if not is_valid:
            raise ValidationError(msg)

        data = dict(data)
        data["password"] = password_manager.hash_password(password)

        user = self.user_repository.create(data)
        cache_manager.invalidate_pattern("user:*")
        emit_resource_change_global("user", "create", ids=[user.id])
        logger.info(f"创建用户成功: {user.username}")
        return user

    def update_user(self, user_id: int, data: Dict[str, Any]) -> Optional[User]:
        if "username" in data and self.check_username_exists(data["username"], exclude_id=user_id):
            raise ValidationError(f"用户名 '{data['username']}' 已存在")

        if "email" in data and data["email"] and self.check_email_exists(data["email"], exclude_id=user_id):
            raise ValidationError(f"邮箱 '{data['email']}' 已存在")

        if "password" in data:
            from app.services.security_service import SecurityService
            is_valid, msg = SecurityService.validate_password(data["password"])
            if not is_valid:
                raise ValidationError(msg)
            data = dict(data)
            data["password"] = password_manager.hash_password(data["password"])

        user = self.user_repository.update(user_id, data, allowed=list(User._UPDATABLE_FIELDS))
        cache_manager.invalidate_pattern(f"user:{user_id}:*")
        cache_manager.invalidate_pattern(f"user_permissions:{user_id}:*")
        cache_manager.invalidate_pattern("user:list:*")
        emit_resource_change_global("user", "update", ids=[user_id])
        logger.info(f"更新用户成功: user_id={user_id}")
        return user

    def delete_user(self, user_id: int, soft_delete: bool = True) -> bool:
        if soft_delete:
            user = self.user_repository.update(user_id, {"status": 1})
            result = user is not None
        else:
            result = self.user_repository.delete(user_id)

        if result:
            cache_manager.invalidate_pattern(f"user:{user_id}:*")
            cache_manager.invalidate_pattern("user:list:*")
            emit_resource_change_global("user", "delete", ids=[user_id])
            logger.info(f"删除用户成功: user_id={user_id}, soft_delete={soft_delete}")

        return result

    def activate_user(self, user_id: int) -> Optional[User]:
        return self.user_repository.activate_user(user_id)

    def deactivate_user(self, user_id: int) -> Optional[User]:
        return self.user_repository.deactivate_user(user_id)


    def update_last_login(
        self,
        user_id: int,
        ip: Optional[str] = None,
        login_type: Optional[str] = "web",
        user_agent: Optional[str] = None,
    ) -> bool:
        log = self.user_log_repository.create_log(
            user_id=user_id,
            login_ip=ip,
            login_type=login_type,
            user_agent=user_agent,
        )
        if log:
            logger.info(
                f"登录日志记录成功: user_id={user_id}, ip={ip}, type={log.login_type}"
            )
        else:
            logger.warning(f"登录日志写入失败: user_id={user_id}, ip={ip}")
        return log is not None

    def get_login_logs(
        self,
        user_id: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        result = self.user_log_repository.get_paginated_logs(
            user_id=user_id, start_time=start_time, end_time=end_time,
            page=page, page_size=page_size,
        )

        logs = result["data"]
        user_ids = {log.user_id for log in logs}
        if user_ids:
            users = self.user_repository.find_by_ids(list(user_ids))
            user_map = {u.id: u for u in users}
        else:
            user_map = {}

        result["data"] = []
        for log in logs:
            d = log.to_dict()
            u = user_map.get(log.user_id)
            d["username"] = u.username if u else None
            d["name"] = u.name if u else None
            result["data"].append(d)

        return result

    def get_last_login_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        log = self.user_log_repository.get_last_login(user_id)
        return log.to_dict() if log else None


    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        user = self.get_by_id(user_id)
        if not user:
            raise RecordNotFoundError("users", {"id": user_id})

        if not password_manager.verify_password(old_password, user.password):
            raise ValidationError("旧密码错误")

        from app.services.security_service import SecurityService
        is_valid, msg = SecurityService.validate_password(new_password)
        if not is_valid:
            raise ValidationError(msg)

        result = self.update_user(user_id, {"password": new_password})
        logger.info(f"修改密码成功: user_id={user_id}")
        return result is not None

    def reset_password(self, user_id: int, new_password: str) -> bool:
        from app.services.security_service import SecurityService
        is_valid, msg = SecurityService.validate_password(new_password)
        if not is_valid:
            raise ValidationError(msg)

        result = self.update_user(user_id, {"password": new_password})
        logger.info(f"重置密码成功: user_id={user_id}")
        return result is not None


    @cached(key_pattern="user:statistics")
    def get_user_statistics(self) -> Dict[str, Any]:
        return self.user_repository.get_user_statistics()


user_service = UserService(UserRepository(), UserLogRepository())
