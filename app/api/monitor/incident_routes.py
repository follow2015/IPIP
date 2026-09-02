# -*- coding: utf-8 -*-
"""事件中心 API（事件聚合 Task 5）

GET /api/monitor/incidents        事件列表（默认非 closed，支持 status 过滤 + 分页）
GET /api/monitor/incidents/<id>   事件详情（含关联告警 + 被抑制下游设备）
"""
from flask import request

from app.api.base import APIResponse
from app.api.monitor import logger, monitor_bp
from app.exceptions.business import BusinessLogicError
from app.openapi.doc import doc
from app.persistence.monitor_incident_repository import IncidentRepository
from app.utils import login_required, permission_required

_INCIDENT_STATUS_WHITELIST = {"active", "acknowledged", "closed"}


@monitor_bp.route("/incidents", methods=["GET"])
@doc(summary="查询事件列表", tags=["监控"], responses={200: "MonitorIncidentListResponse"})
@login_required
@permission_required("monitor:view")
def list_incidents():
    """分页查询事件列表，默认只返回非 closed 事件。

    Query:
        status: 显式状态过滤（active/acknowledged/closed）；不传则返回非 closed
        page / per_page: 分页
    """
    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 20)), 1), 100)
    except ValueError:
        raise BusinessLogicError("page/per_page 必须为正整数", status_code=400)

    status = (request.args.get("status") or "").strip() or None
    if status is not None and status not in _INCIDENT_STATUS_WHITELIST:
        raise BusinessLogicError(
            f"status 仅支持 {sorted(_INCIDENT_STATUS_WHITELIST)}", status_code=400,
        )

    repo = IncidentRepository()
    offset = (page - 1) * per_page
    if status:
        items = repo.list_by_status(status, limit=per_page, offset=offset)
        total = repo.count_by_status(status)
    else:
        items = repo.list_active(limit=per_page, offset=offset)
        total = repo.count_active()
    return APIResponse.paginated(
        data=[i.to_dict() for i in items],
        page=page, per_page=per_page, total=total,
    )


@monitor_bp.route("/incidents/<int:incident_id>", methods=["GET"])
@doc(summary="查询事件详情", tags=["监控"], responses={200: "MonitorIncidentDetailResponse"})
@login_required
@permission_required("monitor:view")
def get_incident(incident_id: int):
    """返回事件详情，含关联告警列表与被抑制的下游设备列表。

    DB 访问全部走 IncidentRepository（C5 约束）。
    """
    repo = IncidentRepository()
    inc = repo.get(incident_id)
    if inc is None:
        raise BusinessLogicError("事件不存在", status_code=404)

    related_alerts = repo.list_alerts_by_incident(incident_id, limit=200)
    suppressed_logs = repo.list_suppressed_by_incident(incident_id, limit=200)

    data = inc.to_dict()
    data["related_alerts"] = [a.to_dict(exclude=["payload"]) for a in related_alerts]
    data["suppressed_logs"] = [l.to_dict() for l in suppressed_logs]
    return APIResponse.success(data=data)
