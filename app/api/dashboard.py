# -*- coding: utf-8 -*-
"""
仪表盘API

提供系统概览和统计数据。
"""
import json
import time
from typing import Any, Dict, Optional

from app.utils.logging import get_logger
from flask import Blueprint
from app.utils.time_utils import now_utc_naive

from app.persistence.factory import create_repository
from app.persistence.room_repository import RoomRepository
from app.persistence.cabinet_repository import CabinetRepository
from app.persistence.device_repository import DeviceRepository
from app.persistence.customer_repository import CustomerRepository
from app.core.enums import CustomerStatus
from app.persistence.ip_repositories import IPManagerRepository, IPNetworkRepository
from app.persistence.user_log_repository import UserLogRepository
from app.openapi.doc import doc
from app.services.auth import login_required, permission_required
from app.api.base import APIResponse

logger = get_logger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/stats", methods=["GET"])
@doc(summary="获取仪表盘统计数据", tags=["仪表盘"], responses={200: "DashboardStatsResponse", 401: "ApiError"})
@login_required
@permission_required("system:stats")
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
@permission_required("system:stats")
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

    except Exception as e:  # noqa: BLE001 -- 活动记录查询失败降级为空列表：仪表盘不得因单块数据失败整体不可用
        logger.error(f"获取活动记录失败: {e}")
        return APIResponse.success(data={"activities": [], "total": 0})


def _probe_components() -> Dict[str, dict]:
    """真实探测各后端服务组件健康,替换原硬编码 services。

    每项独立 try/except + 计时,失败降级 unknown,不拖垮 dashboard 端点。
    返回 {name: {"status": running|degraded|down|unknown, ...指标}}。
    """
    services: Dict[str, dict] = {}

    services["api"] = {"status": "running"}

    try:
        from extensions import db
        from sqlalchemy import text

        start = time.perf_counter()
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        services["database"] = {
            "status": "running",
            "latency_ms": round((time.perf_counter() - start) * 1000, 1),
        }
    except Exception as exc:  # noqa: BLE001 -- 探测失败降级,不冒泡
        logger.warning("数据库探测失败: %s", exc)
        services["database"] = {"status": "down", "message": str(exc)[:200]}

    try:
        from app.utils.redis_client import get_redis_client

        client = get_redis_client()
        start = time.perf_counter()
        ok = bool(client and client.ping())
        latency = round((time.perf_counter() - start) * 1000, 1)
        services["redis"] = (
            {"status": "running", "latency_ms": latency}
            if ok
            else {"status": "down", "message": "Redis ping 失败"}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis 探测失败: %s", exc)
        services["redis"] = {"status": "down", "message": str(exc)[:200]}

    try:
        from app.services.monitoring.heartbeat import interval_seconds, read_heartbeats

        stale_after = max(interval_seconds() * 3, 60)
        for name in ("gateway", "monitor"):
            try:
                state = read_heartbeats([name]).get(name, {})
                if not state.get("checked"):
                    services[name] = {"status": "unknown", "message": "心跳未读到(Redis 可能不可用)"}
                elif not state.get("alive"):
                    services[name] = {"status": "down", "age_seconds": state.get("age_seconds")}
                elif state.get("age_seconds") is not None and state["age_seconds"] > stale_after:
                    services[name] = {"status": "degraded", "age_seconds": state.get("age_seconds")}
                else:
                    services[name] = {"status": "running", "age_seconds": state.get("age_seconds")}
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s 心跳读取失败: %s", name, exc)
                services[name] = {"status": "unknown", "message": str(exc)[:200]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("心跳模块加载失败: %s", exc)
        for name in ("gateway", "monitor"):
            services.setdefault(name, {"status": "unknown", "message": str(exc)[:200]})

    try:
        from app.celery_app import celery

        replies = celery.control.ping(timeout=3)
        workers = len(replies) if isinstance(replies, list) else 0
        services["celery"] = (
            {"status": "running", "workers": workers}
            if workers > 0
            else {"status": "down", "workers": 0}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Celery 探测失败: %s", exc)
        services["celery"] = {"status": "unknown", "message": str(exc)[:200]}

    return services


def _recompute_overall(data: Dict[str, Any]) -> None:
    """把组件健康并入整体状态判定(原地修改 data["overall"])。

    规则:db/redis 挂 → critical;gateway/monitor/celery 降级或失联,或主机已 warning
    → warning;否则保留主机阈值推导的 healthy/warning/critical。
    """
    comp = data.get("services") or {}
    db_down = comp.get("database", {}).get("status") == "down"
    redis_down = comp.get("redis", {}).get("status") == "down"
    comp_abnormal = any(
        comp.get(n, {}).get("status") in ("down", "degraded")
        for n in ("gateway", "monitor", "celery")
    )
    if db_down or redis_down:
        data["overall"] = "critical"
    elif comp_abnormal or data.get("overall") == "warning":
        data["overall"] = "warning"


_STATUS_CACHE_KEY = "ipip:dashboard:system-status"
_STATUS_CACHE_TTL = 10  # 秒；系统状态无需秒级精度，10s 粒度对大屏足够


def _read_status_cache() -> Optional[Dict[str, Any]]:
    """读缓存；未命中/Redis 不可用/解析失败一律返回 None 走实时探测。"""
    try:
        from app.utils.redis_client import get_redis_client

        client = get_redis_client()
        if client is None:
            return None
        raw = client.get(_STATUS_CACHE_KEY)
        if not raw:
            return None
        cached = json.loads(raw)
        return cached if isinstance(cached, dict) else None
    except Exception as exc:  # noqa: BLE001 -- 缓存是优化路径，失败必须静默降级
        logger.warning("系统状态缓存读取失败，降级为实时探测: %s", exc)
        return None


def _write_status_cache(data: Dict[str, Any]) -> None:
    try:
        from app.utils.redis_client import get_redis_client

        client = get_redis_client()
        if client is None:
            return
        client.set(_STATUS_CACHE_KEY, json.dumps(data), ex=_STATUS_CACHE_TTL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("系统状态缓存写入失败（忽略）: %s", exc)


@dashboard_bp.route("/system-status", methods=["GET"])
@doc(summary="获取系统状态", tags=["仪表盘"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@permission_required("system:stats")
def get_system_status():
    """获取系统状态(主机资源 + 后端服务组件真实健康)"""
    cached = _read_status_cache()
    if cached is not None:
        return APIResponse.success(data=cached)

    try:
        try:
            import psutil
        except ImportError:
            psutil = None

        services = _probe_components()
        if psutil is None:
            degraded = {
                "overall": "warning",
                "performance": {
                    "cpu": 0, "memory": 0, "disk": 0,
                    "memory_total": 0, "memory_used": 0,
                    "disk_total": 0, "disk_used": 0
                },
                "services": services,
                "lastUpdated": now_utc_naive().isoformat(),
                "error": "psutil library not installed"
            }
            _write_status_cache(degraded)
            return APIResponse.success(data=degraded)

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
            "services": services,
            "lastUpdated": now_utc_naive().isoformat()
        }

        _recompute_overall(data)
        _write_status_cache(data)

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
            "services": _probe_components(),
            "lastUpdated": now_utc_naive().isoformat(),
            "error": str(e)
        }

        return APIResponse.success(data=data)


@dashboard_bp.route("", methods=["GET"])
@dashboard_bp.route("/", methods=["GET"])
@doc(summary="获取仪表盘统计数据（兼容旧接口）", tags=["仪表盘"], responses={200: "DashboardStatsResponse", 401: "ApiError"})
@login_required
@permission_required("system:stats")
def get_dashboard_stats():
    """获取仪表盘统计数据（兼容旧接口）"""
    return get_stats()
