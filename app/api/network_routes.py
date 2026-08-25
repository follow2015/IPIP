# -*- coding: utf-8 -*-
"""
网络管理 API 路由

提供网段管理、路由查询等接口。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request

from app.api.base import APIResponse, ErrorCode
from app.openapi.doc import doc, public
from app.persistence.ip_repositories import IPNetworkRepository, IPManagerRepository
from app.persistence.network_repo import NetworkRepository
from app.utils.network_utils import get_network_info
from app.utils.auth import login_required, permission_required
from app.core.enums import NotificationTypeCode
from app.utils.transactional import transactional

logger = get_logger(__name__)

router = Blueprint("network", __name__, url_prefix="/api/network")


@router.route("/routes", methods=["GET"])
@doc(summary="查询路由列表", tags=["网段"], responses={200: "IPNetworkResponse", 401: "ApiError"})
@login_required
def list_routes():
    """查询路由列表

    支持按交换机、机房、路由类型过滤。
    route_type 已迁移至 switch_routes 表，需通过子查询过滤并补充字段。
    """
    switch_id = request.args.get("switch_id", type=int)
    room_id = request.args.get("room_id", type=int)
    route_type = request.args.get("route_type", type=int)
    notes = request.args.get("notes", type=int)
    route_type_val = route_type if route_type is not None else notes

    repo = IPNetworkRepository()
    filters = {}
    if switch_id is not None:
        filters["switch_id"] = switch_id
    if room_id is not None:
        filters["room_id"] = room_id
    if route_type_val is not None:
        matching_ids = repo.find_network_ids_by_route_type(route_type_val)
        if not matching_ids:
            return APIResponse.success(data=[])  # 无匹配路由类型，直接返回空
        filters["id"] = matching_ids

    routes = repo.find_all(filters)
    network_ids = [r.id for r in routes]
    sr_map: dict = {}
    if network_ids:
        sr_map = repo.find_switch_routes_by_network_ids(network_ids)

    data = []
    for r in routes:
        d = r.to_dict()
        sr = sr_map.get(r.id)
        d["route_type"] = sr.route_type if sr else None
        d["nexthop"] = sr.nexthop if sr else None
        data.append(d)
    return APIResponse.success(data=data)


@router.route("/info", methods=["GET"])
@doc(summary="查询网段详细信息", tags=["网段"], responses={200: "IPNetworkResponse", 400: "ApiError", 401: "ApiError"})
@login_required
def network_info():
    """查询网段详细信息

    查询参数: cidr (如 10.10.1.0/24)
    """
    cidr = request.args.get("cidr")
    if not cidr:
        return APIResponse.error("缺少 cidr 参数", ErrorCode.VALIDATION_ERROR, 400)

    info = get_network_info(cidr)
    if "error" in info:
        return APIResponse.error(info["error"], ErrorCode.VALIDATION_ERROR, 400)

    return APIResponse.success(data=info)


@router.route("/usage", methods=["GET"])
@doc(summary="查询网段使用率", tags=["网段"], responses={200: "IPNetworkResponse", 400: "ApiError", 401: "ApiError"})
@login_required
def network_usage():
    """查询网段使用率

    查询参数: cidr
    返回字段对齐前端: total_ips, used_ips, available_ips, usage_rate(小数0~1)
    直接对 ip_addresses 表做 SUM(CASE WHEN) 聚合统计，与 IP 管理页面数据源一致。
    IP 可能分散在不同机房，因此只按 CIDR 范围统计，不限制 room_id。
    """
    import ipaddress as _ipaddress

    cidr = request.args.get("cidr")

    if not cidr:
        return APIResponse.error("缺少 cidr 参数", ErrorCode.VALIDATION_ERROR, 400)

    try:
        net = _ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return APIResponse.error(f"无效的网段格式: {cidr}", ErrorCode.VALIDATION_ERROR, 400)

    ip_repo = IPManagerRepository()
    stats = ip_repo.get_status_statistics_by_cidr(cidr)

    used_count = stats["active"] + stats["blocked"]
    total_ips = max(1, net.num_addresses - 2)  # 减去网络地址和广播地址
    usage_rate = round(used_count / total_ips, 4)

    return APIResponse.success(data={
        "total_ips": total_ips,
        "used_ips": used_count,
        "available_ips": total_ips - used_count,
        "usage_rate": usage_rate,
        "active": stats["active"],
        "inactive": stats["inactive"],
        "blocked": stats["blocked"],
        "unused": stats["unused"],
    })


@router.route("/list", methods=["GET"])
@doc(summary="分页获取网段列表", tags=["网段"], responses={200: "IPNetworkResponse", 401: "ApiError"})
@login_required
def get_networks():
    """分页获取网段列表"""
    from app.services.network_service import NetworkService
    filters = {
        "room_id": request.args.get("room_id", type=int),
        "switch_id": request.args.get("switch_id", type=int),
        "customer_id": request.args.get("customer_id", type=int),
        "search": request.args.get("search"),
        "route_type": request.args.get("route_type", type=int),
        "page": request.args.get("page", 1, type=int),
        "page_size": request.args.get("per_page", 20, type=int),
    }
    service = NetworkService(NetworkRepository(), IPManagerRepository())
    result = service.get_networks_paginated(**filters)
    return APIResponse.success(data=result)


@router.route("/<path:ip_network>", methods=["DELETE"])
@doc(summary="删除网段", tags=["网段"], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("network:delete")
@transactional
def delete_network(ip_network):
    """删除网段"""
    from app.services.network_service import NetworkService
    data = request.get_json(silent=True) or {}
    network_id = data.get("network_id")
    if not network_id:
        return APIResponse.error("缺少network_id", ErrorCode.VALIDATION_ERROR, 400)
    net_repo = IPNetworkRepository()
    net_record = net_repo.find_by_id(network_id)
    if net_record and net_record.network != ip_network:
        return APIResponse.error(
            f"URL路径({ip_network})与记录网段({net_record.network})不一致",
            ErrorCode.VALIDATION_ERROR, 400,
        )
    service = NetworkService(NetworkRepository(), IPManagerRepository())
    if service.delete_network(network_id):
        return APIResponse.success(data={"deleted": True})
    return APIResponse.error("网段不存在", ErrorCode.NOT_FOUND, 404)


@router.route("/<path:ip_network>/customer", methods=["PUT"])
@doc(summary="更新网段客户", tags=["网段"], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("network:update")
@transactional
def update_network_customer(ip_network):
    """更新网段客户"""
    from app.services.network_service import NetworkService
    data = request.get_json()
    network_id = data.get("network_id")
    customer_id = data.get("customer_id")
    force = bool(data.get("force", False))
    if not network_id or "customer_id" not in data:
        return APIResponse.error("缺少network_id或customer_id", ErrorCode.VALIDATION_ERROR, 400)
    net_repo = IPNetworkRepository()
    net_record = net_repo.find_by_id(network_id)
    if net_record and net_record.network != ip_network:
        return APIResponse.error(
            f"URL路径({ip_network})与记录网段({net_record.network})不一致",
            ErrorCode.VALIDATION_ERROR, 400,
        )
    service = NetworkService(NetworkRepository(), IPManagerRepository())
    if service.update_network_customer(network_id, customer_id, force=force):
        return APIResponse.success(data={"updated": True})
    return APIResponse.error("更新失败", ErrorCode.NOT_FOUND, 404)


@router.route("/ip_networks", methods=["GET"])
@doc(summary="分页获取IP网段", tags=["网段"], responses={200: "IPNetworkResponse", 401: "ApiError"})
@login_required
def get_ip_networks():
    """分页获取IP网段"""
    from app.services.network_service import NetworkService
    filters = {
        "room_id": request.args.get("room_id", type=int),
        "customer_id": request.args.get("customer_id", type=int),
        "page": request.args.get("page", 1, type=int),
        "page_size": request.args.get("per_page", 20, type=int),
    }
    service = NetworkService(NetworkRepository(), IPManagerRepository())
    result = service.get_ip_networks_paginated(**filters)
    return APIResponse.success(data=result)


@router.route("/<path:ip_network>/ips", methods=["GET"])
@doc(summary="获取网段详情（含IP列表和状态统计）", tags=["网段"], responses={200: "IPNetworkResponse", 400: "ApiError", 401: "ApiError"})
@login_required
def get_network_detail(ip_network):
    """获取网段详情（含基本信息+IP列表+状态统计+路由关联信息）

    返回结构对齐前端 NetworkDetailResponse：
    - network_info: 网段CIDR计算信息（子网掩码/网关/可用IP数等）
    - ip_addresses: 网段内IP列表（含关联字段 switch_name/port/customer_name 等）
    - ip_status_count: 各状态IP数量统计
    - network_info_list: 该网段在 ip_networks 表中的路由关联信息
    """
    import ipaddress as _ipaddress
    from app.persistence.room_repository import RoomRepository
    from app.persistence.customer_repository import CustomerRepository
    from app.persistence.switch_ext_repository import SwitchExtRepository

    room_id = request.args.get("room_id", type=int)
    switch_id = request.args.get("switch_id", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("per_page", 20, type=int)

    net_info = get_network_info(ip_network)
    if "error" in net_info:
        return APIResponse.error(net_info["error"], ErrorCode.VALIDATION_ERROR, 400)

    net_repo = IPNetworkRepository()
    net_filters = {"network": ip_network}
    if switch_id is not None:
        net_filters["switch_id"] = switch_id
    network_records = net_repo.find_all(net_filters)
    if network_records:
        rec = network_records[0]
        net_info["switch_id"] = rec.switch_id
        net_info["room_id"] = rec.room_id
        net_info["port"] = rec.port
        sr = net_repo.find_switch_route(rec.switch_id, rec.network, rec.room_id)
        net_info["nexthop"] = sr.nexthop if sr else None
        net_info["notes"] = rec.notes
        net_info["updated_at"] = rec.updated_at.isoformat() if rec.updated_at else None
        if rec.switch_id:
            sw = SwitchExtRepository().get_by_device_id(rec.switch_id)
            net_info["switch_name"] = sw.device.device_name if sw and sw.device else None
        if rec.room_id:
            room = RoomRepository().find_by_id(rec.room_id)
            net_info["room_name"] = room.name if room else None
        if rec.customer_id:
            cust = CustomerRepository().find_by_id(rec.customer_id)
            net_info["customer_name"] = cust.customer_name if cust else None

    ip_repo = IPManagerRepository()
    try:
        net = _ipaddress.ip_network(ip_network, strict=False)
    except ValueError:
        return APIResponse.error(f"无效的网段格式: {ip_network}", ErrorCode.VALIDATION_ERROR, 400)

    paginated = ip_repo.paginate_with_relations_by_cidr(ip_network, room_id, page, page_size)
    items = paginated["data"]
    total = paginated["total"]
    total_pages = paginated["total_pages"]

    room_ids = {item.room_id for item in items if item.room_id}
    customer_ids = {item.customer_id for item in items if item.customer_id}
    switch_device_ids = set()
    for item in items:
        if item.ip_switch_info and item.ip_switch_info.switch_id:
            switch_device_ids.add(item.ip_switch_info.switch_id)

    room_map = {}
    if room_ids:
        for r in RoomRepository().find_by_ids(list(room_ids)):
            room_map[r.id] = r.name

    customer_map = {}
    if customer_ids:
        for c in CustomerRepository().find_by_ids(list(customer_ids)):
            customer_map[c.id] = c.customer_name

    switch_map = {}
    if switch_device_ids:
        switch_map = SwitchExtRepository().get_device_name_map_by_ids(list(switch_device_ids))

    ip_list = []
    for item in items:
        item_dict = item.to_dict()
        if item.ip_switch_info:
            item_dict["mac_address"] = item.ip_switch_info.mac_address or "N/A"
            item_dict["port"] = item.ip_switch_info.port
            item_dict["switch_name"] = switch_map.get(item.ip_switch_info.switch_id)
        else:
            item_dict["mac_address"] = "N/A"
            item_dict["port"] = None
            item_dict["switch_name"] = None
        item_dict["customer_name"] = customer_map.get(item.customer_id)
        item_dict["room_name"] = room_map.get(item.room_id)
        ip_list.append(item_dict)

    stats = ip_repo.get_status_statistics_by_cidr(ip_network)
    status_count = {
        "在线": stats["active"],
        "离线": stats["inactive"],
        "封禁": stats["blocked"],
        "未使用": stats["unused"],
    }

    network_ids_for_list = [r.id for r in network_records]
    sr_map_list: dict = {}
    if network_ids_for_list:
        switch_ids_set = {r.switch_id for r in network_records}
        destinations_set = {r.network for r in network_records}
        sr_rows = net_repo.find_switch_routes_by_switch_destinations(switch_ids_set, destinations_set)
        for sr in sr_rows:
            key = (sr.switch_id, sr.destination)
            if key not in sr_map_list:
                sr_map_list[key] = sr

    network_info_list = []
    for rec in network_records:
        sr = sr_map_list.get((rec.switch_id, rec.network))
        info_item = {
            "switch_id": rec.switch_id,
            "port": rec.port,
            "nexthop": sr.nexthop if sr else None,
            "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
            "route_type": sr.route_type if sr else None,
            "notes": rec.notes,
            "switch_name": None,
            "room_name": None,
            "customer_name": None,
        }
        if rec.switch_id:
            info_item["switch_name"] = switch_map.get(rec.switch_id)
        if rec.room_id:
            info_item["room_name"] = room_map.get(rec.room_id)
        if rec.customer_id:
            info_item["customer_name"] = customer_map.get(rec.customer_id)
        network_info_list.append(info_item)

    return APIResponse.success(data={
        "network_info": net_info,
        "ip_addresses": ip_list,
        "ip_status_count": status_count,
        "network_info_list": network_info_list,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    })




@router.route("/scan/<int:room_id>", methods=["POST"])
@doc(summary="触发全量扫描（异步）", tags=["网段"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("network:scan")
def trigger_full_scan(room_id):
    """触发全量扫描（异步），含重入保护"""
    from flask import current_app
    from app.services.network_scanner_service import ScanOrchestrator
    from app.services.scan_redis import ScanRedis

    try:
        from app.utils.cache import cache_manager
        if cache_manager.primary_storage and cache_manager.primary_storage.redis_client:
            sr = ScanRedis(cache_manager.primary_storage.redis_client)
            progress = sr.progress_get(room_id)
            if progress and progress.get("phase") not in ("完成", "failed", None):
                return APIResponse.error("已有扫描任务进行中", status_code=400)
            sr.progress_set(room_id, {
                "room_id": room_id,
                "total": 0,
                "completed": 0,
                "failed": 0,
                "phase": "准备中",
                "elapsed_seconds": 0,
                "eta_seconds": 0,
            })
    except Exception:
        logger.warning("全量扫描重入保护检查失败: room_id=%d", room_id, exc_info=True)

    orchestrator = ScanOrchestrator()

    def _scan():
        with current_app.app_context():
            result = orchestrator.full_scan(room_id)
            scan_failed = isinstance(result, dict) and result.get("status") == "failed"
            scan_reason = result.get("reason", "") if isinstance(result, dict) else ""

            try:
                from app.services.switch_events import emit_resource_change, emit_global_event
                from app.persistence.switch_ext_repository import SwitchExtRepository
                switches = SwitchExtRepository().get_all_by_room(room_id)
                for sw in switches:
                    emit_resource_change(sw.device_id, "scan_complete", affected_ports=["*"])
                emit_global_event("room_scan_complete", {"room_id": room_id, "reason": scan_reason} if scan_failed else {"room_id": room_id})
            except Exception as _e:
                logger.warning("全量扫描 SSE 通知失败（不影响数据）: %s", _e)

            try:
                from app.services.notification_service import notification_service
                from app.persistence.room_repository import RoomRepository
                room = RoomRepository().find_by_id(room_id)
                room_name = room.name if room else f"机房#{room_id}"
                if scan_failed:
                    notification_service.notify(
                        type=NotificationTypeCode.ROOM_SCAN_FAILED,
                        severity="warning",
                        title="机房扫描失败",
                        content=f"机房「{room_name}」全量扫描失败：{result.get('message', scan_reason) if isinstance(result, dict) else scan_reason}",
                        payload={"room_id": room_id, "reason": scan_reason},
                        source_module="network_scanner",
                        target_type="broadcast",

                        idempotency_key=f"scan_failed:room:{room_id}:{int(__import__('time').time())}",
                    )
                else:
                    notification_service.notify(
                        type=NotificationTypeCode.ROOM_SCAN_COMPLETE,
                        severity="info",
                        title="机房扫描完成",
                        content=f"机房「{room_name}」全量扫描已完成，数据已更新",
                        payload={"room_id": room_id},
                        source_module="network_scanner",
                        target_type="broadcast",

                        idempotency_key=f"scan_complete:room:{room_id}:{int(__import__('time').time())}",
                    )
            except Exception as _e:
                logger.warning("扫描完成通知创建失败（不影响数据）: %s", _e)

    from app.utils.concurrency.task_executor import task_executor
    task_executor.submit("scan_network", _scan)
    return APIResponse.success({"room_id": room_id, "status": "started"})


@router.route("/scan/status/<int:room_id>", methods=["GET"])
@doc(summary="查询扫描进度", tags=["网段"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def get_scan_status(room_id):
    """查询扫描进度"""
    from app.services.scan_redis import ScanRedis
    try:
        from app.utils.cache import cache_manager
        if cache_manager.primary_storage and cache_manager.primary_storage.redis_client:
            sr = ScanRedis(cache_manager.primary_storage.redis_client)
            progress = sr.progress_get(room_id)
            if progress:
                return APIResponse.success(progress)
    except Exception:
        logger.warning("查询扫描进度失败: room_id=%d", room_id, exc_info=True)
    return APIResponse.success({"phase": "unknown", "detail": ""})




@router.route("/no-auth-fallback/<int:room_id>", methods=["GET"])
@doc(summary="查询降级映射", tags=["网段"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def get_no_auth_fallback(room_id):
    """查询当前所有降级映射"""
    from app.services.scan_redis import ScanRedis
    try:
        from app.utils.cache import cache_manager
        if cache_manager.primary_storage and cache_manager.primary_storage.redis_client:
            redis_client = cache_manager.primary_storage.redis_client
            sr = ScanRedis(redis_client)
            key = f"no_auth_fallback:{room_id}"
            mapping = redis_client.hgetall(key)
            return APIResponse.success(mapping)
    except Exception as e:
        return APIResponse.error(str(e))
    return APIResponse.success({})


@router.route("/no-auth-fallback/rebuild", methods=["POST"])
@doc(summary="手动重建Redis降级映射", tags=["网段"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("system:config")
def rebuild_no_auth_fallback():
    """手动触发从数据库重建 Redis 映射"""
    from app.services.scan_redis import ScanRedis
    from app.persistence.switch_ext_repository import SwitchExtRepository
    from app.persistence.switch_repo import SwitchRepository
    data = request.get_json()
    room_id = data.get("room_id")
    if not room_id:
        return APIResponse.error("room_id 必填", ErrorCode.VALIDATION_ERROR, 400)
    try:
        from app.utils.cache import cache_manager
        if cache_manager.primary_storage and cache_manager.primary_storage.redis_client:
            sr = ScanRedis(cache_manager.primary_storage.redis_client)
            sr.fallback_rebuild_from_db(
                room_id, SwitchExtRepository(), SwitchRepository()
            )
            return APIResponse.success({"room_id": room_id, "status": "rebuilt"})
    except Exception as e:
        return APIResponse.error(str(e))
    return APIResponse.error("Redis 不可用")
