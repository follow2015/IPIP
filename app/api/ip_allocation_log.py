# -*- coding: utf-8 -*-
"""
IP分配日志 API

提供IP分配历史查询的 RESTful API 端点。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request

from app.api.base import APIResponse
from app.services.ip_allocation_log_service import IPAllocationLogService
from app.persistence.ip_allocation_log_repository import IPAllocationLogRepository
from app.openapi.doc import doc, public
from app.utils import login_required, permission_required, rate_limit_api

logger = get_logger(__name__)

ip_alloc_log_bp = Blueprint("ip_allocation_log", __name__)

_ip_alloc_log_service = IPAllocationLogService(IPAllocationLogRepository())


@ip_alloc_log_bp.route("/<ip_address>/allocations", methods=["GET"])
@doc(summary="获取IP分配历史", tags=["IP"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@permission_required("ip:view")
@rate_limit_api
def get_ip_allocations(ip_address):
    room_id = request.args.get('room_id', type=int)
    records = _ip_alloc_log_service.get_by_ip_room(ip_address, room_id)
    return APIResponse.success(data=[r.to_dict() for r in records])
