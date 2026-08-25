# -*- coding: utf-8 -*-
"""
审计日志 Repository 实现

提供审计日志相关的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import Optional, List

from app.models.audit_log import AuditLog
from app.persistence.base import SQLAlchemyRepository

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
