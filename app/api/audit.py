# -*- coding: utf-8 -*-
"""
审计日志 API

提供审计日志的 RESTful API 端点。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request
from marshmallow import Schema, fields, validate

from app.api.base import APIResponse
from app.services.audit_service import AuditService
from app.openapi.doc import doc, public
from app.utils import login_required, permission_required, rate_limit_api

logger = get_logger(__name__)

audit_bp = Blueprint("audit", __name__)

_audit_service = AuditService()




class AuditLogQuerySchema(Schema):
    """审计日志查询参数"""
    user_id = fields.Int(load_default=None)
    action = fields.Str(load_default=None)
    resource = fields.Str(load_default=None)
    resource_id = fields.Int(load_default=None)
    start_time = fields.Str(load_default=None, metadata={"description": "起始时间 ISO8601"})
    end_time = fields.Str(load_default=None, metadata={"description": "结束时间 ISO8601"})
    page = fields.Int(load_default=1, validate=validate.Range(min=1))
    per_page = fields.Int(load_default=20, validate=validate.Range(min=1, max=100))




@audit_bp.route("/logs", methods=["GET"])
@doc(summary="查询审计日志", tags=["审计"], responses={200: "AuditLogResponse", 401: "ApiError"})
@login_required
@permission_required("audit:view")
@rate_limit_api
def get_audit_logs():
    """查询审计日志

    Query Parameters:
        user_id (int): 操作人ID（可选）
        action (str): 操作类型（可选）
        resource (str): 资源类型（可选）
        resource_id (int): 资源ID（可选）
        page (int): 页码，默认 1
        per_page (int): 每页数量，默认 20，最大 100
    """
    schema = AuditLogQuerySchema()
    params = schema.load(request.args)

    page = params.pop('page', 1)
    per_page = params.pop('per_page', 20)

    result = _audit_service.get_logs(
        page=page, per_page=per_page,
        **{k: v for k, v in params.items() if v is not None}
    )
    return APIResponse.paginated(
        data=[log.to_dict() for log in result["data"]],
        page=result["page"],
        per_page=result["page_size"],
        total=result["total_count"],
        message="获取审计日志成功",
    )
