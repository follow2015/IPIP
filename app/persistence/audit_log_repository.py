# -*- coding: utf-8 -*-
"""
审计日志 Repository 实现

提供审计日志相关的数据访问方法。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
from app.utils.time_utils import now_utc_naive

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.data_access import QueryExecutionError
from app.models.audit_log import AuditLog
from app.persistence.base import SQLAlchemyRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AuditLogRepository(SQLAlchemyRepository):
    """审计日志 Repository

    提供审计日志相关的数据访问方法。
    """

    def __init__(self, session=None):
        super().__init__(AuditLog, session)

    def find_by_user(self, user_id: int) -> List[AuditLog]:
        """按操作人查询审计日志"""
        return self.find_all(filters={'user_id': user_id}, order_by='-created_at')

    def find_by_resource(self, resource: str, resource_id: Optional[int] = None) -> List[AuditLog]:
        """按资源类型查询审计日志"""
        filters = {'resource': resource}
        if resource_id is not None:
            filters['resource_id'] = resource_id
        return self.find_all(filters=filters, order_by='-created_at')

    def find_by_action(self, action: str) -> List[AuditLog]:
        """按操作类型查询审计日志"""
        return self.find_all(filters={'action': action}, order_by='-created_at')


    def oldest_created_at(self):
        """最早一条审计记录的 `created_at`（空表返回 `None`）—— 留存检查用。

        留存的判定是"最早记录是否早于 `now - retention_days`"：早于 = 覆盖足够。
        空表返回 None 而非"当前时间" —— 没有日志是"无从判定"，不是"留存不足"，
        让调用方按"不报"处理（清理/补齐归运维任务，安全中心只做提示）。
        """
        try:
            return self.session.query(func.min(AuditLog.created_at)).scalar()
        except SQLAlchemyError as e:
            self.logger.error(f"查询最早审计记录失败: {e}")
            raise QueryExecutionError("查询最早审计记录失败", original_error=e) from e

    def count_login_failures_since(self, since) -> List[tuple]:
        """`since` 之后按 `resource_id` 统计 `auth.login.failed` 次数。

        返回 `[(resource_id, count), ...]`；只统计 `resource_id` 非空的
        （匿名失败没有归属账号，报出来无法处置）。

        为什么读审计日志而不是 `users_log`：登录失败**不写** `users_log`
        （那张表只记成功登录），失败事件只落在审计里 —— 这是本检测项唯一的
        数据源，没有第二处可对照。
        """
        try:
            return (
                self.session.query(AuditLog.resource_id, func.count(AuditLog.id))
                .filter(
                    AuditLog.action == "auth.login.failed",
                    AuditLog.created_at >= since,
                    AuditLog.resource_id.isnot(None),
                )
                .group_by(AuditLog.resource_id)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error(f"统计登录失败次数失败: {e}")
            raise QueryExecutionError("统计登录失败次数失败", original_error=e) from e

    def find_recent_change(
        self,
        device_id: int,
        within_seconds: int = 300,
        now: Optional[datetime] = None,
    ) -> Optional[Dict]:
        """查找设备在时间窗内的最近一次配置变更。

        Args:
            device_id: 设备 ID（匹配 audit_logs.resource_id）。
            within_seconds: 回溯窗口秒数。
            now: 当前时间（测试注入）；None 取当前 UTC。

        Returns:
            ``{"at": datetime, "actor": int, "action": str}``；无变更返回 None。

        Note:
            ``audit_logs.created_at`` 是 naive DateTime（DB 写 UTC 值无 tz 标记），
            threshold 也用 naive UTC 比较，避免 aware vs naive 比较告警。
        """
        ts = now if now is not None else now_utc_naive()
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        threshold = ts - timedelta(seconds=within_seconds)
        row = (
            self.session.query(AuditLog)
            .filter(
                AuditLog.resource_id == device_id,
                AuditLog.resource.in_(("device", "switch")),
                AuditLog.created_at >= threshold,
            )
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        if row is None:
            return None
        return {"at": row.created_at, "actor": row.user_id, "action": row.action}
