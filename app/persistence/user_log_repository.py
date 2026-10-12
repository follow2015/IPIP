# -*- coding: utf-8 -*-
"""
用户登录日志 Repository

提供 users_log 表的数据访问方法。
"""
from app.utils.logging import get_logger
from datetime import timedelta
from typing import Any, Dict, List, Optional
from app.utils.time_utils import now_utc_naive

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.models.user import User
from app.models.user_log import UserLog
from app.core.pagination_limits import ensure_offset_within_limit
from extensions import db

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
    """将认证类型规范化为 login_type（≤10字符）。

    Args:
        raw_type: auth_manager 返回的 auth_type 字符串

    Returns:
        str: 规范后的 login_type，最长 10 字符，默认 'web'
    """
    if not raw_type:
        return "web"
    mapped = _AUTH_TYPE_MAP.get(raw_type, raw_type)
    return mapped[:_LOGIN_TYPE_MAX_LEN]


class UserLogRepository:
    """用户登录日志 Repository

    职责单一：只负责 users_log 表的读写。
    """


    def create_log(
        self,
        user_id: int,
        login_ip: Optional[str] = None,
        login_type: Optional[str] = "web",
        user_agent: Optional[str] = None,
    ) -> Optional[UserLog]:
        """写入一条登录日志。

        使用 savepoint 隔离日志写入，确保：
        - 日志写入失败不影响主流程（fire-and-forget）
        - 即使在 @transactional 上下文内调用，也不会提前提交或回滚外层事务

        Args:
            user_id:    用户 ID
            login_ip:   客户端 IP
            login_type: 登录类型（已或未规范化均可）
            user_agent: 登录设备/浏览器 User-Agent

        Returns:
            Optional[UserLog]: 成功返回日志对象，失败返回 None
        """
        try:
            log = UserLog(
                user_id=user_id,
                login_ip=login_ip,
                login_type=_normalize_login_type(login_type),
                login_time=now_utc_naive(),
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
        """获取指定用户的最近登录日志（按时间降序）。"""
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
        """获取用户最近一次登录记录。"""
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
        """统计用户在最近 N 天内的登录次数。"""
        try:
            since = now_utc_naive() - timedelta(days=days)
            return (
                db.session.query(UserLog)
                .filter(UserLog.user_id == user_id, UserLog.login_time >= since)
                .count()
            )
        except SQLAlchemyError as e:
            logger.error(f"统计登录次数失败 (user_id={user_id}): {e}")
            return 0

    def get_recent_logs(self, days: int = 7, limit: int = 100) -> List[UserLog]:
        """获取全局最近 N 天的登录日志（安全审计用）。"""
        try:
            since = now_utc_naive() - timedelta(days=days)
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


    def login_ips_since(self, since) -> List[tuple]:
        """`since` 之后的 `(user_id, login_ip)` 列表（异地登录检测用）。

        只取 `login_ip` 非空的行：NULL/空串无法判定来源，让检测器去判反而会
        把"没记录 IP"当成"不可信来源"刷告警。
        """
        try:
            return (
                db.session.query(UserLog.user_id, UserLog.login_ip)
                .filter(UserLog.login_time >= since, UserLog.login_ip.isnot(None))
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"查询登录来源 IP 失败: {e}")
            return []

    def last_login_times_by_user(self) -> List[tuple]:
        """每个用户的最后登录时间 `(user_id, max_login_time)`（休眠账号检测用）。

        从未登录过的账号**不出现**在结果里 —— 那是"从未使用"，与"长期不用"
        是两回事，混在一起会让休眠名单里混进一批从没启用的账号。
        """
        try:
            return (
                db.session.query(UserLog.user_id, func.max(UserLog.login_time))
                .group_by(UserLog.user_id)
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"查询各用户最后登录时间失败: {e}")
            return []

    def remote_login_rows_since(self, since, limit: int = 5000) -> List[tuple]:
        """`since` 之后的 `(user_id, login_ip, login_time, username)`（异地登录面板用）。

        带上 `username` 是为了让前端一次拿全展示字段，避免按 user_id 逐条回查（N+1）。
        `login_ip` 为空的行**排除**：无法判定来源，混进来只会制造噪声。
        `limit` 是扫描上限护栏 —— 聚合在 Python 侧做，无上限时大表会把内存吃满。
        """
        try:
            return (
                db.session.query(UserLog.user_id, UserLog.login_ip, UserLog.login_time,
                                 User.username)
                .join(User, User.id == UserLog.user_id)
                .filter(UserLog.login_time >= since, UserLog.login_ip.isnot(None))
                .order_by(UserLog.login_time.desc())
                .limit(limit)
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"查询异地登录记录失败: {e}")
            return []

    def get_paginated_logs(
        self,
        user_id: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """分页查询登录日志，支持按用户和时间范围过滤。

        Args:
            user_id:    按用户ID过滤（None 则不过滤）
            start_time: 起始时间 ISO 格式（如 2026-04-01T00:00:00）
            end_time:   结束时间 ISO 格式
            page:       页码
            page_size:  每页数量

        Returns:
            Dict 包含 data / page / page_size / total_count / total_pages
        """
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
            ensure_offset_within_limit(offset)
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
