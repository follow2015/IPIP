# -*- coding: utf-8 -*-
"""
链路聚合组 API

提供链路聚合组管理的 RESTful API 端点。
- lag_bp: 设备级端点，挂载在 /api/switch 下
- lag_global_bp: 全局端点，挂载在 /api/link-aggregation 下

路由去重说明（Task 0）：
设备级 port-channels 的创建/删除端点由 app/api/switch_routes.py 以 SSH 实现胜出
（Werkzeug url_map 取首个注册命中，switch_routes 先于 lag_bp 注册），本文件仅保留
GET 列表端点（switch_routes 无对应 GET 列表端点）。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request

from app.api.base import APIResponse
from app.services.link_aggregation_service import LinkAggregationService
from app.persistence.link_aggregation_repository import LinkAggregationRepository
from app.openapi.doc import doc, public
from app.utils import login_required, permission_required, rate_limit_api

logger = get_logger(__name__)

lag_bp = Blueprint("link_aggregation", __name__)

lag_global_bp = Blueprint("link_aggregation_global", __name__)

_lag_service = LinkAggregationService(LinkAggregationRepository())




@lag_global_bp.route("/", methods=["GET"])
@doc(summary="获取所有链路聚合组", tags=["链路聚合"], responses={200: "LinkAggregationGroupResponse", 401: "ApiError"})
@login_required
@permission_required("switch:view")
@rate_limit_api
def list_all_port_channels():
    """获取所有链路聚合组（全局视图，分页）

    Query Parameters:
        page (int): 页码，默认 1
        per_page (int): 每页数量，默认 20
        search (str, optional): 模糊搜索（匹配聚合组名称）
        room_id (int, optional): 按机房筛选
        device_id (int, optional): 按交换机筛选
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", type=str)
    room_id = request.args.get("room_id", type=int)
    device_id = request.args.get("device_id", type=int)
    result = _lag_service.get_all_with_device_info_paginated(
        page=page, per_page=per_page, search=search,
        room_id=room_id, device_id=device_id,
    )
    return APIResponse.paginated(result["items"], page, per_page, result["total"])




@lag_bp.route("/<int:device_id>/port-channels", methods=["GET"])
@doc(summary="获取设备的链路聚合组", tags=["链路聚合"], responses={200: "LinkAggregationGroupResponse", 401: "ApiError"})
@login_required
@permission_required("switch:view")
@rate_limit_api
def get_port_channels(device_id):
    """获取设备的链路聚合组

    Path Parameters:
        device_id (int): 设备ID
    """
    groups = _lag_service.get_by_device(device_id)
    return APIResponse.success(data=[g.to_dict() for g in groups])
