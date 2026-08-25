# -*- coding: utf-8 -*-
"""
设备级端口/VLAN/LAG/连接 CRUD 路由

Blueprint 前缀 /api/devices，对所有交换机开放。

路由去重说明（Task 0）：
VLAN/LAG 的列表/创建/更新/成员编辑端点已由 app/api/device.py 在同前缀下以纯 DB
实现胜出（Werkzeug url_map 取首个注册命中：device_bp 先于 device_port_router 注册），
本文件只保留未被遮蔽的单条查询/删除端点（get_vlan / delete_vlan / get_lag）以及
物理端口与连接的 CRUD（device.py 无对应路径）。

守卫范围（Task 6，已据领域规则最终确认）：
- 仅**物理端口** CRUD（create/update/delete_port）对网管设备（has_ssh）拒绝——
  端口的存在/名称/状态是设备硬件的客观事实，网管设备只能由 SSH 扫描获取，
  手动在 DB 里"创建"端口等于编造未必真实的硬件，故禁止手动 CRUD，启用/关闭
  已存在端口也只走 /api/switch（SSH 同步）。
- VLAN/LAG（Eth-Trunk）是**逻辑配置**，不是"东西存不存在"的客观事实，而是
  "要不要这么配"的业务决策，逻辑记录层（device.py 及本文件 get_vlan/delete_vlan/
  get_lag）对所有设备（管/不管）开放自由 CRUD，不按物理端口规则拦截。
- 连接（create/update/delete_connection）对所有设备开放——连接为人工维护，
  非扫描派生，网管设备同样需要手动连线管理，故不受此守卫限制。

辅助函数 _reject_managed_or_400 仅用于上述物理端口三端点。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request

from app.api.base import APIResponse, ErrorCode
from app.services.port_management_service import port_management_service
from app.openapi.doc import doc, public
from app.utils.auth import login_required, permission_required
from app.utils.transactional import transactional
from app.persistence.vlan_repository import VLANRepository
from app.persistence.link_aggregation_repository import LinkAggregationRepository

logger = get_logger(__name__)

router = Blueprint("device_port", __name__, url_prefix="/api/devices")


def _reject_managed_or_400(device_id):
    """网管设备拒绝手动 DB 写操作

    网管设备端口由自动扫描获取，手动 CRUD 会与扫描结果冲突；
    网管设备应经 /api/switch 走 SSH 同步（启用/关闭等）。
    非网管设备端口为纯 DB 维护，允许这些写操作。
    """
    from app.persistence.switch_repo import SwitchRepository
    switch = SwitchRepository().find_by_device_id(device_id)
    if switch and switch.has_ssh:
        return APIResponse.error(
            "网管设备端口由扫描自动获取，禁止手动CRUD；请通过交换机管理页面操作",
            ErrorCode.VALIDATION_ERROR, 400,
        )
    return None




@router.route("/<int:device_id>/ports", methods=["POST"])
@doc(summary="手动创建端口", tags=["设备"], responses={200: "ApiResponse", 409: "ApiError"})
@login_required
@permission_required("device:update")
@transactional
def create_port(device_id):
    """手动创建端口"""
    guard = _reject_managed_or_400(device_id)
    if guard:
        return guard
    data = request.get_json()
    try:
        port = port_management_service.create_port(device_id, data)
        return APIResponse.success(data=port.to_dict(), message="端口创建成功")
    except Exception as e:
        logger.error("创建端口失败: %s", e)
        if "已存在" in str(e):
            return APIResponse.error(str(e), ErrorCode.DUPLICATE_ERROR, 409)
        raise


@router.route("/<int:device_id>/ports/<path:port_name>", methods=["GET"])
@doc(summary="获取端口详情", tags=["设备"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
def get_port(device_id, port_name):
    """获取端口详情"""
    from app.persistence.switch_port_repository import NetworkPortRepository
    repo = NetworkPortRepository()
    port = repo.find_port_by_name(device_id, port_name)
    if not port:
        return APIResponse.error(f"端口 {port_name} 不存在", ErrorCode.NOT_FOUND, 404)
    return APIResponse.success(data=port)


@router.route("/<int:device_id>/ports/<path:port_name>", methods=["PUT"])
@doc(summary="更新端口", tags=["设备"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("device:update")
@transactional
def update_port(device_id, port_name):
    """更新端口（白名单字段）"""
    guard = _reject_managed_or_400(device_id)
    if guard:
        return guard
    from app.persistence.switch_port_repository import NetworkPortRepository
    repo = NetworkPortRepository()
    port_data = repo.find_port_by_name(device_id, port_name)
    if not port_data:
        return APIResponse.error(f"端口 {port_name} 不存在", ErrorCode.NOT_FOUND, 404)

    data = request.get_json()
    try:
        port = port_management_service.update_port(port_data["id"], data)
        return APIResponse.success(data=port.to_dict(), message="端口更新成功")
    except Exception as e:
        logger.error("更新端口失败: %s", e)
        raise


@router.route("/<int:device_id>/ports/<path:port_name>", methods=["DELETE"])
@doc(summary="删除端口", tags=["设备"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("device:update")
@transactional
def delete_port(device_id, port_name):
    """删除端口"""
    guard = _reject_managed_or_400(device_id)
    if guard:
        return guard
    from app.persistence.switch_port_repository import NetworkPortRepository
    repo = NetworkPortRepository()
    port_data = repo.find_port_by_name(device_id, port_name)
    if not port_data:
        return APIResponse.error(f"端口 {port_name} 不存在", ErrorCode.NOT_FOUND, 404)

    try:
        port_management_service.delete_port(port_data["id"])
        return APIResponse.success(message="端口删除成功")
    except Exception as e:
        logger.error("删除端口失败: %s", e)
        raise




@router.route("/<int:device_id>/vlans/<int:vlan_db_id>", methods=["GET"])
@doc(summary="获取VLAN详情", tags=["设备"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
def get_vlan(device_id, vlan_db_id):
    """获取 VLAN 详情"""
    from app.services.vlan_service import VLANService
    service = VLANService(VLANRepository())
    vlan = service.get_by_id(vlan_db_id)
    if not vlan:
        return APIResponse.error(f"VLAN 不存在 (ID: {vlan_db_id})", ErrorCode.NOT_FOUND, 404)
    return APIResponse.success(data=vlan.to_dict())


@router.route("/<int:device_id>/vlans/<int:vlan_db_id>", methods=["DELETE"])
@doc(summary="删除VLAN", tags=["设备"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("switch:config")
@transactional
def delete_vlan(device_id, vlan_db_id):
    """删除 VLAN

    注意：VLAN/LAG 是逻辑配置（"要不要这么配"的业务决策），与物理端口
    是否真实存在无关；逻辑记录层（device.py 本文件）对所有设备（管/不管）
    开放自由 CRUD，不按物理端口"扫描获取、禁手动"的规则拦截。
    """
    try:
        port_management_service.delete_vlan(vlan_db_id)
        return APIResponse.success(message="VLAN 删除成功")
    except Exception as e:
        logger.error("删除 VLAN 失败: %s", e)
        raise




@router.route("/<int:device_id>/port-channels/<int:lag_id>", methods=["GET"])
@doc(summary="获取LAG详情", tags=["设备"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
def get_lag(device_id, lag_id):
    """获取 LAG 详情"""
    from app.services.link_aggregation_service import LinkAggregationService
    service = LinkAggregationService(LinkAggregationRepository())
    lag = service.repo.find_by_id(lag_id)
    if not lag:
        return APIResponse.error(f"LAG 不存在 (ID: {lag_id})", ErrorCode.NOT_FOUND, 404)
    return APIResponse.success(data=lag.to_dict())




@router.route("/<int:device_id>/connections", methods=["POST"])
@doc(summary="创建D2N连接", tags=["设备"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("device:update")
@transactional
def create_connection(device_id):
    """创建 D2N 连接"""
    data = request.get_json()
    try:
        conn_id = port_management_service.create_d2n_connection(device_id, data)
        return APIResponse.success(data={"id": conn_id}, message="连接创建成功")
    except Exception as e:
        logger.error("创建连接失败: %s", e)
        raise


@router.route("/<int:device_id>/connections/<int:conn_id>", methods=["PUT"])
@doc(summary="更新连接", tags=["设备"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("device:update")
@transactional
def update_connection(device_id, conn_id):
    """更新连接"""
    from app.services.device_connection_service import device_connection_service
    data = request.get_json()
    try:
        result = device_connection_service.update_connection(conn_id, data)
        return APIResponse.success(data=result, message="连接更新成功")
    except Exception as e:
        logger.error("更新连接失败: %s", e)
        raise


@router.route("/<int:device_id>/connections/<int:conn_id>", methods=["DELETE"])
@doc(summary="删除连接", tags=["设备"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("device:update")
@transactional
def delete_connection(device_id, conn_id):
    """删除连接"""
    conn_type = request.args.get("type", "d2n")
    try:
        result = port_management_service.delete_connection(conn_id, conn_type)
        return APIResponse.success(message="连接删除成功")
    except Exception as e:
        logger.error("删除连接失败: %s", e)
        raise




@router.route("/<int:device_id>/port-sync-enabled", methods=["GET"])
@doc(summary="查询设备端口同步开关", tags=["设备"], responses={200: "DevicePortSyncEnabledResponse"})
@login_required
@permission_required("device:view")
def get_port_sync_enabled(device_id: int):
    """返回设备级端口同步开关状态。

    Returns:
        data: {
            "port_sync_enabled": bool | null,  # None=跟随全局
            "global_enabled": bool,            # 全局开关当前值
            "effective_enabled": bool,         # 实际生效值
        }
    """
    from extensions import db
    from app.models.device_switch_ext import DeviceSwitchExt
    from app.services.monitoring.dynamic_config import MonitorDynamicConfig

    ext = db.session.query(DeviceSwitchExt).filter_by(device_id=device_id).first()
    port_sync_enabled = ext.port_sync_enabled if ext else None
    global_enabled = bool(MonitorDynamicConfig.get("MONITOR_NON_MANAGED_PORT_SYNC"))
    effective = bool(port_sync_enabled) if port_sync_enabled is not None else global_enabled
    return APIResponse.success(data={
        "port_sync_enabled": port_sync_enabled,
        "global_enabled": global_enabled,
        "effective_enabled": effective,
    })


@router.route("/<int:device_id>/port-sync-enabled", methods=["PUT"])
@doc(summary="设置设备端口同步开关", tags=["设备"], responses={200: "DevicePortSyncEnabledUpdateResponse"})
@login_required
@permission_required("device:update")
@transactional
def put_port_sync_enabled(device_id: int):
    """设置设备级端口同步开关。

    Body:
        {"port_sync_enabled": bool | null}  # null=跟随全局
    """
    from extensions import db
    from app.models.device_switch_ext import DeviceSwitchExt
    from app.models.device import Device

    body = request.get_json(silent=True) or {}
    value = body.get("port_sync_enabled")
    if value is not None and not isinstance(value, bool):
        from app.exceptions.validation import ValidationError
        raise ValidationError("port_sync_enabled 必须为 bool 或 null")

    device = db.session.query(Device).filter_by(id=device_id).first()
    if not device:
        from app.exceptions.business import BusinessLogicError
        raise BusinessLogicError("设备不存在", status_code=404)

    ext = db.session.query(DeviceSwitchExt).filter_by(device_id=device_id).first()
    if ext is None:
        ext = DeviceSwitchExt(device_id=device_id)
        db.session.add(ext)
    ext.port_sync_enabled = value
    db.session.flush()
    return APIResponse.success(data={"port_sync_enabled": value})

