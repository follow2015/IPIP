# -*- coding: utf-8 -*-
"""
用户登录日志 Repository

提供 users_log 表的数据访问方法。
"""
from app.utils.logging import get_logger
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError

from app.models.user_log import UserLog
from extensions import db
from flask import g

logger = get_logger(__name__)

_LOGIN_TYPE_MAX_LEN = 10

_AUTH_TYPE_MAP: Dict[str, str] = {
    "password": "web",
    "wechat":   "wechat",
    "api":      "api",
    "mobile":   "mobile",
    "token":    "token",
}


def _normalize_login_type(raw_type: Optional[str]) -> str:
    if not raw_type:
        return "web"
    mapped = _AUTH_TYPE_MAP.get(raw_type, raw_type)
    return mapped[:_LOGIN_TYPE_MAX_LEN]


class UserLogRepository:


    def create_log(
        self,
        user_id: int,
        login_ip: Optional[str] = None,
        login_type: Optional[str] = "web",
        user_agent: Optional[str] = None,
    ) -> Optional[UserLog]:
        try:
            log = UserLog(
                user_id=user_id,
                login_ip=login_ip,
                login_type=_normalize_login_type(login_type),
                login_time=datetime.now(),
                user_agent=user_agent,
            )
            with db.session.begin_nested():
                db.session.add(log)
                db.session.flush()
            logger.debug(
                f"登录日志写入成功: user_id={user_id}, "
                f"ip={login_ip}, type={log.login_type}"
            )
            return log
        except SQLAlchemyError as e:
            logger.error(f"登录日志写入失败 (user_id={user_id}): {e}")
            return None


    def get_logs_by_user(
        self,
        user_id: int,
        limit: int = 20,
    ) -> List[UserLog]:
        try:
            return (
                db.session.query(UserLog)
                .filter(UserLog.user_id == user_id)
                .order_by(UserLog.login_time.desc())
                .limit(limit)
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"查询用户登录日志失败 (user_id={user_id}): {e}")
            return []

    def get_last_login(self, user_id: int) -> Optional[UserLog]:
        try:
            return (
                db.session.query(UserLog)
                .filter(UserLog.user_id == user_id)
                .order_by(UserLog.login_time.desc())
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"查询最近登录失败 (user_id={user_id}): {e}")
            return None

    def get_login_count(self, user_id: int, days: int = 30) -> int:
        try:
            since = datetime.now() - timedelta(days=days)
            return (
                db.session.query(UserLog)
                .filter(UserLog.user_id == user_id, UserLog.login_time >= since)
                .count()
            )
        except SQLAlchemyError as e:
            logger.error(f"统计登录次数失败 (user_id={user_id}): {e}")
            return 0

    def get_recent_logs(self, days: int = 7, limit: int = 100) -> List[UserLog]:
        try:
            since = datetime.now() - timedelta(days=days)
            return (
                db.session.query(UserLog)
                .filter(UserLog.login_time >= since)
                .order_by(UserLog.login_time.desc())
                .limit(limit)
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"查询全局登录日志失败: {e}")
            return []

    def get_paginated_logs(
        self,
        user_id: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        try:
            query = db.session.query(UserLog)
            if user_id is not None:
                query = query.filter(UserLog.user_id == user_id)
            if start_time:
                query = query.filter(UserLog.login_time >= start_time)
            if end_time:
                query = query.filter(UserLog.login_time <= end_time)
            query = query.order_by(UserLog.login_time.desc())

            total_count = query.count()
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page        = max(1, min(page, total_pages))
            offset      = (page - 1) * page_size
            data        = query.limit(page_size).offset(offset).all()

            return {
                "data":        data,
                "page":        page,
                "page_size":   page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next":    page < total_pages,
                "has_prev":    page > 1,
            }
        except SQLAlchemyError as e:
            logger.error(f"分页查询登录日志失败: {e}")
            return {
                "data": [], "page": page, "page_size": page_size,
                "total_count": 0, "total_pages": 0,
                "has_next": False, "has_prev": False,
            }
