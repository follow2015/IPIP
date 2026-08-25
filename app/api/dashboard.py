# -*- coding: utf-8 -*-
"""
仪表盘API

提供系统概览和统计数据。
"""
from app.utils.logging import get_logger
from flask import Blueprint
from datetime import datetime

from app.persistence.factory import create_repository
from app.persistence.room_repository import RoomRepository
from app.persistence.cabinet_repository import CabinetRepository
from app.persistence.device_repository import DeviceRepository
from app.persistence.customer_repository import CustomerRepository
from app.core.enums import CustomerStatus
from app.persistence.ip_repositories import IPManagerRepository, IPNetworkRepository
from app.persistence.user_log_repository import UserLogRepository
from app.openapi.doc import doc, public
from app.utils.auth import login_required, permission_required
from app.api.base import APIResponse

logger = get_logger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/stats", methods=["GET"])
@doc(summary="获取仪表盘统计数据", tags=["仪表盘"], responses={200: "DashboardStatsResponse", 401: "ApiError"})
@login_required
def get_stats():
    """获取仪表盘统计数据

    Returns:
        JSON响应，包含各项统计数据，含设备/机柜按状态码的完整分布
    """
    room_repo = create_repository(RoomRepository)
    cabinet_repo = create_repository(CabinetRepository)
    device_repo = create_repository(DeviceRepository)
    customer_repo = create_repository(CustomerRepository)
    ip_manager_repo = create_repository(IPManagerRepository)
    ip_network_repo = create_repository(IPNetworkRepository)

    active_rooms = room_repo.count(filters={"status": 0})

    total_cabinets = cabinet_repo.count(filters={"status": [1, 2, 3, 4]})
    available_cabinets = cabinet_repo.count(filters={"status": 1})
    occupied_cabinets = cabinet_repo.count(filters={"status": 2})
    maintenance_cabinets = cabinet_repo.count(filters={"status": 3})
    reserved_cabinets = cabinet_repo.count(filters={"status": 4})
    disabled_cabinets = cabinet_repo.count(filters={"status": 0})

    total_devices = device_repo.count()
    total_customers = customer_repo.count(filters={"customer_status": CustomerStatus.ACTIVE})

    from app.core.enums import DeviceStatus
    device_status_distribution = {}
    for status_code in range(8):
        device_status_distribution[str(status_code)] = device_repo.count_by_status(status_code)

    online_devices = device_status_distribution.get(str(DeviceStatus.ONLINE), 0)
    offline_devices = device_status_distribution.get(str(DeviceStatus.OFFLINE), 0)

    total_switches = device_repo.count_switches()

    ip_stats = ip_manager_repo.get_status_statistics()
    total_ips = ip_stats['total']
    active_ips = ip_stats['active']
    inactive_ips = ip_stats['inactive']
    blocked_ips = ip_stats['blocked']
    unused_ips = ip_stats['unused']

    net_type_stats = ip_manager_repo.get_network_type_statistics()
    private_stats = net_type_stats["private"]
    public_stats = net_type_stats["public"]

    total_networks = ip_network_repo.count()

    device_online_rate = round((online_devices / total_devices * 100), 1) if total_devices > 0 else 0
    cabinet_utilization = round((occupied_cabinets / total_cabinets * 100), 1) if total_cabinets > 0 else 0
    ip_utilization = round((active_ips / total_ips * 100), 1) if total_ips > 0 else 0

    data = {
        "rooms": {
            "total": active_rooms,
            "active": active_rooms
        },
        "cabinets": {
            "total": total_cabinets,
            "occupied": occupied_cabinets,
            "available": available_cabinets,
            "maintenance": maintenance_cabinets,
            "reserved": reserved_cabinets,
            "disabled": disabled_cabinets,
            "utilization": cabinet_utilization
        },
        "devices": {
            "total": total_devices,
            "online": online_devices,
            "offline": offline_devices,
            "status_distribution": device_status_distribution,
        },
        "networks": {
            "segments": total_networks,
            "ips_total": total_ips,
            "ips_used": active_ips,
            "ips_inactive": inactive_ips,
            "ips_blocked": blocked_ips,
            "ips_available": unused_ips,
            "switches": total_switches,
            "ports_total": 0,
            "ports_used": 0,
            "public_ips": public_stats,
            "private_ips": private_stats,
        },
        "customers": {
            "total": total_customers,
            "active": total_customers,
            "inactive": 0
        },
        "switches": {
            "total": total_switches
        },
        "percentages": {
            "device_online_rate": device_online_rate,
            "cabinet_utilization": cabinet_utilization,
            "ip_utilization": ip_utilization,
            "port_utilization": 0
        }
    }

    return APIResponse.success(data=data)


@dashboard_bp.route("/activities", methods=["GET"])
@doc(summary="获取最近活动记录", tags=["仪表盘"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def get_activities():
    """获取最近活动记录（基于 UserLog 登录日志）

    Query Params:
        limit: 返回条数，默认 20，最大 50

    Returns:
        JSON响应，包含活动记录列表
    """
    from flask import request

    try:
        limit = min(int(request.args.get("limit", 20)), 50)
    except (ValueError, TypeError):
        limit = 20

    try:
        user_log_repo = UserLogRepository()
        logs = user_log_repo.get_recent_logs(days=30, limit=limit)

        type_style = {
            "web": {"icon": "GlobalOutlined", "color": "blue"},
            "wechat": {"icon": "WechatOutlined", "color": "green"},
            "api": {"icon": "ApiOutlined", "color": "orange"},
            "mobile": {"icon": "MobileOutlined", "color": "purple"},
            "token": {"icon": "KeyOutlined", "color": "cyan"},
        }

        from app.models.user import User
        user_ids = list({log.user_id for log in logs})
        user_map = {}
        if user_ids:
            users = User.query.filter(User.id.in_(user_ids)).all()
            user_map = {u.id: u.username for u in users}

        activities = []
        for log in logs:
            style = type_style.get(log.login_type or "web", {"icon": "LoginOutlined", "color": "default"})
            activities.append({
                "id": log.id,
                "title": f"{user_map.get(log.user_id, '未知用户')} 登录系统",
                "description": f"通过 {log.login_type or 'web'} 方式登录，IP: {log.login_ip or '未知'}",
                "user": user_map.get(log.user_id, "未知"),
                "timestamp": log.login_time.isoformat() if log.login_time else None,
                "icon": style["icon"],
                "color": style["color"],
            })

        return APIResponse.success(data={"activities": activities, "total": len(activities)})

    except Exception as e:
        logger.error(f"获取活动记录失败: {e}")
        return APIResponse.success(data={"activities": [], "total": 0})


@dashboard_bp.route("/system-status", methods=["GET"])
@doc(summary="获取系统状态", tags=["仪表盘"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def get_system_status():
    """获取系统状态"""
    try:
        try:
            import psutil
        except ImportError:
            return APIResponse.success(data={
                "overall": "warning",
                "performance": {
                    "cpu": 0, "memory": 0, "disk": 0,
                    "memory_total": 0, "memory_used": 0,
                    "disk_total": 0, "disk_used": 0
                },
                "services": {
                    "database": "running",
                    "api": "running",
                    "frontend": "running"
                },
                "lastUpdated": datetime.now().isoformat(),
                "error": "psutil library not installed"
            })

        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
        except Exception:
            raise

        overall = "healthy"
        if cpu_percent > 80 or memory.percent > 85 or disk.percent > 90:
            overall = "critical"
        elif cpu_percent > 60 or memory.percent > 70 or disk.percent > 80:
            overall = "warning"

        data = {
            "overall": overall,
            "performance": {
                "cpu": round(cpu_percent, 2),
                "memory": round(memory.percent, 2),
                "disk": round(disk.percent, 2),
                "memory_total": round(memory.total / (1024**3), 2),
                "memory_used": round(memory.used / (1024**3), 2),
                "disk_total": round(disk.total / (1024**3), 2),
                "disk_used": round(disk.used / (1024**3), 2)
            },
            "services": {
                "database": "running",
                "api": "running",
                "frontend": "running"
            },
            "lastUpdated": datetime.now().isoformat()
        }

        return APIResponse.success(data=data)

    except Exception as e:
        logger.error(f"获取系统状态失败: {str(e)}", exc_info=True)

        data = {
            "overall": "unknown",
            "performance": {
                "cpu": 0, "memory": 0, "disk": 0,
                "memory_total": 0, "memory_used": 0,
                "disk_total": 0, "disk_used": 0
            },
            "services": {
                "database": "unknown",
                "api": "unknown",
                "frontend": "unknown"
            },
            "lastUpdated": datetime.now().isoformat(),
            "error": str(e)
        }

        return APIResponse.success(data=data)


@dashboard_bp.route("/alerts", methods=["GET"])
@doc(summary="获取系统警告列表", tags=["仪表盘"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def get_alerts():
    """获取系统警告列表

    Returns:
        JSON响应，包含警告列表
    """
    data = {
        "alerts": [],
        "total": 0
    }

    return APIResponse.success(data=data)


@dashboard_bp.route("", methods=["GET"])
@dashboard_bp.route("/", methods=["GET"])
@doc(summary="获取仪表盘统计数据（兼容旧接口）", tags=["仪表盘"], responses={200: "DashboardStatsResponse", 401: "ApiError"})
@login_required
def get_dashboard_stats():
    """获取仪表盘统计数据（兼容旧接口）"""
    return get_stats()


@dashboard_bp.route("/statistics", methods=["GET"])
@doc(summary="获取系统统计信息", tags=["仪表盘"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@permission_required("system:stats")
def get_statistics():
    """获取系统统计信息

    统计IP状态、机房和交换机的相关信息。
    """
    try:
        from app.services.network_service import NetworkService
        from app.persistence.network_repo import NetworkRepository
        from app.persistence.ip_repositories import IPManagerRepository
        network_svc = NetworkService(NetworkRepository(), IPManagerRepository())
        stats = network_svc.get_statistics()

        return APIResponse.success(data={'data': stats})
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        return APIResponse.error(str(e), status_code=500)
