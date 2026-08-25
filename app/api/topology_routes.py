# -*- coding: utf-8 -*-
"""
网络拓扑 API 路由

提供拓扑数据聚合和自动推断接口。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request

from app.api.base import APIResponse, ErrorCode, api_exception_handler
from app.openapi.doc import doc
from app.services.topology_service import TopologyService
from app.utils.auth import login_required
from app.utils.transactional import transactional

logger = get_logger(__name__)

router = Blueprint("topology", __name__, url_prefix="/api/topology")

_topology_service = TopologyService()


@router.route("/network", methods=["GET"])
@login_required
@api_exception_handler
@doc(
    summary="获取网络层拓扑",
    tags=["拓扑"],
    parameters=[
        {"name": "room_id", "in": "query", "schema": {"type": "integer"}, "description": "机房ID"},
        {"name": "virtual_room_id", "in": "query", "schema": {"type": "integer"}, "description": "虚拟机房ID（与room_id互斥，优先级更高）"},
        {"name": "layer", "in": "query", "schema": {"type": "integer"}, "description": "网络层级"},
        {"name": "include_offline", "in": "query", "schema": {"type": "boolean"}, "description": "是否包含离线设备"},
    ],
    responses={200: {"description": "网络层拓扑数据（交换机 + N2N 互联 + uplink 逻辑链路）"}},
)
def get_network_topology():
    """获取网络层拓扑"""
    room_id = request.args.get("room_id", type=int)
    virtual_room_id = request.args.get("virtual_room_id", type=int)
    layer = request.args.get("layer", type=int)
    include_offline = request.args.get("include_offline", "false").lower() in ("true", "1", "yes")

    result = _topology_service.build_network_topology(
        room_id=room_id,
        virtual_room_id=virtual_room_id,
        layer=layer,
        include_offline=include_offline,
    )
    return APIResponse.success(data=result, message="获取网络拓扑成功")


@router.route("/device", methods=["GET"])
@login_required
@api_exception_handler
@doc(
    summary="获取设备层拓扑",
    tags=["拓扑"],
    parameters=[
        {"name": "room_id", "in": "query", "schema": {"type": "integer"}, "description": "机房ID"},
        {"name": "virtual_room_id", "in": "query", "schema": {"type": "integer"}, "description": "虚拟机房ID（与room_id互斥，优先级更高）"},
        {"name": "cabinet_id", "in": "query", "schema": {"type": "integer"}, "description": "机柜ID"},
        {"name": "switch_device_id", "in": "query", "schema": {"type": "integer"}, "description": "以某交换机为中心展开"},
    ],
    responses={200: {"description": "设备层拓扑数据（交换机 + 服务器 + N2N + D2N）"}},
)
def get_device_topology():
    """获取设备层拓扑"""
    room_id = request.args.get("room_id", type=int)
    virtual_room_id = request.args.get("virtual_room_id", type=int)
    cabinet_id = request.args.get("cabinet_id", type=int)
    switch_device_id = request.args.get("switch_device_id", type=int)

    result = _topology_service.build_device_topology(
        room_id=room_id,
        virtual_room_id=virtual_room_id,
        cabinet_id=cabinet_id,
        switch_device_id=switch_device_id,
    )
    return APIResponse.success(data=result, message="获取设备拓扑成功")


@router.route("/auto-detect", methods=["POST"])
@login_required
@api_exception_handler
@transactional
@doc(
    summary="自动推断拓扑字段",
    tags=["拓扑"],
    responses={200: {"description": "推断结果（dry_run=true时不写入DB）"}},
)
def auto_detect_topology():
    """基于 N2N 连接自动推断 switch_role / layer / uplink_device_id / core_device_id"""
    data = request.get_json(silent=True) or {}
    room_id = data.get("room_id")
    dry_run = data.get("dry_run", True)
    force = data.get("force", False)

    if not room_id:
        return APIResponse.error("缺少必填字段: room_id", ErrorCode.VALIDATION_ERROR, 400)

    result = _topology_service.auto_detect_topology(
        room_id=room_id,
        dry_run=dry_run,
        force=force,
    )
    return APIResponse.success(data=result, message="自动推断完成")
