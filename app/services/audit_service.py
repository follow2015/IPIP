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

    def __init__(self, audit_repo=None):
        self.audit_repo = audit_repo

    def _create_audit_session(self) -> Session:
        return Session(bind=db.engine, expire_on_commit=False)

    def log(self, user_id: Optional[int], action: str, resource: str,
            resource_id: Optional[int] = None, detail: Optional[Dict] = None,
            ip_address: Optional[str] = None) -> AuditLog:
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
                 page: int = 1, per_page: int = 20) -> dict:
        if self.audit_repo is None:
            from app.persistence.audit_log_repository import AuditLogRepository
            self.audit_repo = AuditLogRepository()
        filters = {}
        if user_id is not None:
            filters['user_id'] = user_id
        if action is not None:
            filters['action'] = action
        if resource is not None:
            filters['resource'] = resource
        if resource_id is not None:
            filters['resource_id'] = resource_id
        return self.audit_repo.paginate(page=page, page_size=per_page, filters=filters, order_by='-created_at')

    def log_and_notify(self, user_id: Optional[int], action: str, resource: str,
                       resource_id: Optional[int] = None, detail: Optional[Dict] = None,
                       ip_address: Optional[str] = None, severity: str = "info") -> AuditLog:
        audit_log = self.log(user_id, action, resource, resource_id, detail, ip_address)

        try:
            from app.services.ops_alert_bridge import bridge_audit_event
            bridge_audit_event(audit_log, severity)
        except Exception:
            logger.warning("审计通知触发失败（已忽略）", exc_info=True)

        return audit_log
