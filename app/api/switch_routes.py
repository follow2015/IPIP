# -*- coding: utf-8 -*-
"""
交换机 CRUD API 路由

提供交换机管理、端口查询、扫描触发等接口。
"""
from app.utils.logging import get_logger
import time

from flask import Blueprint, g, request

from app.api.base import APIResponse, ErrorCode, api_exception_handler
from app.openapi.doc import doc, public
from app.persistence.switch_repo import SwitchRepository
from app.persistence.switch_port_repository import NetworkPortRepository
from app.persistence.customer_repository import CustomerRepository
from app.persistence.room_repository import RoomRepository
from app.persistence.vlan_repository import VLANRepository
from app.persistence.link_aggregation_repository import LinkAggregationRepository
from app.persistence.network_connection_repository import NetworkConnectionRepository
from app.persistence.switch_ext_repository import SwitchExtRepository
from app.services.network_scanner_service import NetworkScannerService
from app.services.switch_info_service import SwitchInfoService
from app.services.switch_config_service import SwitchConfigService
from app.utils.auth import login_required, permission_required
from extensions import db
from app.core.enums import NotificationTypeCode, SwitchDeviceTypeCode
from app.utils.transactional import transactional

logger = get_logger(__name__)

router = Blueprint("switch", __name__, url_prefix="/api/switch")



def _notify_port_action_result(user_id, switch_device_id, port, action, *, success, message="", error=""):
    """端口操作结果创建站内信通知（不阻塞主流程）"""
    if not user_id:
        logger.warning("端口操作结果通知跳过：user_id 为空")
        return
    try:
        from app.services.notification_service import notification_service
        action_labels = {
            "enable_port": "启用端口", "disable_port": "关闭端口",
            "update_port_info": "修改端口信息", "set_port_speed": "设置端口限速",
            "set_port_vlan": "配置VLAN", "set_port_ip": "配置IP",
            "delete_port_ip": "删除IP", "clear_port_config": "清除端口配置",
            "delete_interface": "删除接口", "add_port_to_trunk": "加入链路聚合",
            "delete_trunk": "删除链路聚合", "create_port_channel": "创建链路聚合",
            "remove_port_from_channel": "移除链路聚合成员", "delete_vlan": "删除VLAN",
            "cancel_port_speed": "取消端口限速",
        }
        label = action_labels.get(action, action)
        if success:
            notification_service.notify(
                type=f"port_action_{action}",
                severity="info",
                title=f"{label}成功",
                content=f"端口 {port} {label}成功" + (f"：{message}" if message else ""),
                payload={"device_id": switch_device_id, "port": port, "action": action},
                source_module="switch_config",
                target_type="user",
                target_id=user_id,
                channels=("inbox",),
            )
        else:
            notification_service.notify(
                type=f"port_action_{action}",
                severity="warning",
                title=f"{label}失败",
                content=f"端口 {port} {label}失败" + (f"：{error}" if error else ""),
                payload={"device_id": switch_device_id, "port": port, "action": action},
                source_module="switch_config",
                target_type="user",
                target_id=user_id,
                channels=("inbox",),
            )
    except Exception:
        logger.exception("端口操作结果通知创建失败（不影响主流程）")


def _notify_async_result(user_id, action_type, label, *, success, error="", device_id=None):
    """异步操作结果创建站内信通知（不阻塞主流程）"""
    if not user_id:
        logger.warning("异步操作结果通知跳过：user_id 为空")
        return
    try:
        from app.services.notification_service import notification_service
        device_label = ""
        if device_id:
            try:
                from app.models.device import Device
                dev = Device.query.get(device_id)
                if dev and dev.management_ip:
                    device_label = dev.management_ip
                else:
                    device_label = str(device_id)
            except Exception:
                device_label = str(device_id)
        if success:
            notification_service.notify(
                type=f"async_{action_type}",
                severity="info",
                title=f"{label}完成",
                content=f"{label}已完成" + (f"，设备: {device_label}" if device_label else ""),
                payload={"device_id": device_id, "action": action_type} if device_id else {"action": action_type},
                source_module="switch",
                target_type="user",
                target_id=user_id,
                channels=("inbox",),
            )
        else:
            notification_service.notify(
                type=f"async_{action_type}",
                severity="warning",
                title=f"{label}失败",
                content=f"{label}失败" + (f"：{error}" if error else ""),
                payload={"device_id": device_id, "action": action_type, "error": error} if device_id else {"action": action_type, "error": error},
                source_module="switch",
                target_type="user",
                target_id=user_id,
                channels=("inbox",),
            )
    except Exception:
        logger.exception("异步操作结果通知创建失败（不影响主流程）")




def _find_switch_or_404(device_id):
    """查找交换机，不存在则返回 404 APIResponse

    统一使用 device_id（devices.id）作为交换机标识。
    """
    repo = SwitchRepository()
    switch = repo.find_by_device_id(device_id)
    if not switch:
        return None, APIResponse.error(f"交换机 {device_id} 不存在", ErrorCode.NOT_FOUND, 404)
    return switch, None


def _build_customer_map(ports):
    """批量查询端口关联的 customer_name，返回 {customer_id: customer_name}"""
    customer_ids = {p.customer_id for p in ports if p.customer_id}
    if not customer_ids:
        return {}
    return CustomerRepository().find_id_name_map_by_ids(customer_ids)


def _map_port_fields(ports, adapter, customer_map, device_id=None):
    """端口字段映射：对齐前端 SwitchPort 类型定义

    字段重命名：mac→mac_address, description→notes
    补充字段：customer_name, port_info, max_speed, ip_list
    V2.0: 保留 port_name/port_type 原字段名（对齐 network_ports 表）
    """
    port_ip_map = {}
    if device_id is not None and ports:
        port_names = [p.port_name for p in ports if p.port_name]
        ip_rows = NetworkPortRepository().find_port_ips_by_device_and_names(device_id, port_names)
        for ip_row in ip_rows:
            port_ip_map.setdefault(ip_row.port_name, []).append(ip_row.to_dict())

    port_list = []
    for p in ports:
        item = p.to_dict()
        item.pop("port_number", None)
        item["customer_name"] = customer_map.get(p.customer_id)
        if adapter:
            item["max_speed"] = adapter.get_port_max_speed(item.get("port_name", ""))
        item["ip_list"] = port_ip_map.get(p.port_name, [])
        port_list.append(item)
    return port_list


def _map_switch_data(switch, ports):
    """交换机字段映射：对齐前端 Switch 类型定义

    字段重命名：ip→ip_address
    补充字段：name, device_model, room_name, mac_address(数组)
    V2.0: 保留 switch_role（不再改回 status），补充 device_id/layer/has_ssh/uplink_device_id
    V2.1: 聚合 SwitchStatusCache 的 device_version/device_uptime + Device.serial_number 作为 device_serial
    """

    switch_data = switch.to_dict(exclude=["password"])
    if switch.device:
        switch_data["name"] = switch.device.device_name
        switch_data["device_model"] = switch.device.device_model
        switch_data["serial_number"] = switch.device.serial_number
        switch_data["hostname"] = switch.device.hostname
        switch_data["switch_role"] = switch.device.switch_role
        switch_data["layer"] = switch.device.layer
        switch_data["port_num"] = switch.device.port_num
        if switch.device.switch_ext:
            switch_data["uplink_device_id"] = switch.device.switch_ext.uplink_device_id
            switch_data["core_device_id"] = switch.device.switch_ext.core_device_id
            if switch.device.switch_ext.uplink_device:
                switch_data["uplink_device_name"] = switch.device.switch_ext.uplink_device.device_name
            if switch.device.switch_ext.core_device:
                switch_data["core_device_name"] = switch.device.switch_ext.core_device.device_name
            switch_data["uplink_port_ids"] = switch.device.switch_ext.uplink_port_ids
            if switch.device.switch_ext.uplink_port_ids:
                uplink_pids = switch.device.switch_ext.uplink_port_ids
                port_rows = NetworkPortRepository().find_by_ids_orm(uplink_pids)
                port_map = {p.id: p.port_name for p in port_rows}
                switch_data["uplink_port_names"] = [port_map.get(pid, f"(ID:{pid})") for pid in uplink_pids]
            else:
                switch_data["uplink_port_names"] = None
        if switch.device.switch_ext and switch.device.switch_ext.uplink_port_ids:
            uplink_port_ids = switch.device.switch_ext.uplink_port_ids
            conns = NetworkConnectionRepository().find_by_port_ids_orm(uplink_port_ids)
            port_to_peer: dict = {}
            for conn in conns:
                if conn.local_port_id in set(uplink_port_ids):
                    port_to_peer[conn.local_port_id] = conn.peer_port.port_name if conn.peer_port else f"(ID:{conn.peer_port_id})"
                if conn.peer_port_id in set(uplink_port_ids):
                    port_to_peer[conn.peer_port_id] = conn.local_port.port_name if conn.local_port else f"(ID:{conn.local_port_id})"
            peer_names = [port_to_peer.get(pid, f"(ID:{pid})") for pid in uplink_port_ids]
            switch_data["peer_port_names"] = peer_names if peer_names else None
        else:
            switch_data["peer_port_names"] = None
        if switch.device.status_cache:
            switch_data["device_version"] = switch.device.status_cache.device_version
            switch_data["device_uptime"] = switch.device.status_cache.device_uptime
        switch_data["device_serial"] = switch.device.serial_number
        if switch.device.cabinet:
            switch_data["room_id"] = switch.device.cabinet.room_id
            if switch.device.cabinet.room:
                switch_data["room_name"] = switch.device.cabinet.room.name
    switch_data["ip_address"] = switch_data.pop("ip", None)
    mac_set = {p.mac for p in ports if p.mac}
    switch_data["mac_address"] = sorted(mac_set) if mac_set else []
    return switch_data




@router.route("/list", methods=["GET"])
@doc(summary="查询交换机列表（分页）", tags=["交换机"], responses={200: "SwitchResponse", 401: "ApiError"})
@login_required
def list_switches():
    """查询交换机列表（分页）

    支持按机房、状态、设备类型过滤，支持关键词搜索。
    字段映射对齐前端 Switch 类型：ip→ip_address, 补充 name/device_model/room_name。
    """
    room_id = request.args.get("room_id", type=int)
    cabinet_id = request.args.get("cabinet_id", type=int)
    switch_role = request.args.get("switch_role", type=int)
    search = request.args.get("search")
    device_type = request.args.get("device_type")
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("per_page", 20, type=int)

    repo = SwitchRepository()
    result = repo.find_by_filters(
        room_id=room_id, cabinet_id=cabinet_id, switch_role=switch_role, search=search,
        device_type=device_type, page=page, page_size=page_size,
    )

    return APIResponse.paginated(
        data=result["items"],
        page=result["page"],
        per_page=result["page_size"],
        total=result["total"],
        message="获取交换机列表成功",
    )


@router.route("/<int:device_id>", methods=["GET"])
@doc(summary="获取交换机详情", tags=["交换机"], responses={200: "SwitchResponse", 404: "ApiError"})
@login_required
def get_switch(device_id):
    """获取交换机详情包含端口列表

    返回结构对齐前端 SwitchWithPortsResponse 类型定义：
    - switch: 补充 name/ip_address/status/device_model/room_name/mac_address(数组)
    - ports:  字段映射 port_name→port_number, mac→mac_address, description→notes, port_type→type
              补充 customer_name, max_speed

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    from app.adapters.adapter_factory import get_adapter

    switch, err = _find_switch_or_404(device_id)
    if err:
        return err

    port_repo = NetworkPortRepository()
    ports = port_repo.get_by_device(switch.device_id)

    switch_data = _map_switch_data(switch, ports)
    adapter = get_adapter(switch.device_type) if switch.device_type else None
    customer_map = _build_customer_map(ports)
    port_list = _map_port_fields(ports, adapter, customer_map, device_id=switch.device_id)

    return APIResponse.success({"switch": switch_data, "ports": port_list})


@router.route("/", methods=["POST"])
@doc(summary="创建交换机", tags=["交换机"], responses={200: "SwitchResponse", 409: "ApiError", 500: "ApiError"})
@permission_required("switch:create")
@api_exception_handler
@transactional
def create_switch():
    """创建交换机

    请求体: {"name": "...", "ip": "...", "port": 22, ...}
    字段映射：name→Device.device_name
    """
    data = request.get_json()
    repo = SwitchRepository()

    device_name = data.pop("name", None)
    device_model = data.pop("device_model", None)

    cabinet_id = data.pop("cabinet_id", None)
    u_position = data.pop("u_position", None)
    height_u = data.pop("height_u", None)
    device_status = data.pop("status", None)
    customer_id = data.pop("customer_id", None)

    uplink_device_id = data.pop("uplink_device_id", None)
    core_device_id = data.pop("core_device_id", None)
    uplink_port_ids = data.pop("uplink_port_ids", None)
    port_num = data.pop("port_num", None)
    hostname = data.pop("hostname", None)

    data.pop("ip_address", None)
    data.pop("room_name", None)

    if repo.name_ip_exists(device_name or "", data.get("ip", "")):
        return APIResponse.error("交换机名称或IP已存在", ErrorCode.DUPLICATE_ERROR, 409)

    device_data = {
        "device_name": device_name or data.get("ip", ""),
        "device_type": "network",
        "device_model": device_model,
        "cabinet_id": cabinet_id,
        "u_position": u_position,
        "height_u": height_u,
        "status": device_status,
        "customer_id": customer_id,
    }

    ext_data = None
    if any(v is not None for v in [uplink_device_id, core_device_id, uplink_port_ids, port_num, hostname]):
        ext_data = {
            "uplink_device_id": uplink_device_id,
            "core_device_id": core_device_id,
            "uplink_port_ids": uplink_port_ids,
            "port_num": port_num,
            "hostname": hostname,
        }

    switch = repo.create_switch_with_device(
        device_data=device_data,
        switch_data=data,
        ext_data=ext_data,
    )
    device = switch.device

    result = switch.to_dict(exclude=["password"])
    result["ip_address"] = result.pop("ip", None)
    if switch.device:
        result["name"] = switch.device.device_name
        result["device_model"] = switch.device.device_model
        result["switch_role"] = switch.device.switch_role
        result["layer"] = switch.device.layer
        result["uplink_device_id"] = switch.device.uplink_device_id
        result["core_device_id"] = switch.device.core_device_id
        result["port_num"] = switch.device.port_num
        if switch.device.cabinet:
            result["room_id"] = switch.device.cabinet.room_id
            if switch.device.cabinet.room:
                result["room_name"] = switch.device.cabinet.room.name

    return APIResponse.success(
        data=result,
        message="创建成功",
    )


@router.route("/<int:device_id>", methods=["PUT"])
@doc(summary="更新交换机信息", tags=["交换机"], responses={200: "SwitchResponse", 404: "ApiError", 409: "ApiError", 500: "ApiError"})
@permission_required("switch:update")
@api_exception_handler
@transactional
def update_switch(device_id):
    """更新交换机信息

    请求体: 需要更新的字段
    字段映射：name→Device.device_name

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    data = request.get_json()
    repo = SwitchRepository()

    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    device_name = data.pop("name", None)
    device_model = data.pop("device_model", None)
    layer = data.pop("layer", None)
    switch_role = data.pop("switch_role", None)
    uplink_device_id = data.pop("uplink_device_id", None)
    core_device_id = data.pop("core_device_id", None)
    uplink_port_ids = data.pop("uplink_port_ids", None)
    port_num = data.pop("port_num", None)
    hostname = data.pop("hostname", None)

    data.pop("ip_address", None)
    data.pop("room_name", None)

    if "password" in data and not data["password"]:
        del data["password"]

    if repo.name_ip_exists(
        device_name or "", data.get("ip", ""), exclude_id=switch.id
    ):
        return APIResponse.error("交换机名称或IP已存在", ErrorCode.DUPLICATE_ERROR, 409)

    switch = repo.update(switch.id, data)
    if not switch:
        return APIResponse.error(f"交换机 {device_id} 不存在", ErrorCode.NOT_FOUND, 404)

    if switch.device:
        updated = False
        if device_name:
            switch.device.device_name = device_name
            updated = True
        if device_model is not None:
            switch.device.device_model = device_model
            updated = True
        if layer is not None:
            switch.device.layer = layer
            updated = True
        if switch_role is not None:
            switch.device.switch_role = switch_role
            updated = True
        if uplink_device_id is not None:
            switch.device.uplink_device_id = uplink_device_id
            updated = True
        if core_device_id is not None:
            switch.device.core_device_id = core_device_id
            updated = True
        if uplink_port_ids is not None:
            switch.device.uplink_port_ids = uplink_port_ids
            updated = True
        if port_num is not None:
            switch.device.port_num = port_num
            updated = True
        if hostname is not None:
            switch.device.hostname = hostname
            updated = True
        if data.get("ip"):
            switch.device.management_ip = data["ip"]
            updated = True


    result = switch.to_dict(exclude=["password"])
    result["ip_address"] = result.pop("ip", None)
    if switch.device:
        result["name"] = switch.device.device_name
        result["device_model"] = switch.device.device_model
        result["switch_role"] = switch.device.switch_role
        result["layer"] = switch.device.layer
        result["uplink_device_id"] = switch.device.uplink_device_id
        result["core_device_id"] = switch.device.core_device_id
        result["port_num"] = switch.device.port_num
        if switch.device.cabinet:
            result["room_id"] = switch.device.cabinet.room_id
            if switch.device.cabinet.room:
                result["room_name"] = switch.device.cabinet.room.name

    return APIResponse.success(
        data=result,
        message="更新成功",
    )


@router.route("/<int:device_id>", methods=["DELETE"])
@doc(summary="删除交换机", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError", 409: "ApiError", 500: "ApiError"})
@permission_required("switch:delete")
@api_exception_handler
@transactional
def delete_switch(device_id):
    """删除交换机

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    repo = SwitchRepository()

    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if repo.has_ports(switch.device_id):
        return APIResponse.error("该交换机有关联端口，请先删除端口", status_code=409)

    deleted = repo.delete(switch.id)
    if not deleted:
        return APIResponse.error(f"交换机 {device_id} 不存在", ErrorCode.NOT_FOUND, 404)

    return APIResponse.success(message="删除成功")


@router.route("/<int:device_id>/ports", methods=["GET"])
@doc(summary="获取交换机端口列表", tags=["交换机"], responses={200: "SwitchPortResponse", 404: "ApiError"})
@login_required
def get_switch_ports(device_id):
    """获取交换机端口列表（含 max_speed 字段）

    字段映射对齐前端 SwitchPort 类型定义。
    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    from app.adapters.adapter_factory import get_adapter

    switch, err = _find_switch_or_404(device_id)
    if err:
        return err

    port_repo = NetworkPortRepository()
    ports = port_repo.get_by_device(switch.device_id)

    adapter = get_adapter(switch.device_type) if switch.device_type else None
    customer_map = _build_customer_map(ports)
    data = _map_port_fields(ports, adapter, customer_map, device_id=switch.device_id)
    return APIResponse.success(data=data)


@router.route("/switch_detail/<int:device_id>/ports", methods=["GET"])
@doc(summary="获取交换机详情及端口列表", tags=["交换机"], responses={200: "SwitchResponse", 404: "ApiError"})
@login_required
def get_switch_detail_with_ports(device_id):
    """获取交换机详情及端口列表（前端 viewDetail 使用）

    旧版在打开详情时会异步触发 SSH 更新，新版通过 no_update 参数控制：
    - no_update=1（默认）：仅查数据库，不触发 SSH
    - no_update=0：异步触发 SSH 采集交换机信息

    Returns:
        {switch: {...}, ports: [...]}
    字段映射与 get_switch() 保持一致，对齐前端 SwitchWithPortsResponse。

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    from app.adapters.adapter_factory import get_adapter

    switch, err = _find_switch_or_404(device_id)
    if err:
        return err

    no_update = request.args.get("no_update", "1")
    if no_update == "0":
        from flask import current_app
        app_ref = current_app._get_current_object()
        user_id = g.current_user["user_id"] if hasattr(g, 'current_user') else None

        def _async_collect(app_ref):
            try:
                with app_ref.app_context():
                    service = SwitchInfoService()
                    service.collect_device_info(switch.device_id)
                    from app.services.switch_events import emit_resource_change, emit_resource_change_global
                    emit_resource_change(switch.device_id, "info_refresh", affected_ports=[])
                    emit_resource_change_global("device", "update", ids=[switch.device_id])
                    _notify_async_result(
                        user_id, "info_refresh", "刷新设备信息",
                        success=True, device_id=switch.device_id,
                    )
            except Exception as e:
                logger.error("异步采集交换机 device_id=%d 失败: %s", switch.device_id, e)
                try:
                    with app_ref.app_context():
                        from app.services.switch_events import emit_resource_change, emit_resource_change_global
                        emit_resource_change(
                            switch.device_id, "info_refresh",
                            affected_ports=[],
                            extra={"success": False, "error": str(e)},
                        )
                        emit_resource_change_global("device", "update", ids=[switch.device_id])
                except Exception:
                    logger.warning("异步采集交换机 device_id=%d 失败后 SSE 通知失败", switch.device_id, exc_info=True)
                _notify_async_result(
                    user_id, "info_refresh", "刷新设备信息",
                    success=False, error=str(e), device_id=switch.device_id,
                )

        from app.utils.concurrency.task_executor import task_executor
        task_executor.submit("collect_info", _async_collect, app_ref)

    port_repo = NetworkPortRepository()
    ports = port_repo.get_by_device(switch.device_id)

    switch_data = _map_switch_data(switch, ports)
    adapter = get_adapter(switch.device_type) if switch.device_type else None
    customer_map = _build_customer_map(ports)
    port_list = _map_port_fields(ports, adapter, customer_map, device_id=switch.device_id)

    return APIResponse.success(data={"switch": switch_data, "ports": port_list})


@router.route("/<int:device_id>/sync_ports", methods=["POST"])
@doc(summary="异步同步交换机端口信息", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
def sync_switch_ports(device_id):
    """异步同步交换机端口信息（仅执行 display interface，立即返回，后台执行）

    与 /scan 不同，此接口仅采集端口信息（display interface）并增量更新，
    不执行路由表、MAC、ARP 等全量扫描阶段。

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        return APIResponse.error("非网管设备不支持端口同步操作", ErrorCode.VALIDATION_ERROR, 400)

    user_id = g.current_user["user_id"] if hasattr(g, 'current_user') else None

    from app.utils.idempotency import _get_redis_client
    redis_client = _get_redis_client()
    lock_key = f"ipm:lock:sync_ports:{device_id}"
    if redis_client:
        acquired = redis_client.set(lock_key, "1", nx=True, ex=600)
        if not acquired:
            return APIResponse.error("该交换机端口同步正在进行中，请稍后再试", error_code="RESOURCE_LOCKED", status_code=409)

    def _async_sync_ports(app_ref):
        try:
            with app_ref.app_context():
                service = SwitchInfoService()
                result = service.collect_port_info(switch.device_id)
                from extensions import db
                db.session.commit()
                from app.services.switch_events import emit_resource_change
                if result.get("success"):
                    logger.info("异步同步端口信息 device_id=%d 完成", device_id)
                    emit_resource_change(switch.device_id, "scan_complete", affected_ports=[])
                    _notify_async_result(
                        user_id, "scan_complete", "同步数据",
                        success=True, device_id=switch.device_id,
                    )
                else:
                    error_msg = result.get("error", "未知错误")
                    logger.error("异步同步端口信息 device_id=%d 失败: %s", device_id, error_msg)
                    emit_resource_change(switch.device_id, "scan_complete", affected_ports=[])
                    _notify_async_result(
                        user_id, "scan_complete", "同步数据",
                        success=False, error=error_msg, device_id=switch.device_id,
                    )
        except Exception as e:
            logger.error("异步同步端口信息 device_id=%d 失败: %s", device_id, e)
            try:
                with app_ref.app_context():
                    from app.services.switch_events import emit_resource_change
                    emit_resource_change(
                        switch.device_id, "scan_complete",
                        affected_ports=[],
                        extra={"success": False, "error": str(e)},
                    )
            except Exception:
                logger.warning("异步同步端口信息 device_id=%d 失败后 SSE 通知失败", device_id, exc_info=True)
            _notify_async_result(
                user_id, "scan_complete", "同步数据",
                success=False, error=str(e), device_id=switch.device_id,
            )
        finally:
            if redis_client:
                try:
                    redis_client.delete(lock_key)
                except Exception:
                    pass

    from flask import current_app
    app_ref = current_app._get_current_object()
    from app.utils.concurrency.task_executor import task_executor
    task_executor.submit("sync_ports", _async_sync_ports, app_ref)
    return APIResponse.success(message="端口同步已启动，请稍后刷新查看结果")


@router.route("/<int:device_id>/scan", methods=["POST"])
@doc(summary="异步触发交换机扫描", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
def scan_switch(device_id):
    """异步触发交换机扫描（立即返回，后台执行）

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """

    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        return APIResponse.error("非网管设备不支持扫描操作", ErrorCode.VALIDATION_ERROR, 400)

    from app.utils.idempotency import _get_redis_client as _get_redis_client_scan
    scan_redis_client = _get_redis_client_scan()
    scan_lock_key = f"ipm:lock:scan_switch:{device_id}"
    if scan_redis_client:
        acquired = scan_redis_client.set(scan_lock_key, "1", nx=True, ex=1800)
        if not acquired:
            return APIResponse.error("该交换机扫描正在进行中，请稍后再试", error_code="RESOURCE_LOCKED", status_code=409)

    def _async_scan(app_ref):
        try:
            with app_ref.app_context():
                service = NetworkScannerService()
                service.scan_switch(switch.device_id)
                logger.info("异步扫描交换机 device_id=%d 完成", device_id)
                from app.services.switch_events import emit_resource_change
                emit_resource_change(switch.device_id, "scan_complete", affected_ports=[])
        except Exception as e:
            logger.error("异步扫描交换机 device_id=%d 失败: %s", device_id, e)
            try:
                with app_ref.app_context():
                    from app.services.switch_events import emit_resource_change
                    emit_resource_change(
                        switch.device_id, "scan_complete",
                        affected_ports=[],
                        extra={"success": False, "error": str(e)},
                    )
            except Exception:
                logger.warning("异步扫描交换机 device_id=%d 失败后 SSE 通知失败", device_id, exc_info=True)
        finally:
            if scan_redis_client:
                try:
                    scan_redis_client.delete(scan_lock_key)
                except Exception:
                    pass

    from flask import current_app
    app_ref = current_app._get_current_object()
    from app.utils.concurrency.task_executor import task_executor
    task_executor.submit("scan_switch", _async_scan, app_ref)
    return APIResponse.success(message="扫描已启动，请稍后刷新查看结果")


@router.route("/room/<int:room_id>/scan", methods=["POST"])
@doc(summary="触发机房扫描（异步）", tags=["交换机"], responses={200: "ApiResponse", 400: "ApiError"})
@permission_required("switch:config")
def scan_room(room_id):
    """触发机房扫描（异步，立即返回，前端轮询进度 API）"""
    from app.services.network_scanner_service import get_scan_progress
    scope = f"r:{room_id}"
    existing_progress = get_scan_progress(scope)
    if existing_progress:
        phase = existing_progress.get("phase")
        completed = existing_progress.get("completed", 0)
        total = existing_progress.get("total", 0)
        if phase == "完成" or (total > 0 and completed >= total):
            try:
                from app.utils.cache import cache_manager
                if cache_manager.primary_storage and cache_manager.primary_storage.redis_client:
                    from app.services.scan_redis import ScanRedis
                    sr = ScanRedis(cache_manager.primary_storage.redis_client)
                    sr.progress_set(f"r:{room_id}", {
                        "scope": f"r:{room_id}",
                        "room_id": room_id,
                        "total": 0,
                        "completed": 0,
                        "failed": 0,
                        "phase": "准备中",
                        "elapsed_seconds": 0,
                        "eta_seconds": 0,
                    })
            except Exception:
                logger.warning("机房扫描重入保护进度重置失败: room_id=%d", room_id, exc_info=True)
        else:
            return APIResponse.error("已有扫描任务在进行中", error_code="SCAN_RUNNING", status_code=400)

    from app.utils.cache import cache_manager
    redis_client = (
        cache_manager.primary_storage.redis_client
        if cache_manager.primary_storage else None
    )
    SCAN_LOCK_TTL = 7200
    acquired_locks = []
    if redis_client:
        from app.persistence.switch_repo import SwitchRepository
        from app.services.network_scanner_service import get_scan_progress
        sw_ids = SwitchRepository().find_room_switch_ids(room_id)
        scope = f"r:{room_id}"
        for did in sw_ids:
            lock_key = f"scan_lock:{did}"
            if redis_client.exists(lock_key):
                lock_scope = redis_client.get(lock_key)
                if lock_scope:
                    lock_scope_str = lock_scope if isinstance(lock_scope, str) else lock_scope.decode()
                    progress = get_scan_progress(lock_scope_str)
                    if progress and progress.get("phase") != "完成" and not (
                        progress.get("total", 0) > 0
                        and progress.get("completed", 0) >= progress.get("total", 0)
                    ):
                        for lk in acquired_locks:
                            redis_client.delete(lk)
                        return APIResponse.error(
                            f"以下交换机正在被虚拟机房扫描任务占用: [{did}]",
                            error_code="SCAN_CONFLICT",
                            status_code=400,
                        )
                redis_client.delete(lock_key)
            if redis_client.set(lock_key, scope, nx=True, ex=SCAN_LOCK_TTL):
                acquired_locks.append(lock_key)
            else:
                for lk in acquired_locks:
                    redis_client.delete(lk)
                return APIResponse.error(
                    f"交换机 {did} 正在被其他扫描任务占用",
                    error_code="SCAN_CONFLICT",
                    status_code=400,
                )

    from flask import current_app
    app_ref = current_app._get_current_object()

    def _async_scan():
        try:
            with app_ref.app_context():
                service = NetworkScannerService()
                result = service.scan_room(room_id)
                if isinstance(result, dict) and result.get("reason") == "missing_n2n_connections":
                    from app.services.switch_events import emit_global_event
                    emit_global_event("room_scan_complete", {
                        "scope": f"r:{room_id}",
                        "room_id": room_id,
                        "error": result.get("message", "缺少N2N连接"),
                        "reason": "missing_n2n_connections",
                    })
                    from app.services.scan_redis import ScanRedis, get_scan_redis_client
                    redis_client = get_scan_redis_client()
                    if redis_client:
                        sr = ScanRedis(redis_client)
                        sr.progress_set(f"r:{room_id}", {
                            "scope": f"r:{room_id}",
                            "room_id": room_id,
                            "total": 0,
                            "completed": 0,
                            "failed": 1,
                            "phase": "failed",
                            "reason": "missing_n2n_connections",
                            "elapsed_seconds": 0,
                            "eta_seconds": 0,
                        })
                    return
                from app.services.switch_events import emit_resource_change
                switches = SwitchExtRepository().get_all_by_room(room_id)
                for sw in switches:
                    emit_resource_change(sw.device_id, "scan_complete", affected_ports=[])
                from app.services.switch_events import emit_global_event
                emit_global_event("room_scan_complete", {"scope": f"r:{room_id}", "room_id": room_id})
                from app.services.notification_service import notification_service
                _room = RoomRepository().find_by_id(room_id)
                _room_name = _room.name if _room else f"机房#{room_id}"
                notification_service.notify(
                    type=NotificationTypeCode.ROOM_SCAN_COMPLETE,
                    severity="info",
                    title=f"机房扫描完成",
                    content=f"机房「{_room_name}」的网络扫描已完成",
                    payload={"room_id": room_id, "scope": f"r:{room_id}"},
                    source_module="scan",
                    target_type="broadcast",

                    idempotency_key=f"room_scan_complete:r:{room_id}:{int(time.time())}",
                )
        except Exception as e:
            logger.error("异步机房扫描 %d 失败: %s", room_id, e)
            try:
                with app_ref.app_context():
                    from app.services.switch_events import emit_global_event
                    from app.services.scan_redis import ScanRedis, get_scan_redis_client
                    redis_client = get_scan_redis_client()
                    if redis_client:
                        sr = ScanRedis(redis_client)
                        for did in sw_ids:
                            lock_key = f"scan_lock:{did}"
                            try:
                                redis_client.delete(lock_key)
                            except Exception:
                                logger.warning("清理 scan_lock 失败: device_id=%d", did, exc_info=True)
                        fail_progress = {
                            "scope": f"r:{room_id}",
                            "room_id": room_id,
                            "total": 0,
                            "completed": 0,
                            "failed": 1,
                            "phase": "完成",
                            "elapsed_seconds": 0,
                            "eta_seconds": 0,
                        }
                        sr.progress_set(f"r:{room_id}", fail_progress)
                        emit_global_event("scan_progress", fail_progress)
                    emit_global_event("room_scan_complete", {"scope": f"r:{room_id}", "room_id": room_id, "error": str(e)})
                    from app.services.notification_service import notification_service
                    _room = RoomRepository().find_by_id(room_id)
                    _room_name = _room.name if _room else f"机房#{room_id}"
                    notification_service.notify(
                        type=NotificationTypeCode.ROOM_SCAN_FAILED,
                        severity="warning",
                        title="机房扫描失败",
                        content=f"机房「{_room_name}」扫描异常: {str(e)[:200]}",
                        payload={"room_id": room_id, "scope": f"r:{room_id}"},
                        source_module="scan",
                        target_type="broadcast",
    
                        idempotency_key=f"room_scan_failed:r:{room_id}:{int(time.time())}",
                    )
            except Exception:
                logger.warning("异步机房扫描 %d 失败后清理/通知失败", room_id, exc_info=True)

    from app.utils.concurrency.task_executor import task_executor
    task_executor.submit("scan_room", _async_scan)
    return APIResponse.success(message="机房扫描已启动，请轮询进度 API 获取实时进度")


@router.route("/room/<int:room_id>/scan/progress", methods=["GET"])
@doc(summary="查询机房扫描实时进度", tags=["交换机"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def scan_room_progress(room_id):
    """查询机房扫描实时进度

    从 Redis 读取 ScanProgress 数据，供前端轮询展示进度条。
    返回格式：{ room_id, total, completed, failed, phase, elapsed_seconds, eta_seconds }
    无进行中的扫描时返回 { progress: null }。
    """
    from app.services.network_scanner_service import get_scan_progress
    progress = get_scan_progress(f"r:{room_id}")
    return APIResponse.success(data={"progress": progress})


@router.route("/<int:device_id>/collect_info", methods=["POST"])
@doc(summary="异步采集交换机设备信息", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
def collect_switch_info(device_id):
    """异步采集交换机设备信息（立即返回，后台执行）

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """

    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        return APIResponse.error("非网管设备不支持信息采集操作", ErrorCode.VALIDATION_ERROR, 400)

    user_id = g.current_user["user_id"] if hasattr(g, 'current_user') else None

    def _async_collect(app_ref):
        try:
            with app_ref.app_context():
                service = SwitchInfoService()
                service.collect_device_info(switch.device_id)
                from extensions import db
                db.session.commit()
                logger.info("异步采集交换机 device_id=%d 设备信息完成", device_id)
                from app.services.switch_events import emit_resource_change, emit_resource_change_global
                emit_resource_change(switch.device_id, "info_refresh", affected_ports=[])
                emit_resource_change_global("device", "update", ids=[switch.device_id])
                _notify_async_result(
                    user_id, "info_refresh", "刷新设备信息",
                    success=True, device_id=switch.device_id,
                )
        except Exception as e:
            logger.error("异步采集交换机 device_id=%d 设备信息失败: %s", device_id, e)
            try:
                with app_ref.app_context():
                    from app.services.switch_events import emit_resource_change, emit_resource_change_global
                    emit_resource_change(
                        switch.device_id, "info_refresh",
                        affected_ports=[],
                        extra={"success": False, "error": str(e)},
                    )
                    emit_resource_change_global("device", "update", ids=[switch.device_id])
            except Exception:
                logger.warning("异步采集交换机 device_id=%d 设备信息失败后 SSE 通知失败", device_id, exc_info=True)
            _notify_async_result(
                user_id, "info_refresh", "刷新设备信息",
                success=False, error=str(e), device_id=switch.device_id,
            )

    from flask import current_app
    app_ref = current_app._get_current_object()
    from app.utils.concurrency.task_executor import task_executor
    task_executor.submit("collect_info", _async_collect, app_ref)
    return APIResponse.success(message="采集已启动，请稍后刷新查看结果")


@router.route("/<int:device_id>/ports/<path:port_number>", methods=["GET"])
@doc(summary="获取端口详情", tags=["交换机"], responses={200: "SwitchPortResponse", 404: "ApiError"})
@login_required
def get_port_detail(device_id, port_number):
    """获取端口详情（仅从 sw_info + sw_info_ip 读取，不触发 SSH）

    数据来源：
    - sw_info 表：端口状态/VLAN/MAC/速率/描述等摘要信息
    - sw_info_ip 表：端口 IP 列表（支持多 IP）
    - sw_port_info 表：端口配置文本的缓存状态（仅返回是否有缓存 + updated_at）

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    sw_repo = SwitchRepository()
    cached = sw_repo.get_port_info_cache(device_id, port_number)
    if not cached:
        return APIResponse.success(None)

    result = {
        "port": cached.get("port_number", port_number),
        "status": cached.get("status"),
        "vlan": cached.get("vlan"),
        "mac_address": cached.get("mac_address"),
        "ip_address": cached.get("ip_address"),
        "speed": cached.get("speed"),
        "description": cached.get("notes", ""),
        "port_mac": cached.get("mac_address"),
        "updated_at": cached.get("updated_at"),
    }
    result["ip_list"] = sw_repo.get_port_ips(device_id, port_number)
    config_cached = sw_repo.get_port_config_with_time(device_id, port_number)
    result["has_port_config"] = config_cached is not None
    result["port_config_updated_at"] = config_cached["updated_at"] if config_cached else None
    import re as _re
    if config_cached and config_cached.get("port_config"):
        _m = _re.search(r"eth-trunk\s+(\d+)", config_cached["port_config"], _re.IGNORECASE)
        if _m:
            result["eth_trunk_id"] = int(_m.group(1))

    id_match = _re.search(r"\d+", port_number)
    if id_match:
        port_id = int(id_match.group())
        if port_number.lower().startswith("vlan"):
            vlan_row = VLANRepository().find_by_device_and_vlan_id(device_id, port_id)
            if vlan_row:
                vlan_data = vlan_row.to_dict()
                if vlan_data.get("member_ports"):
                    result["vlan_ports"] = vlan_data["member_ports"]
        elif "trunk" in port_number.lower():
            lag_row = LinkAggregationRepository().find_by_device_and_name(device_id, port_number)
            if lag_row:
                lag_data = lag_row.to_dict()
                if lag_data.get("member_ports"):
                    result["trunk_members"] = lag_data["member_ports"]
    return APIResponse.success(result)


@router.route("/<int:device_id>/ports/<path:port_number>", methods=["PUT"])
@doc(summary="更新端口信息（客户归属+描述）", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def update_port_info(device_id, port_number):
    """更新端口信息（客户归属 + 描述）

    逻辑：
    - customer_id 有值：设置客户归属（纯 SQL 操作）
    - customer_id 为 null/0：删除客户归属（纯 SQL 操作，置空 customer_id）
    - description 有值：
      - 网管设备：通过 SSH 设置端口描述
      - 非网管设备：直接更新数据库
    - description 为空字符串：
      - 网管设备：通过 SSH 删除端口描述（undo description）
      - 非网管设备：直接清空数据库描述字段
    - 描述变更后自动刷新端口配置缓存
    - 客户/描述与数据库当前值一致时跳过执行，避免无意义的 SSH 操作

    注意：客户归属和描述是独立操作，任一失败不影响另一个。

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    data = request.get_json()
    repo = SwitchRepository()
    service = SwitchConfigService()

    errors = []

    switch = repo.find_by_device_id(device_id)
    is_managed = switch.has_ssh if switch else True

    current_info = repo.get_port_info_cache(device_id, port_number)
    current_customer_id = current_info.get("customer_id") if current_info else None
    current_description = current_info.get("notes") if current_info else None

    if "customer_id" in data:
        customer_id = data["customer_id"]
        effective_customer_id = None if (customer_id is None or customer_id == 0) else customer_id
        if effective_customer_id != current_customer_id:
            try:
                service.update_port_customer(device_id, port_number, effective_customer_id)
            except Exception as e:
                logger.error("更新端口客户归属失败: %s", e)
                errors.append("客户归属更新失败")

    description = data.get("description")
    if description is not None:
        if description != (current_description or ""):
            if is_managed:
                if switch:
                    desc_result = service.modify_port_description(switch, port_number, description)
                    if not desc_result.get("success"):
                        errors.append(f"描述更新失败: {desc_result.get('error', '')}")
            else:
                result = service.dispatch_port_action_db(
                    device_id, 'update_port_info', port_number,
                    {'description': description},
                )
                if not result.get("success"):
                    errors.append(f"描述更新失败: {result.get('error', '')}")

    if errors:
        return APIResponse.error("; ".join(errors))

    return APIResponse.success({"message": "端口信息已更新"})


@router.route("/<int:device_id>/ports/<path:port_number>/config", methods=["GET"])
@doc(summary="获取端口配置文本", tags=["交换机"], responses={200: "SwitchPortResponse", 401: "ApiError"})
@login_required
@transactional
def fetch_port_config(device_id, port_number):
    """获取端口配置文本

    流程：
    1. 先查 sw_port_info 缓存，命中则直接返回
    2. 未命中则 SSH 获取 display current-configuration interface <port>
    3. 写入 sw_port_info 表
    4. 从配置文本解析 VLAN/IP，同步回 sw_info / sw_info_ip 表

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    service = SwitchConfigService()
    result = service.fetch_port_config(device_id, port_number)
    if result.get("success") is False:
        return APIResponse.error(result.get("message", "获取配置失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/ports/<path:port_number>/refresh", methods=["GET"])
@doc(summary="强制刷新端口配置", tags=["交换机"], responses={200: "SwitchPortResponse", 401: "ApiError"})
@login_required
@transactional
def refresh_port_detail(device_id, port_number):
    """强制刷新端口配置（跳过缓存，从设备实时读取并同步）

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    service = SwitchConfigService()
    result = service.fetch_port_config(device_id, port_number, force_refresh=True)
    if result.get("success") is False:
        return APIResponse.error(result.get("message", "刷新失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/sync_members", methods=["POST"])
@doc(summary="批量同步VLAN/链路聚合成员端口", tags=["交换机"], responses={200: "ApiResponse", 401: "ApiError"})
@permission_required("switch:config")
def sync_members(device_id):
    """异步批量同步 VLAN 和链路聚合的成员端口（立即返回，后台执行）

    使用 display vlan / display eth-trunk（不带 ID）一次性获取所有成员，
    仅需 2 次 SSH 连接即可完成全部同步。

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        return APIResponse.error("非网管设备不支持成员同步操作", ErrorCode.VALIDATION_ERROR, 400)

    user_id = g.current_user["user_id"] if hasattr(g, 'current_user') else None

    def _async_sync_members(app_ref):
        try:
            with app_ref.app_context():
                from app.services.sync_coordinator import SyncCoordinator
                from app.infra import SSHManager
                from app.persistence.switch_repo import SwitchRepository
                from app.services.device_op_lock import DeviceOpLock

                coordinator = SyncCoordinator(
                    SSHManager(), SwitchRepository(), DeviceOpLock(),
                )
                results = coordinator.batch_sync_members(switch.device_id)
                from extensions import db
                db.session.commit()
                logger.info("异步同步成员端口 device_id=%d 完成", device_id)
                from app.services.switch_events import emit_resource_change, emit_resource_change_global
                emit_resource_change(switch.device_id, "port_sync", affected_ports=[], affected_lags=[], affected_vlans=[])
                emit_resource_change_global("device", "update", ids=[switch.device_id])
                errors = results.get("errors", [])
                if errors:
                    _notify_async_result(
                        user_id, "sync_members", "同步成员端口",
                        success=False, error="; ".join(errors), device_id=switch.device_id,
                    )
                else:
                    _notify_async_result(
                        user_id, "sync_members", "同步成员端口",
                        success=True, device_id=switch.device_id,
                    )
        except Exception as e:
            logger.error("异步同步成员端口 device_id=%d 失败: %s", device_id, e)
            try:
                with app_ref.app_context():
                    from app.services.switch_events import emit_resource_change, emit_resource_change_global
                    emit_resource_change(
                        switch.device_id, "port_sync",
                        affected_ports=[], affected_lags=[], affected_vlans=[],
                        extra={"success": False, "error": str(e)},
                    )
                    emit_resource_change_global("device", "update", ids=[switch.device_id])
            except Exception:
                logger.warning("异步同步成员端口 device_id=%d 失败后 SSE 通知失败", device_id, exc_info=True)
            _notify_async_result(
                user_id, "sync_members", "同步成员端口",
                success=False, error=str(e), device_id=switch.device_id,
            )

    from flask import current_app
    app_ref = current_app._get_current_object()
    from app.utils.concurrency.task_executor import task_executor
    task_executor.submit("sync_members", _async_sync_members, app_ref)
    return APIResponse.success(message="成员端口同步已启动，请稍后刷新查看结果")


@router.route("/<int:device_id>/ports/<path:port_number>/clear", methods=["DELETE"])
@doc(summary="清除端口配置", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def clear_port_config(device_id, port_number):
    """清除端口配置

    SSH 执行 clear configuration this（带 Y 确认），
    清除后通过 _sync_port_from_device 自动同步三表。

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        service = SwitchConfigService()
        result = service.dispatch_port_action_db(switch.device_id, 'clear_port_config', port_number)
        if not result.get("success"):
            return APIResponse.error(result.get("error", "清除配置失败"))
        return APIResponse.success(result)

    service = SwitchConfigService()
    result = service.clear_port_config(switch, port_number)
    if not result.get("success"):
        return APIResponse.error(result.get("error", "清除配置失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/ports_list", methods=["GET"])
@doc(summary="获取端口名称列表", tags=["交换机"], responses={200: "SwitchPortResponse", 401: "ApiError"})
@login_required
def get_ports_list(device_id):
    """端口名称列表

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    repo = SwitchRepository()
    ports = repo.get_switch_ports_list(device_id)
    return APIResponse.success(ports)


@router.route("/<int:device_id>/ports/action", methods=["POST"])
@doc(summary="异步端口操作", tags=["交换机"], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def port_action(device_id):
    """异步端口操作（提交后台线程执行，通过SSE推送结果）

    网管设备(has_ssh=true): SSH下发 + DB同步（异步）
    非网管设备(has_ssh=false): 纯DB操作（同步返回）

    请求体:
    {
        "action": "enable_port",
        "port": "GigabitEthernet0/0/1",
        "params": {}
    }
    """
    from flask import current_app
    from app.services.switch_events import emit_port_action_result
    from app.utils.concurrency.task_executor import task_executor

    data = request.get_json()
    action = data.get("action")
    port = data.get("port", "")
    params = data.get("params", {})

    if not action:
        return APIResponse.error("缺少 action 参数", ErrorCode.VALIDATION_ERROR, 400)

    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    app_ref = current_app._get_current_object()
    switch_device_id = switch.device_id
    is_managed = switch.has_ssh
    user_id = g.current_user["user_id"] if hasattr(g, 'current_user') else None

    if not is_managed:
        service = SwitchConfigService()
        result = service.dispatch_port_action_db(
            switch_device_id, action, port, params,
        )
        success = result.get("success", False)
        _notify_port_action_result(
            user_id, switch_device_id, port, action,
            success=success,
            message=result.get("message", ""),
            error=result.get("error", ""),
        )
        return APIResponse.success({
            "action": action,
            "status": "completed" if success else "failed",
            "result": result,
        })

    def _execute_and_notify():
        """后台线程：执行操作 + 推送SSE结果 + 创建站内信通知

        无论操作成功或异常，都通过 emit_port_action_result 推送结果，
        确保前端不会因事件丢失而超时。同时通过 notify() 创建站内信，
        确保不在当前页面的用户也能收到操作结果。
        """
        with app_ref.app_context():
            try:
                service = SwitchConfigService()
                sw = SwitchRepository().find_by_device_id(switch_device_id)
                if not sw:
                    emit_port_action_result(
                        switch_device_id, port, task_id, action,
                        success=False, error="交换机对象已失效",
                    )
                    _notify_port_action_result(
                        user_id, switch_device_id, port, action,
                        success=False, error="交换机对象已失效",
                    )
                    return

                result = service.dispatch_port_action(sw, action, port, params)
                success = result.get("success", False)
                emit_port_action_result(
                    switch_device_id, port, task_id, action,
                    success=success,
                    message=result.get("message", ""),
                    error=result.get("error", ""),
                    detail_op_type=result.get("detail_op_type", ""),
                )
                _notify_port_action_result(
                    user_id, switch_device_id, port, action,
                    success=success,
                    message=result.get("message", ""),
                    error=result.get("error", ""),
                )
            except Exception as e:
                logger.error("端口操作异常 device=%d port=%s action=%s: %s",
                             switch_device_id, port, action, e, exc_info=True)
                emit_port_action_result(
                    switch_device_id, port, task_id, action,
                    success=False, error=f"操作异常: {e}",
                )
                _notify_port_action_result(
                    user_id, switch_device_id, port, action,
                    success=False, error=f"操作异常: {e}",
                )

    task_id = task_executor.submit("port_action", _execute_and_notify)
    return APIResponse.success({
        "task_id": task_id,
        "action": action,
        "status": "pending",
    })


@router.route("/<int:device_id>/ports/batch-action", methods=["POST"])
@doc(summary="异步批量端口操作", tags=["交换机"], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@permission_required("switch:config")
def batch_port_action(device_id):
    """异步批量端口操作（提交后台线程执行，通过SSE推送结果）

    请求体:
    {
        "action": "set_port_vlan",
        "ports": ["10GE1/0/1", "10GE1/0/2", "10GE1/0/3"],
        "port_range": "10GE1/0/5 to 10GE1/0/10",
        "params": {"vlan_id": 100, "mode": "access"}
    }

    立即返回:
    {"task_id": "batch_port_action_xxxx", "action": "set_port_vlan", "status": "pending"}
    """
    from flask import current_app
    from app.services.switch_events import emit_port_action_result
    from app.utils.concurrency.task_executor import task_executor
    from app.utils.port_range_parser import PortRangeParser

    data = request.get_json()
    action = data.get("action")
    ports = data.get("ports", [])
    port_range = data.get("port_range", "")
    params = data.get("params", {})

    if not action:
        return APIResponse.error("缺少 action 参数", ErrorCode.VALIDATION_ERROR, 400)

    try:
        resolved_ports = PortRangeParser.parse(
            ports=ports,
            port_range=port_range if port_range else None,
        )
    except ValueError as e:
        return APIResponse.error(str(e), ErrorCode.VALIDATION_ERROR, 400)

    if not resolved_ports:
        return APIResponse.error("端口列表不能为空", ErrorCode.VALIDATION_ERROR, 400)

    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    app_ref = current_app._get_current_object()
    switch_device_id = switch.device_id
    is_managed = switch.has_ssh
    user_id = g.current_user["user_id"] if hasattr(g, 'current_user') else None

    def _execute_and_notify():
        """后台线程：执行批量操作 + 推送SSE结果 + 创建站内信通知"""
        with app_ref.app_context():
            try:
                service = SwitchConfigService()
                sw = SwitchRepository().find_by_device_id(switch_device_id)

                if is_managed and sw:
                    result = service.batch_port_action(sw, action, resolved_ports, params)
                else:
                    result = service.batch_port_action_db(
                        switch_device_id, action, resolved_ports, params,
                    )

                success = result.get("success", False)
                port_display = ",".join(resolved_ports[:5]) + (f" 等 {len(resolved_ports)} 个端口" if len(resolved_ports) > 5 else "")
                emit_port_action_result(
                    switch_device_id, port_display, task_id, action,
                    success=success,
                    message=f"批量操作完成: 成功{result.get('succeeded', 0)}/{result.get('total', 0)}",
                    error=result.get("error", ""),
                )
                _notify_port_action_result(
                    user_id, switch_device_id, port_display, action,
                    success=success,
                    message=f"批量操作完成: 成功{result.get('succeeded', 0)}/{result.get('total', 0)}",
                    error=result.get("error", ""),
                )
            except Exception as e:
                logger.error("批量端口操作异常 device=%d action=%s: %s",
                             switch_device_id, action, e, exc_info=True)
                emit_port_action_result(
                    switch_device_id, "", task_id, action,
                    success=False, error=f"批量操作异常: {e}",
                )
                _notify_port_action_result(
                    user_id, switch_device_id, "", action,
                    success=False, error=f"批量操作异常: {e}",
                )

    task_id = task_executor.submit("batch_port_action", _execute_and_notify)
    return APIResponse.success({
        "task_id": task_id,
        "action": action,
        "status": "pending",
        "port_count": len(resolved_ports),
    })


@router.route("/<int:device_id>/ports/<path:port_number>/enable", methods=["POST"])
@doc(summary="启用端口", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def enable_port(device_id, port_number):
    """启用端口

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        service = SwitchConfigService()
        result = service.dispatch_port_action_db(switch.device_id, 'enable_port', port_number)
        if not result.get("success"):
            return APIResponse.error(result.get("error", "启用端口失败"))
        return APIResponse.success(result)

    service = SwitchConfigService()
    result = service.enable_port(switch, port_number)
    if not result.get("success"):
        return APIResponse.error(result.get("error", "启用端口失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/ports/<path:port_number>/disable", methods=["POST"])
@doc(summary="禁用端口", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def disable_port(device_id, port_number):
    """禁用端口

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        service = SwitchConfigService()
        result = service.dispatch_port_action_db(switch.device_id, 'disable_port', port_number)
        if not result.get("success"):
            return APIResponse.error(result.get("error", "禁用端口失败"))
        return APIResponse.success(result)

    service = SwitchConfigService()
    result = service.shutdown_port(switch, port_number)
    if not result.get("success"):
        return APIResponse.error(result.get("error", "禁用端口失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/ports/<path:port_number>/speed", methods=["POST"])
@doc(summary="设置端口限速", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def set_port_speed(device_id, port_number):
    """设置端口限速（QoS 策略方式）

    统一使用 traffic-policy（华为）或 qos policy（H3C）方式限速。
    inbound/outbound 单位为 Mbps，0 表示取消该方向限速。
    限速值范围由前端根据端口速率动态控制，后端不做范围限制。

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    data = request.get_json()
    inbound = data.get("inbound_speed", 0)
    outbound = data.get("outbound_speed", 0)
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        return APIResponse.error("非网管设备不支持限速操作（需SSH连接设备）", ErrorCode.VALIDATION_ERROR, 400)

    service = SwitchConfigService()
    result = service.set_port_speed_limit(switch, port_number, inbound, outbound)
    if not result.get("success"):
        return APIResponse.error(result.get("error", "限速设置失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/ports/<path:port_number>/vlan", methods=["POST"])
@doc(summary="配置端口VLAN", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def set_port_vlan(device_id, port_number):
    """配置端口VLAN

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    data = request.get_json()
    vlan_id = data.get("vlan_id")
    mode = data.get("mode", "access")
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        service = SwitchConfigService()
        result = service.dispatch_port_action_db(
            switch.device_id, 'set_port_vlan', port_number,
            {'vlan_id': vlan_id, 'mode': mode}
        )
        if not result.get("success"):
            return APIResponse.error(result.get("error", "VLAN配置失败"))
        return APIResponse.success(result)

    service = SwitchConfigService()
    result = service.set_port_vlan(switch, port_number, vlan_id, mode)
    if not result.get("success"):
        return APIResponse.error(result.get("error", "VLAN配置失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/vlans/<int:vlan_id>", methods=["DELETE"])
@doc(summary="删除VLAN", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def delete_vlan(device_id, vlan_id):
    """删除VLAN

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        return APIResponse.error("非网管设备不支持删除VLAN操作（需SSH连接设备）", ErrorCode.VALIDATION_ERROR, 400)

    service = SwitchConfigService()
    result = service.delete_vlan(switch, vlan_id)
    if not result.get("success"):
        return APIResponse.error(result.get("error", "删除VLAN失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/port-channels/<int:trunk_id>/ports", methods=["POST"])
@doc(summary="加入Eth-Trunk", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def add_port_to_trunk(device_id, trunk_id):
    """加入Eth-Trunk

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    data = request.get_json()
    port = data.get("port")
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        service = SwitchConfigService()
        member_port = data.get("port")
        result = service.dispatch_port_action_db(
            switch.device_id, 'add_port_to_trunk', member_port,
            {'channel_id': trunk_id}
        )
        if not result.get("success"):
            return APIResponse.error(result.get("error", "加入Eth-Trunk失败"))
        return APIResponse.success(result)

    service = SwitchConfigService()
    result = service.add_port_to_channel(switch, trunk_id, port)
    if not result.get("success"):
        return APIResponse.error(result.get("error", "加入Eth-Trunk失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/port-channels/<int:trunk_id>", methods=["DELETE"])
@doc(summary="删除Eth-Trunk", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def delete_trunk(device_id, trunk_id):
    """删除Eth-Trunk

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        return APIResponse.error("非网管设备不支持删除Eth-Trunk操作（需SSH连接设备）", ErrorCode.VALIDATION_ERROR, 400)

    service = SwitchConfigService()
    result = service.delete_eth_trunk(switch, trunk_id)
    if not result.get("success"):
        return APIResponse.error(result.get("error", "删除Eth-Trunk失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/ports/<path:port_number>/ip", methods=["POST"])
@doc(summary="配置端口IP", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def set_port_ip(device_id, port_number):
    """配置端口IP

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    data = request.get_json()
    ip_address = data.get("ip_address")
    subnet_mask = data.get("subnet_mask")
    is_secondary = data.get("is_secondary", False)
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        return APIResponse.error("非网管设备不支持IP配置操作（需SSH连接设备）", ErrorCode.VALIDATION_ERROR, 400)

    service = SwitchConfigService()
    result = service.set_port_ip(switch, port_number, ip_address, subnet_mask, is_secondary)
    if not result.get("success"):
        return APIResponse.error(result.get("error", "IP配置失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/ports/<path:port_number>/ip", methods=["GET"])
@doc(summary="查询端口IP", tags=["交换机"], responses={200: "SwitchPortIPResponse", 401: "ApiError"})
@login_required
def get_port_ips(device_id, port_number):
    """查询端口IP

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    service = SwitchConfigService()
    ips = service.get_port_ips(device_id, port_number)
    return APIResponse.success(ips)


@router.route("/<int:device_id>/ports/<path:port_number>/ip", methods=["DELETE"])
@doc(summary="删除端口IP", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def delete_port_ip(device_id, port_number):
    """删除端口IP

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    data = request.get_json()
    ip_address = data.get("ip_address")
    subnet_mask = data.get("subnet_mask")
    is_secondary = data.get("is_secondary", False)
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        return APIResponse.error("非网管设备不支持删除IP操作（需SSH连接设备）", ErrorCode.VALIDATION_ERROR, 400)

    service = SwitchConfigService()
    result = service.delete_port_ip(switch, port_number, ip_address, subnet_mask, is_secondary)
    if not result.get("success"):
        return APIResponse.error(result.get("error", "删除IP失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/ports/<path:port_number>/interface", methods=["DELETE"])
@doc(summary="删除接口（虚拟接口）", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def delete_interface(device_id, port_number):
    """删除接口（LoopBack等虚拟接口）

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        return APIResponse.error("非网管设备不支持删除接口操作（需SSH连接设备）", ErrorCode.VALIDATION_ERROR, 400)

    service = SwitchConfigService()
    result = service.delete_interface(switch, port_number)
    if not result.get("success"):
        return APIResponse.error(result.get("error", "删除接口失败"))
    return APIResponse.success(result)


@router.route("/<int:device_id>/port-channels", methods=["POST"])
@doc(summary="创建链路聚合组(Eth-Trunk)", tags=["交换机"], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def create_port_channel(device_id):
    """创建链路聚合组(Eth-Trunk)

    请求体: {"channel_id": 10, "member_ports": ["XGigabitEthernet0/0/1"]}

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    data = request.get_json()
    channel_id = data.get("channel_id")
    member_ports = data.get("member_ports", [])

    if channel_id is None:
        return APIResponse.error("缺少 channel_id", ErrorCode.VALIDATION_ERROR, 400)

    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        return APIResponse.error("非网管设备不支持创建链路聚合操作（需SSH连接设备）", ErrorCode.VALIDATION_ERROR, 400)

    service = SwitchConfigService()
    result = service.create_port_channel(switch, channel_id, member_ports)
    return APIResponse.success(result)


@router.route("/<int:device_id>/ports/<path:port_number>/port-channel", methods=["DELETE"])
@doc(summary="从链路聚合组移除端口", tags=["交换机"], responses={200: "ApiResponse", 404: "ApiError"})
@permission_required("switch:config")
@transactional
def remove_port_from_channel(device_id, port_number):
    """从链路聚合组移除端口

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    switch, _err = _find_switch_or_404(device_id)
    if _err:
        return _err

    if not switch.has_ssh:
        service = SwitchConfigService()
        result = service.dispatch_port_action_db(switch.device_id, 'remove_port_from_channel', port_number)
        if not result.get("success"):
            return APIResponse.error(result.get("error", "移除链路聚合成员失败"))
        return APIResponse.success(result)

    service = SwitchConfigService()
    result = service.remove_port_from_channel(switch, port_number)
    return APIResponse.success(result)


@router.route("/scan/status", methods=["GET"])
@doc(summary="获取扫描任务状态", tags=["交换机"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def scan_status():
    """获取扫描任务状态

    返回当前是否有扫描任务运行中，以及进度信息。
    """
    service = NetworkScannerService()
    status_info = service.get_scan_status()
    return APIResponse.success(data=status_info)


@router.route("/events", methods=["GET"])
@doc(summary="SSE全局事件流（已迁移至ASGI网关）", tags=["交换机"], responses={410: "ApiError"})
def global_events():
    """SSE 全局事件流 — 已迁移至独立 ASGI 推送网关

    此端点已废弃（410 Gone）。SSE 服务已从 Flask 移出，
    由独立的 realtime_gateway (uvicorn) 进程提供。
    新端点：GET /sse/global?token=xxx

    迁移原因：
    - SSE 长连接占用 Flask worker 线程
    - 多进程部署下 seq/环形缓冲区不一致
    - 网关单进程持有 seq，天然全局唯一、天然支持重放
    """
    return APIResponse.error(
        "SSE 服务已迁移至 ASGI 推送网关，请使用 /sse/global?token=xxx",
        error_code="GONE",
        status_code=410,
    )


@router.route("/<int:device_id>/events", methods=["GET"])
@doc(summary="SSE端口变更事件流（已迁移至ASGI网关）", tags=["交换机"], responses={410: "ApiError"})
def switch_events(device_id):
    """SSE 端口变更事件流 — 已迁移至独立 ASGI 推送网关

    此端点已废弃（410 Gone）。SSE 服务已从 Flask 移出，
    由独立的 realtime_gateway (uvicorn) 进程提供。
    新端点：GET /sse/switch/{device_id}?since_seq=0&ticket=xxx

    迁移原因同 global_events。
    """
    return APIResponse.error(
        f"SSE 服务已迁移至 ASGI 推送网关，请使用 /sse/switch/{device_id}?ticket=xxx",
        error_code="GONE",
        status_code=410,
    )




@router.route("/<int:device_id>/ext", methods=["GET"])
@doc(summary="查询交换机扩展信息", tags=["交换机"], responses={200: "SwitchResponse", 404: "ApiError"})
@login_required
def get_switch_ext(device_id):
    """查询交换机扩展信息

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    from app.persistence.switch_ext_repository import SwitchExtRepository
    sw, _err = _find_switch_or_404(device_id)
    if _err:
        return _err
    repo = SwitchExtRepository()
    ext = repo.get_by_device_id(sw.device_id)
    if not ext:
        return APIResponse.error("扩展信息不存在", ErrorCode.NOT_FOUND, 404)
    return APIResponse.success(ext.to_dict())


@router.route("/<int:device_id>/ext", methods=["POST"])
@doc(summary="创建交换机扩展信息", tags=["交换机"], responses={200: "SwitchResponse", 404: "ApiError"})
@permission_required("switch:create")
@transactional
def create_switch_ext(device_id):
    """创建交换机扩展信息

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    from app.persistence.switch_ext_repository import SwitchExtRepository
    from app.utils.port_name_utils import normalize_port
    sw, _err = _find_switch_or_404(device_id)
    if _err:
        return _err
    repo = SwitchExtRepository()
    data = request.get_json()
    fields = {}
    for k in ("has_ssh", "layer", "switch_role", "uplink_device_id", "core_device_id"):
        if k in data:
            fields[k] = data[k]
    _FIELD_MAP = {
        "is_core": "switch_role",
        "uplink_sw_id": "uplink_device_id",
        "core_sw_id": "core_device_id",
    }
    for old, new in _FIELD_MAP.items():
        if old in data and new not in fields:
            if old == "is_core":
                fields[new] = 0 if data[old] else 1
            else:
                fields[new] = data[old]
    if "uplink_port_ids" in data:
        raw = data["uplink_port_ids"]
        if isinstance(raw, list):
            fields["uplink_port_ids"] = [int(p) for p in raw if p is not None]
        else:
            fields["uplink_port_ids"] = raw
    ext = repo.upsert(sw.device_id, **fields)

    return APIResponse.success(ext.to_dict())


@router.route("/<int:device_id>/ext", methods=["PUT"])
@doc(summary="更新交换机扩展信息", tags=["交换机"], responses={200: "SwitchResponse", 404: "ApiError"})
@permission_required("switch:update")
@transactional
def update_switch_ext(device_id):
    """更新交换机扩展信息

    当 has_ssh=False 且 uplink_* 有值时，自动写 Redis fallback。

    路由参数 device_id 对应 devices.id（统一交换机标识）。
    """
    from app.persistence.switch_ext_repository import SwitchExtRepository
    from app.utils.port_name_utils import normalize_port
    repo = SwitchExtRepository()
    sw, _err = _find_switch_or_404(device_id)
    if _err:
        return _err
    data = request.get_json()
    fields = {}
    for k in ("has_ssh", "layer", "switch_role", "uplink_device_id", "core_device_id"):
        if k in data:
            fields[k] = data[k]
    _FIELD_MAP = {
        "is_core": "switch_role",
        "uplink_sw_id": "uplink_device_id",
        "core_sw_id": "core_device_id",
    }
    for old, new in _FIELD_MAP.items():
        if old in data and new not in fields:
            if old == "is_core":
                fields[new] = 0 if data[old] else 1
            else:
                fields[new] = data[old]
    if "uplink_port_ids" in data:
        raw = data["uplink_port_ids"]
        if isinstance(raw, list):
            fields["uplink_port_ids"] = [int(p) for p in raw if p is not None]
        else:
            fields["uplink_port_ids"] = raw
    ext = repo.upsert(sw.device_id, **fields)

    if not data.get("has_ssh", True) and (data.get("uplink_device_id") or data.get("uplink_sw_id")):
        try:
            from app.services.scan_redis import ScanRedis
            from app.services.network_scanner_service import ScanOrchestrator
            redis_client = ScanOrchestrator._get_redis_client()
            if not redis_client:
                from app.utils.cache import cache_manager
                if cache_manager.primary_storage and cache_manager.primary_storage.redis_client:
                    redis_client = cache_manager.primary_storage.redis_client
            if redis_client:
                sr = ScanRedis(redis_client)
                if sw and sw.ip:
                    uplink_port_ids_raw = data.get("uplink_port_ids", [])
                    uplink_port = ""
                    if uplink_port_ids_raw and isinstance(uplink_port_ids_raw, list):
                        first_port = NetworkPortRepository().find_by_id_orm(uplink_port_ids_raw[0])
                        uplink_port = first_port.port_name if first_port else ""
                    fallback_room_id = None
                    if sw.device and sw.device.cabinet:
                        fallback_room_id = sw.device.cabinet.room_id
                    uplink_device_id_for_fallback = None
                    if ext.device and ext.device.switch_ext:
                        uplink_device_id_for_fallback = ext.device.switch_ext.uplink_device_id
                    if uplink_device_id_for_fallback:
                        sr.fallback_set(fallback_room_id, sw.ip,
                                        uplink_device_id_for_fallback, uplink_port)
        except Exception as e:
            logger.warning("写入降级映射失败: %s", e)

    return APIResponse.success(ext.to_dict())


@router.route("/batch-update", methods=["PUT"])
@doc(summary="批量修改交换机远程信息", tags=["交换机"], responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@permission_required("switch:update")
@transactional
def batch_update_switches():
    """批量修改交换机远程信息

    请求体:
    {
        "device_ids": [1, 2, 3],
        "updates": {
            "port": 22,
            "protocol": "ssh",
            "username": "admin",
            "password": "new_password",
            "device_type": SwitchDeviceTypeCode.HUAWEI,
            "switch_role": 1,
            "layer": 2,
            "authentication_method": "password"
        }
    }

    updates 中仅包含需要修改的字段，未包含的字段不会被更新。
    password 为空时不修改密码（避免用空字符串覆盖加密密码）。
    """
    data = request.get_json()
    device_ids = data.get("device_ids", [])
    updates = data.get("updates", {})

    if not device_ids:
        return APIResponse.error("device_ids 不能为空", ErrorCode.VALIDATION_ERROR, 400)
    if not updates:
        return APIResponse.error("updates 不能为空", ErrorCode.VALIDATION_ERROR, 400)

    switch_fields = {}
    for k in ("port", "protocol", "username", "password", "device_type", "authentication_method", "has_ssh"):
        if k in updates:
            switch_fields[k] = updates[k]

    if "password" in switch_fields and not switch_fields["password"]:
        del switch_fields["password"]

    device_fields = {}
    for k in ("switch_role", "layer"):
        if k in updates:
            device_fields[k] = updates[k]

    repo = SwitchRepository()

    success_ids = []
    failed_items = []

    for device_id in device_ids:
        try:
            sp = db.session.begin_nested()  # savepoint 隔离每台设备的修改
            switch = repo.find_by_device_id(device_id)
            if not switch:
                sp.rollback()
                failed_items.append({"device_id": device_id, "error": "交换机不存在"})
                continue

            if switch_fields:
                repo.update(switch.id, switch_fields)

            if device_fields and switch.device:
                updated = False
                if "switch_role" in device_fields:
                    switch.device.switch_role = device_fields["switch_role"]
                    updated = True
                if "layer" in device_fields:
                    switch.device.layer = device_fields["layer"]
                    updated = True
                if updated:
                    repo.session.flush()

            sp.commit()
            success_ids.append(device_id)
        except Exception as e:
            sp.rollback()
            logger.error("批量更新交换机 device_id=%d 失败: %s", device_id, e)
            failed_items.append({"device_id": device_id, "error": str(e)})

    result = {
        "success_count": len(success_ids),
        "failed_count": len(failed_items),
        "success_ids": success_ids,
        "failed_items": failed_items,
    }

    if failed_items:
        return APIResponse.success(data=result, message=f"部分更新成功：{len(success_ids)} 成功，{len(failed_items)} 失败")
    return APIResponse.success(data=result, message=f"批量更新成功：{len(success_ids)} 台交换机已更新")
