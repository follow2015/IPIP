# -*- coding: utf-8 -*-
"""
审计日志 Repository 实现

提供审计日志相关的数据访问方法。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

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
        ts = now if now is not None else datetime.now(timezone.utc)
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
