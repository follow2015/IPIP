# -*- coding: utf-8 -*-
"""
审计中间件

自动拦截对关键资源的写操作（POST/PUT/DELETE/PATCH），
写入 audit_logs 表并触发分级通知。写入失败不阻塞业务请求。

路由级 severity 覆盖：
    在视图函数中设置 g._audit_severity = "critical" 可覆盖默认级别，
    用于标记批量删除、RBAC 变更等高风险操作。
"""
from flask import g, request

from app.utils.auth import get_current_user_id
from app.utils.logging import get_logger

logger = get_logger(__name__)

AUDITED_RESOURCES = {
    "/api/devices": "device",
    "/api/users": "user",
    "/api/switch": "switch",
    "/api/rbac": "rbac",
    "/api/webhook-configs": "webhook_config",
    "/api/settings/mail": "mail_setting",
}

METHOD_ACTION_MAP = {
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}


def _resolve_resource(path: str) -> str | None:
    for prefix, resource in AUDITED_RESOURCES.items():
        if path.startswith(prefix):
            return resource
    return None


def _extract_resource_id(path: str, resource: str) -> int | None:
    resource_prefix = None
    for prefix, res in AUDITED_RESOURCES.items():
        if res == resource:
            resource_prefix = prefix
            break

    if not resource_prefix:
        return None

    path_parts = [p for p in path.split("/") if p]
    prefix_parts = [p for p in resource_prefix.split("/") if p]

    prefix_len = len(prefix_parts)
    if len(path_parts) > prefix_len:
        candidate = path_parts[prefix_len]
        try:
            return int(candidate)
        except (ValueError, IndexError):
            pass

    return None


class AuditMiddleware:

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        logger.info("审计中间件已注册")

    def _before_request(self):
        method = request.method
        path = request.path

        if method not in METHOD_ACTION_MAP:
            return

        resource = _resolve_resource(path)
        if resource is None:
            return

        g._audit_needed = True
        g._audit_resource = resource
        g._audit_action = METHOD_ACTION_MAP[method]
        g._audit_resource_id = _extract_resource_id(path, resource)

    def _after_request(self, response):
        if not getattr(g, '_audit_needed', False):
            return response

        if response.status_code < 200 or response.status_code >= 300:
            if response.status_code != 403:
                return response

        try:
            from app.services.audit_service import AuditService
            audit_service = AuditService()

            resource_id = getattr(g, '_audit_resource_id', None)
            if resource_id is None and response.status_code in (200, 201):
                resource_id = self._extract_id_from_response(response)

            severity = getattr(g, '_audit_severity', 'info')

            audit_service.log_and_notify(
                user_id=get_current_user_id(),
                action=getattr(g, '_audit_action', 'unknown'),
                resource=getattr(g, '_audit_resource', 'unknown'),
                resource_id=resource_id,
                detail={
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                },
                ip_address=request.remote_addr,
                severity=severity,
            )
        except Exception:
            logger.warning("审计日志写入失败（已忽略）", exc_info=True)

        return response

    @staticmethod
    def _extract_id_from_response(response) -> int | None:
        try:
            data = response.get_json(silent=True)
            if not data or not isinstance(data, dict) or 'data' not in data:
                return None

            created = data['data']

            if isinstance(created, dict) and 'id' in created:
                return created['id']

            if isinstance(created, list) and len(created) > 0:
                first = created[0]
                if isinstance(first, dict) and 'id' in first:
                    return first['id']
        except Exception:
            pass

        return None
