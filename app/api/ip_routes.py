# -*- coding: utf-8 -*-
"""
IP 管理 + 封禁/解封 API 路由

提供 IP 地址管理、状态查询、封禁/解封等接口。
"""
import ipaddress
from app.utils.logging import get_logger

from flask import Blueprint, request, Response

from app.api.base import APIResponse, ErrorCode
from app.api.validators import parse_ip_room
from app.openapi.doc import doc, public
from app.utils.auth import login_required, permission_required
from app.core.enums import IPStatus, NotificationTypeCode
from app.utils.transactional import transactional
from app.exceptions.business import (
    IPAlreadyBannedException, IPNotBannedException,
    NoCoreSwitch, BanCommandFailed,
)
from app.services.ip_ban_service import IPBanService, ban_ip_list, unban_ip_list
from app.infra import SSHManager
from app.services.ip_status_service import detect_ip_status
from app.persistence.ip_repositories import IPManagerRepository

logger = get_logger(__name__)

router = Blueprint("ip", __name__, url_prefix="/api/ip")


@router.route("/ban", methods=["POST"])
@doc(summary="封禁IP（通过交换机黑洞路由）", tags=["IP"], responses={200: "ApiResponse", 400: "ApiError", 409: "ApiError", 503: "ApiError"})
@login_required
@permission_required("ip:update")
def ban_ip_endpoint():
    """封禁 IP（通过交换机黑洞路由）

    请求体: {"ip_address": "10.10.1.100"}
    room_id 可选，为空时自动查找该IP所在机房
    """
    data = request.get_json()
    ip_address = data.get("ip_address")
    room_id = data.get("room_id")  # 可选

    if not ip_address:
        return APIResponse.error("缺少 ip_address", ErrorCode.VALIDATION_ERROR, 400)

    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        return APIResponse.error(f"无效的 IP 地址格式: {ip_address}", ErrorCode.VALIDATION_ERROR, 400)

    service = IPBanService(SSHManager())
    try:
        ban_result = service.ban_ip(ip_address=ip_address, room_id=room_id)
    except IPAlreadyBannedException as e:
        return APIResponse.error(str(e), ErrorCode.DUPLICATE_ERROR, 409)
    except (NoCoreSwitch, BanCommandFailed) as e:
        return APIResponse.error(str(e), status_code=503)
    except ValueError as e:
        return APIResponse.error(str(e), ErrorCode.VALIDATION_ERROR, 400)

    return APIResponse.success(
        data={
            "ip_address": ban_result.ip_address,
            "switch_id": ban_result.switch_id,
            "switch_ip": ban_result.switch_ip,
        },
        message=ban_result.message,
    )


@router.route("/unban", methods=["POST"])
@doc(summary="解封IP（撤销交换机黑洞路由）", tags=["IP"], responses={200: "ApiResponse", 400: "ApiError", 409: "ApiError", 503: "ApiError"})
@login_required
@permission_required("ip:update")
def unban_ip_endpoint():
    """解封 IP（撤销交换机黑洞路由/静态ARP）

    请求体: {"ip_address": "10.10.1.100", "room_id": 3}
    room_id 可选，为空时自动查找该IP所在机房
    """
    data = request.get_json()
    ip_address = data.get("ip_address")
    room_id = data.get("room_id")  # 可选

    if not ip_address:
        return APIResponse.error("缺少 ip_address", ErrorCode.VALIDATION_ERROR, 400)

    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        return APIResponse.error(f"无效的 IP 地址格式: {ip_address}", ErrorCode.VALIDATION_ERROR, 400)

    service = IPBanService(SSHManager())
    try:
        unban_result = service.unban_ip(ip_address=ip_address, room_id=room_id)
    except IPNotBannedException as e:
        return APIResponse.error(str(e), ErrorCode.DUPLICATE_ERROR, 409)
    except (NoCoreSwitch, BanCommandFailed) as e:
        return APIResponse.error(str(e), status_code=503)
    except ValueError as e:
        return APIResponse.error(str(e), ErrorCode.VALIDATION_ERROR, 400)

    return APIResponse.success(
        data={
            "ip_address": unban_result.ip_address,
            "switch_id": unban_result.switch_id,
            "switch_ip": unban_result.switch_ip,
        },
        message=unban_result.message,
    )


@router.route("/ban/batch", methods=["POST"])
@doc(summary="批量封禁IP", tags=["IP"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("ip:update")
def batch_ban_endpoint():
    """批量封禁 IP

    请求体: {"ip_list": ["10.10.1.100", "10.10.1.101"]}
    room_id 可选，为空时逐IP自动查找所在机房
    """
    data = request.get_json()
    ip_list = data.get("ip_list", [])
    room_id = data.get("room_id")  # 可选

    if not ip_list:
        return APIResponse.error("缺少 ip_list", ErrorCode.VALIDATION_ERROR, 400)

    service = IPBanService(SSHManager())
    result = ban_ip_list(service, ip_list, room_id)

    failed_count = len(result.get("failed", []))
    success_count = len(result.get("success", []))
    if failed_count > 0:
        from app.services.notification_service import notification_service
        from flask import g
        user_id = g.current_user["user_id"] if hasattr(g, 'current_user') else None
        severity = "warning" if success_count > 0 else "critical"
        title = "批量封禁IP部分失败" if success_count > 0 else "批量封禁IP全部失败"
        notification_service.notify(
            type=NotificationTypeCode.BATCH_BAN_IP,
            severity=severity,
            title=title,
            content=f"共 {len(ip_list)} 个IP，成功 {success_count} 个，失败 {failed_count} 个",
            payload={"room_id": room_id, "success_count": success_count, "failed_count": failed_count},
            source_module="ip_ban",
            target_type="user",
            target_id=user_id,
            idempotency_key=f"batch_ban:{user_id or 'anon'}:{int(__import__('time').time())}",
        )

    return APIResponse.success(data=result)


@router.route("/unban/batch", methods=["POST"])
@doc(summary="批量解封IP", tags=["IP"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("ip:update")
def batch_unban_endpoint():
    """批量解封 IP

    请求体: {"ip_list": ["10.10.1.100", "10.10.1.101"], "room_id": 3}
    room_id 可选，为空时自动查找每个IP所在机房
    """
    data = request.get_json()
    ip_list = data.get("ip_list", [])
    room_id = data.get("room_id")

    if not ip_list:
        return APIResponse.error("缺少 ip_list", ErrorCode.VALIDATION_ERROR, 400)

    service = IPBanService(SSHManager())
    result = unban_ip_list(service, ip_list, room_id)

    failed_count = len(result.get("failed", []))
    success_count = len(result.get("success", []))
    if failed_count > 0:
        from app.services.notification_service import notification_service
        from flask import g
        user_id = g.current_user["user_id"] if hasattr(g, 'current_user') else None
        severity = "warning" if success_count > 0 else "critical"
        title = "批量解封IP部分失败" if success_count > 0 else "批量解封IP全部失败"
        notification_service.notify(
            type=NotificationTypeCode.BATCH_UNBAN_IP,
            severity=severity,
            title=title,
            content=f"共 {len(ip_list)} 个IP，成功 {success_count} 个，失败 {failed_count} 个",
            payload={"room_id": room_id, "success_count": success_count, "failed_count": failed_count},
            source_module="ip_ban",
            target_type="user",
            target_id=user_id,
            idempotency_key=f"batch_unban:{user_id or 'anon'}:{int(__import__('time').time())}",
        )

    return APIResponse.success(data=result)


@router.route("/<ip_address>/ban_status", methods=["GET"])
@doc(summary="查询IP封禁状态", tags=["IP"], responses={200: "IPAddressResponse", 400: "ApiError", 404: "ApiError"})
@login_required
def check_ban_status(ip_address):
    """查询 IP 封禁状态

    查询参数: room_id
    """
    room_id = request.args.get("room_id", type=int)
    if room_id is None:
        return APIResponse.error("缺少 room_id 参数", ErrorCode.VALIDATION_ERROR, 400)

    repo = IPManagerRepository()
    record = repo.get_by_ip_room(ip_address, room_id)
    if not record:
        return APIResponse.error(f"IP {ip_address} 不存在", ErrorCode.NOT_FOUND, 404)

    return APIResponse.success(data={
        "ip_address": ip_address,
        "is_banned": record.status == IPStatus.BANNED,
        "status": record.status,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    })


@router.route("/<ip_address>/detect", methods=["POST"])
@doc(summary="检测IP在线状态", tags=["IP"], responses={200: "IPAddressResponse", 400: "ApiError"})
@login_required
@permission_required("ip:scan")
def detect_ip_endpoint(ip_address):
    """检测 IP 在线状态

    执行 ping + 端口扫描，返回检测结果。
    """
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        return APIResponse.error(f"无效的 IP 地址格式: {ip_address}", ErrorCode.VALIDATION_ERROR, 400)

    status = detect_ip_status(ip_address)
    return APIResponse.success(data={
        "ip_address": ip_address,
        "status": int(status),
        "status_text": status.name,
    })


@router.route("/list", methods=["GET"])
@doc(summary="查询IP列表（分页）", tags=["IP"], responses={200: "IPAddressResponse", 401: "ApiError"})
@login_required
def list_ips():
    """查询 IP 列表（分页，含关联信息）

    支持按机房、状态、客户过滤，支持IP/MAC地址搜索。
    返回数据包含 switch_name, port, customer_name, room_name, mac_address。
    """
    room_id = request.args.get("room_id", type=int)
    status = request.args.get("status", type=int)
    customer_id = request.args.get("customer_id", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", type=str)

    repo = IPManagerRepository()
    filters = {}
    if room_id is not None:
        filters["room_id"] = room_id
    if status is not None:
        filters["status"] = status
    if customer_id is not None:
        filters["customer_id"] = customer_id

    result = repo.paginate_with_relations(
        page=page, page_size=page_size,
        filters=filters, search=search,
    )
    return APIResponse.paginated(
        data=result["data"],
        page=result["page"],
        per_page=result["page_size"],
        total=result["total_count"],
    )


@router.route("/<ip_address>/customer", methods=["PUT"])
@doc(summary="更新IP客户关联", tags=["IP"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("ip:update")
@transactional
def update_ip_customer(ip_address):
    """更新IP客户关联"""
    from app.services.ip_crud_service import IPRudService
    data = request.get_json()
    customer_id = data.get("customer_id")
    room_id = data.get("room_id")
    service = IPRudService(IPManagerRepository())
    count = service.update_ip_customer(ip_address, customer_id, room_id)
    if count:
        return APIResponse.success(data={"updated": count})
    return APIResponse.error("更新失败", ErrorCode.NOT_FOUND, 404)


@router.route("/<ip_address>/notes", methods=["GET"])
@doc(summary="获取IP备注", tags=["IP"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def get_ip_notes(ip_address):
    """获取IP备注"""
    from app.services.ip_crud_service import IPRudService
    room_id = request.args.get("room_id", type=int)
    service = IPRudService(IPManagerRepository())
    notes = service.get_ip_notes(ip_address, room_id)
    return APIResponse.success(data=notes)


@router.route("/<ip_address>/notes", methods=["PUT"])
@doc(summary="更新IP备注", tags=["IP"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("ip:update")
@transactional
def update_ip_notes(ip_address):
    """更新IP备注"""
    from app.services.ip_crud_service import IPRudService
    data = request.get_json()
    notes = data.get("notes", "")
    room_id = data.get("room_id")
    service = IPRudService(IPManagerRepository())
    count = service.update_ip_notes(ip_address, notes, room_id)
    if count:
        return APIResponse.success(data={"updated": count})
    return APIResponse.error("更新失败", ErrorCode.NOT_FOUND, 404)


@router.route("/batch/customer", methods=["POST"])
@doc(summary="批量更新IP客户关联", tags=["IP"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("ip:update")
@transactional
def batch_update_ip_customer():
    """批量更新IP客户关联

    请求体: {"ip_list": ["10.10.1.100", ...], "customer_id": 1, "room_id": 9(可选)}
    room_id 可选，不传则跨机房按 ip_address 更新。
    """
    data = request.get_json()
    ip_list = data.get("ip_list", [])
    customer_id = data.get("customer_id")
    room_id = data.get("room_id")

    if not ip_list:
        return APIResponse.error("缺少 ip_list", ErrorCode.VALIDATION_ERROR, 400)
    if customer_id is None:
        return APIResponse.error("缺少 customer_id", ErrorCode.VALIDATION_ERROR, 400)

    from app.services.customer_service import CustomerService
    from app.persistence.customer_repository import CustomerRepository
    try:
        CustomerService(CustomerRepository()).assert_allocatable(customer_id)
    except Exception as e:
        from app.exceptions.business import BusinessLogicError
        from app.exceptions.data_access import RecordNotFoundError
        if isinstance(e, (BusinessLogicError, RecordNotFoundError)):
            return APIResponse.error(str(e), ErrorCode.BUSINESS_ERROR, getattr(e, "status_code", 400))
        raise

    repo = IPManagerRepository()
    count = repo.batch_update_customer_by_ips(customer_id, ip_list, room_id)
    return APIResponse.success(data={"updated": count})


@router.route("/batch/notes", methods=["POST"])
@doc(summary="批量更新IP备注", tags=["IP"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("ip:update")
@transactional
def batch_update_ip_notes():
    """批量更新IP备注

    请求体: {"ip_list": ["10.10.1.100", ...], "notes": "备注文本", "room_id": 9(可选)}
    room_id 可选，不传则跨机房按 ip_address 更新。
    """
    data = request.get_json()
    ip_list = data.get("ip_list", [])
    notes = data.get("notes", "")
    room_id = data.get("room_id")

    if not ip_list:
        return APIResponse.error("缺少 ip_list", ErrorCode.VALIDATION_ERROR, 400)

    repo = IPManagerRepository()
    count = repo.batch_update_notes_by_ips(notes, ip_list, room_id)
    return APIResponse.success(data={"updated": count})


@router.route("/<ip_address>", methods=["GET"])
@doc(summary="获取IP详细信息", tags=["IP"], responses={200: "IPAddressDetailResponse", 404: "ApiError"})
@login_required
def get_ip_detail(ip_address):
    """获取IP详细信息（含5表JOIN关联数据）

    返回 switch_name, switch_ip, port, customer_name, room_name, mac_address 等关联字段。
    """
    room_id = request.args.get("room_id", type=int)
    repo = IPManagerRepository()
    detail = repo.get_detail_with_relations(ip_address, room_id)
    if detail:
        return APIResponse.success(data=detail)
    return APIResponse.error("IP不存在", ErrorCode.NOT_FOUND, 404)


@router.route("/<ip_address>/ping", methods=["POST"])
@doc(summary="Ping检测IP", tags=["IP"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("ip:scan")
def ping_ip(ip_address):
    """Ping检测"""
    from app.services.ip_crud_service import IPRudService
    service = IPRudService(IPManagerRepository())
    result = service.ping_ip(ip_address)
    return APIResponse.success(data={"ip": ip_address, "reachable": result})


@router.route("/<ip_address>/scan", methods=["POST"])
@doc(summary="端口扫描IP", tags=["IP"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("ip:scan")
def scan_ports(ip_address):
    """端口扫描"""
    from app.services.ip_crud_service import IPRudService
    data = request.get_json(silent=True) or {}
    ports = data.get("ports")
    service = IPRudService(IPManagerRepository())
    result = service.scan_ports(ip_address, ports)
    return APIResponse.success(data=result)


@router.route("/scan/network", methods=["POST"])
@doc(summary="异步扫描网段内所有IP状态", tags=["IP"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("ip:view")
def scan_network():
    """异步扫描网段内所有IP状态

    请求体: {"ip_network": "10.10.1.0/24", "room_id": 1}
    异步并发检测网段内每个IP的在线状态，立即返回，后台执行。
    """
    data = request.get_json()
    ip_network = data.get("ip_network")
    room_id = data.get("room_id")

    if not ip_network or room_id is None:
        return APIResponse.error("缺少 ip_network 或 room_id", ErrorCode.VALIDATION_ERROR, 400)

    try:
        network = ipaddress.ip_network(ip_network, strict=False)
    except ValueError:
        return APIResponse.error(f"无效的网段格式: {ip_network}", ErrorCode.VALIDATION_ERROR, 400)

    from flask import current_app, g

    network_str = str(network)
    app_ref = current_app._get_current_object()
    user_id = g.current_user["user_id"] if hasattr(g, 'current_user') else None

    def _async_scan():
        """后台执行网段扫描"""
        try:
            with app_ref.app_context():
                from app.services.ip_status_service import batch_detect_network_status
                batch_detect_network_status(network_str, room_id)
                from extensions import db
                db.session.commit()
                logger.info("异步网段扫描完成: %s (room=%d)", network_str, room_id)
                try:
                    from app.services.switch_events import emit_global_event
                    emit_global_event("ip_scan_complete", {
                        "network": network_str,
                        "room_id": room_id,
                    })
                except Exception:
                    logger.warning("异步网段扫描完成后 SSE 通知失败: network=%s, room_id=%d", network_str, room_id, exc_info=True)
                try:
                    if not user_id:
                        logger.warning("IP扫描完成通知跳过：user_id 为空")
                    else:
                        from app.services.notification_service import notification_service
                        notification_service.notify(
                            type=NotificationTypeCode.IP_SCAN_COMPLETE,
                            severity="info",
                            title="网段扫描完成",
                            content=f"网段 {network_str} 扫描已完成，数据已更新",
                            payload={"network": network_str, "room_id": room_id},
                            source_module="ip_scan",
                            target_type="user",
                            target_id=user_id,
                        )
                except Exception:
                    logger.exception("IP扫描完成通知创建失败")
        except Exception as e:
            logger.error("异步网段扫描失败: %s (room=%d): %s", network_str, room_id, e)
            try:
                with app_ref.app_context():
                    from app.services.switch_events import emit_global_event
                    emit_global_event("scan_failed", {
                        "network": network_str,
                        "room_id": room_id,
                        "error": str(e)[:200],
                    })
            except Exception:
                logger.warning("异步网段扫描失败后 SSE 通知失败: network=%s, room_id=%d", network_str, room_id, exc_info=True)
            try:
                if not user_id:
                    logger.warning("IP扫描失败通知跳过：user_id 为空")
                else:
                    from app.services.notification_service import notification_service
                    notification_service.notify(
                        type=NotificationTypeCode.IP_SCAN_FAILED,
                        severity="warning",
                        title="网段扫描失败",
                        content=f"网段 {network_str} 扫描失败：{str(e)[:200]}",
                        payload={"network": network_str, "room_id": room_id},
                        source_module="ip_scan",
                        target_type="user",
                        target_id=user_id,
                    )
            except Exception:
                logger.exception("IP扫描失败通知创建失败")

    from app.utils.concurrency.task_executor import task_executor
    task_executor.submit("scan_ip", _async_scan)
    return APIResponse.success(message=f"网段 {network_str} 扫描已启动")


@router.route("/statistics", methods=["GET"])
@doc(summary="获取IP状态统计", tags=["IP"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def ip_statistics():
    """获取IP状态统计

    查询参数: room_id (可选), search (可选，IP地址或CIDR)
    返回各状态(在线/离线/封禁/未使用)的IP数量，支持按机房和搜索条件过滤。
    """
    room_id = request.args.get("room_id", type=int)
    search = request.args.get("search")

    repo = IPManagerRepository()
    stats = repo.get_status_statistics(room_id, search)
    return APIResponse.success(data=stats)
