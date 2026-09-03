# -*- coding: utf-8 -*-
"""
审计服务模块

提供审计日志的业务逻辑，通过独立 session 写入，与业务事务解耦。
审计写入使用绑定同一 engine 的独立 Session，写入后立即 commit + close，
确保业务回滚不影响审计留痕。
"""
from typing import Optional, Dict

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.utils.logging import get_logger
from extensions import db

logger = get_logger(__name__)


class AuditService:
    """审计服务

    操作审计日志入口，使用独立 session 写入审计记录。
    审计 session 与业务 db.session 完全解耦：
    - 业务事务回滚不影响审计留痕
    - 403/异常场景仍能记录审计日志
    """

    def __init__(self, audit_repo=None):
        """初始化审计服务

        Args:
            audit_repo: 审计日志 Repository（保留兼容，查询方法仍使用）
        """
        self.audit_repo = audit_repo

    def _create_audit_session(self) -> Session:
        """创建独立于业务事务的审计专用 session

        绑定同一 engine 但独立事务，写入即 commit，与业务事务解耦。
        """
        return Session(bind=db.engine, expire_on_commit=False)

    def log(self, user_id: Optional[int], action: str, resource: str,
            resource_id: Optional[int] = None, detail: Optional[Dict] = None,
            ip_address: Optional[str] = None) -> AuditLog:
        """记录审计日志（使用独立 session）

        Args:
            user_id: 操作人ID
            action: 操作类型
            resource: 资源类型
            resource_id: 资源ID
            detail: 操作详情
            ip_address: 操作IP

        Returns:
            AuditLog: 创建的审计日志记录
        """
        audit_session = self._create_audit_session()
        try:
            audit_log = AuditLog(
                user_id=user_id,
                action=action,
                resource=resource,
                resource_id=resource_id,
                detail=detail,
                ip_address=ip_address,
            )
            audit_session.add(audit_log)
            audit_session.commit()
            return audit_log
        except Exception:
            audit_session.rollback()
            logger.warning("审计日志写入失败（独立 session）", exc_info=True)
            raise
        finally:
            audit_session.close()

    def get_logs(self, user_id: Optional[int] = None, action: Optional[str] = None,
                 resource: Optional[str] = None, resource_id: Optional[int] = None,
                 start_time: Optional[str] = None, end_time: Optional[str] = None,
                 page: int = 1, per_page: int = 20) -> dict:
        """查询审计日志（分页）

        查询仍使用业务 db.session（只读，无需独立事务）。

        Args:
            user_id: 操作人ID（可选）
            action: 操作类型（可选）
            resource: 资源类型（可选）
            resource_id: 资源ID（可选）
            start_time: 起始时间 ISO8601（可选）
            end_time: 结束时间 ISO8601（可选）
            page: 页码
            per_page: 每页数量

        Returns:
            dict: 分页结果
        """
        if self.audit_repo is None:
            from app.persistence.audit_log_repository import AuditLogRepository
            self.audit_repo = AuditLogRepository()
        filters = {}
        if user_id is not None:
            filters['user_id'] = user_id
        if action is not None:
            if action.endswith('.'):
                filters['action'] = {'startswith': action}
            else:
                filters['action'] = action
        if resource is not None:
            filters['resource'] = resource
        if resource_id is not None:
            filters['resource_id'] = resource_id
        if start_time is not None:
            filters['created_at'] = {'gte': start_time}
        if end_time is not None:
            if 'created_at' in filters:
                filters['created_at']['lte'] = end_time
            else:
                filters['created_at'] = {'lte': end_time}
        return self.audit_repo.paginate(page=page, page_size=per_page, filters=filters, order_by='-created_at')

    def log_and_notify(self, user_id: Optional[int], action: str, resource: str,
                       resource_id: Optional[int] = None, detail: Optional[Dict] = None,
                       ip_address: Optional[str] = None, severity: str = "info") -> AuditLog:
        """记录审计日志并触发分级通知

        使用独立 session 写入审计记录，与业务事务完全解耦。
        业务回滚不影响审计留痕，403/异常场景仍能记录。

        Args:
            user_id: 操作人ID
            action: 操作类型
            resource: 资源类型
            resource_id: 资源ID
            detail: 操作详情
            ip_address: 操作IP
            severity: 严重程度 info/warning/critical，决定通知渠道

        Returns:
            AuditLog: 创建的审计日志记录
        """
        audit_log = self.log(user_id, action, resource, resource_id, detail, ip_address)

        try:
            from app.services.ops_alert_bridge import bridge_audit_event
            bridge_audit_event(audit_log, severity)
        except Exception:
            logger.warning("审计通知触发失败（已忽略）", exc_info=True)

        return audit_log
