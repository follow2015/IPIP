# -*- coding: utf-8 -*-
"""IP 审计 API

提供 IP 生命周期审计日志的查询端点：把 ip_allocation_logs（归属变更
allocate/release）与 ip_ban_records（封禁/解封 ban/unban）合并为一条审计流。

只记录**人工**操作产生的归属变更；封禁/解封由既有封禁流程写入
ip_ban_records，本模块只读不写。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request
from marshmallow import Schema, fields, validate

from app.api.base import APIResponse
from app.persistence.ip_audit_repository import IPAuditRepository
from app.services.ip_audit_service import IPAuditService
from app.openapi.doc import doc
from app.utils import login_required, permission_required, rate_limit_api

logger = get_logger(__name__)

ip_audit_bp = Blueprint("ip_audit", __name__)

_ip_audit_service = IPAuditService(IPAuditRepository())




class IPAuditLogQuerySchema(Schema):
    """IP 审计日志查询参数"""
    action = fields.Str(
        load_default=None,
        metadata={"description": "动作：allocate/release/ban/unban"},
    )
    ip_address = fields.Str(load_default=None, metadata={"description": "IP精确匹配"})
    room_id = fields.Int(load_default=None, metadata={"description": "机房ID"})
    operator_id = fields.Int(load_default=None, metadata={"description": "操作人ID"})
    start_time = fields.Str(load_default=None, metadata={"description": "起始时间 ISO8601"})
    end_time = fields.Str(load_default=None, metadata={"description": "结束时间 ISO8601"})
    page = fields.Int(load_default=1, validate=validate.Range(min=1))
    per_page = fields.Int(load_default=20, validate=validate.Range(min=1, max=100))




@ip_audit_bp.route("/logs", methods=["GET"])
@doc(summary="查询IP审计日志", tags=["IP"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@permission_required("ip:view")
@rate_limit_api
def get_ip_audit_logs():
    """查询IP审计日志（归属变更 + 封禁/解封合并）

    Query Parameters:
        action (str): 动作过滤，allocate/release/ban/unban（可选）
        ip_address (str): IP精确匹配（可选）
        room_id (int): 机房ID（可选）
        operator_id (int): 操作人ID（可选）
        start_time (str): 起始时间 ISO8601（可选）
        end_time (str): 结束时间 ISO8601（可选）
        page (int): 页码，默认 1
        per_page (int): 每页数量，默认 20，最大 100
    """
    schema = IPAuditLogQuerySchema()
    params = schema.load(request.args)

    page = params.pop("page", 1)
    per_page = params.pop("per_page", 20)

    result = _ip_audit_service.query_audit_logs(
        page=page,
        per_page=per_page,
        **{k: v for k, v in params.items() if v is not None}
    )

    return APIResponse.paginated(
        data=result["items"],
        page=result["page"],
        per_page=result["per_page"],
        total=result["total"],
        message="获取IP审计日志成功",
    )
