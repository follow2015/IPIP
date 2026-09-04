# -*- coding: utf-8 -*-
"""内置能力注册：复用既有 service 层，注册为 capability 供技能 YAML 引用。

技能模块（YAML）只引用这些已注册能力名，绝不执行任意代码。
"""
from typing import Any, Dict

from app.services.ai.capabilities.registry import register_capability
from app.utils.logging import get_logger

logger = get_logger(__name__)

_MAX_QUERY_CHARS = 4000

_ALL_DEVICES_PAGE_SIZE = 10000


@register_capability("monitor.get_devices_summary")
def get_devices_summary(args):
    from app.services.ai.service_factory import get_device_service, get_monitor_service
    ids = args.get("device_ids")
    devs = get_device_service().get_all_devices(
        page_size=_ALL_DEVICES_PAGE_SIZE)["devices"]
    if ids:
        devs = [d for d in devs if d["id"] in ids]
    return get_monitor_service().get_devices_monitor_summary([d["id"] for d in devs])


@register_capability("builtin.threshold_filter")
def threshold_filter(args):
    items = args["summary"].get("devices", [])
    t = args.get("thresholds", {})
    out = []
    for it in items:
        issues = []
        if it.get("cpu", 0) > t.get("cpu_pct", 1e9):
            issues.append(f"CPU {it['cpu']}%")
        if it.get("temp", 0) > t.get("temp_c", 1e9):
            issues.append(f"温度 {it['temp']}°C")
        if it.get("mem", 0) > t.get("mem_pct", 1e9):
            issues.append(f"内存 {it['mem']}%")
        if issues:
            out.append({"device": it.get("device_name"), "issues": issues})
    return out


@register_capability("devices.top_cpu")
def top_cpu(args: Dict[str, Any]) -> list:
    """返回 CPU 使用率最高的设备。"""
    from app.services.ai.service_factory import get_device_service, get_monitor_service
    limit = int(args.get("limit", 5))
    all_devices = get_device_service().get_all_devices(
        page_size=_ALL_DEVICES_PAGE_SIZE)["devices"]
    device_ids = [d["id"] for d in all_devices]
    summary = get_monitor_service().get_devices_monitor_summary(device_ids)
    items = sorted(summary.get("devices", []), key=lambda x: x.get("cpu", 0), reverse=True)
    return items[:limit]


@register_capability("devices.count_by_room")
def count_by_room(args: Dict[str, Any]) -> dict:
    """按机房统计设备数量。

    N4 修复：原逐机房 get_device_count_by_room(room.id) 为 N+1 查询。
    改为一次 get_all_devices() + get_all_rooms()，在内存按 room_id 分组计数，
    把 N+1 次 DB 查询降为 2 次。

    注意：get_all_devices() 返回分页字典，需取 ["devices"] 才是设备列表；
    且默认 page_size=20，统计场景必须放大页大小，否则只统计到前 20 台。
    """
    from app.services.ai.service_factory import get_device_service, get_room_service
    rooms = get_room_service().get_all_rooms()
    devices = get_device_service().get_all_devices(
        page_size=_ALL_DEVICES_PAGE_SIZE)["devices"]
    counts: Dict[str, int] = {}
    bucket: Dict[int, int] = {}
    for d in devices:
        rid = d.get("room_id")
        if rid is None:
            continue
        bucket[rid] = bucket.get(rid, 0) + 1
    for r in rooms:
        counts[r["name"]] = bucket.get(r["id"], 0)
    return counts



@register_capability("devices.statistics")
def devices_statistics(args: Dict[str, Any]) -> dict:
    """设备资产统计（类型分布、状态、机房等）。"""
    from app.services.ai.service_factory import get_device_service
    return get_device_service().get_device_statistics()


@register_capability("devices.search")
def devices_search(args: Dict[str, Any]) -> dict:
    """按关键字 / 类型 / 状态 / 机柜 / 客户检索设备（分页）。"""
    from app.services.ai.service_factory import get_device_service
    return get_device_service().search_devices(
        keyword=args.get("keyword"),
        device_type=args.get("device_type"),
        status=args.get("status"),
        cabinet_id=_coerce_int(args.get("cabinet_id")),
        customer_id=_coerce_int(args.get("customer_id")),
        page=_coerce_int(args.get("page"), default=1) or 1,
        page_size=_coerce_int(args.get("page_size"), default=20) or 20,
    )


@register_capability("rooms.list")
def rooms_list(args: Dict[str, Any]) -> list:
    """列出所有机房。"""
    from app.services.ai.service_factory import get_room_service
    return get_room_service().get_all_rooms()



@register_capability("cabinets.global_statistics")
def cabinets_global_statistics(args: Dict[str, Any]) -> dict:
    """机柜全局统计（总数、U 位利用率、空间分布等）。"""
    from app.services.ai.service_factory import get_cabinet_service
    return get_cabinet_service().get_global_statistics()


@register_capability("cabinets.utilization")
def cabinet_utilization(args: Dict[str, Any]) -> dict:
    """单台机柜利用率（已用 U / 总 U / 设备数）。"""
    from app.services.ai.service_factory import get_cabinet_service
    cabinet_id = _coerce_int(args.get("cabinet_id"))
    if cabinet_id is None:
        raise ValueError("cabinet_id 必填")
    result = get_cabinet_service().get_utilization(cabinet_id)
    if result is None:
        raise ValueError(f"机柜不存在: {cabinet_id}")
    return result



@register_capability("ip.ban_consistency")
def ip_ban_consistency(args: Dict[str, Any]) -> dict:
    """封禁一致性核对：发现 ip_ban_records 与 ip_manager 状态不一致 / 超时记录。"""
    from app.services.ip_ban_service import check_ban_consistency
    return check_ban_consistency(room_id=_coerce_int(args.get("room_id")))


@register_capability("ip.list")
def ip_list(args: Dict[str, Any]) -> dict:
    """按关键字 / 客户 / 机房 / 状态分页检索 IP。"""
    from app.services.ai.service_factory import get_ip_crud_service
    return get_ip_crud_service().get_ip_addresses_paginated(
        keyword=args.get("keyword"),
        customer_id=_coerce_int(args.get("customer_id")),
        room_id=_coerce_int(args.get("room_id")),
        status=_coerce_int(args.get("status")),
        page=_coerce_int(args.get("page"), default=1) or 1,
        page_size=_coerce_int(args.get("page_size"), default=20) or 20,
    )



@register_capability("monitor.overview")
def monitor_overview(args: Dict[str, Any]) -> dict:
    """监控总览：在线 / 离线 / 中断统计、按协议与设备类型分布、近期告警。"""
    from app.services.monitoring.monitor_service import get_overview
    return get_overview(failure_threshold=_coerce_int(args.get("failure_threshold"), default=2) or 2)


@register_capability("monitor.list_alerts")
def monitor_list_alerts(args: Dict[str, Any]) -> dict:
    """分页查询告警投递历史，支持类型 / 级别 / 状态 / 设备 / 时间范围过滤。"""
    from app.services.monitoring.monitor_service import list_alerts
    return list_alerts({
        "page": _coerce_int(args.get("page"), default=1) or 1,
        "per_page": _coerce_int(args.get("per_page"), default=20) or 20,
        "alert_type": args.get("alert_type"),
        "severity": args.get("severity"),
        "status": args.get("status"),
        "device_id": _coerce_int(args.get("device_id")),
        "start_date": args.get("start_date"),
        "end_date": args.get("end_date"),
    })


@register_capability("monitor.alert_statistics")
def monitor_alert_statistics(args: Dict[str, Any]) -> dict:
    """告警多维度统计报表（按时间桶密度 + Top N 设备 / 类型）。"""
    from app.services.monitoring.monitor_service import get_alert_statistics
    return get_alert_statistics(
        start_date=args.get("start_date"),
        end_date=args.get("end_date"),
        device_id=_coerce_int(args.get("device_id")),
        severity=args.get("severity"),
        bucket=args.get("bucket") or "hour",
        top_n=_coerce_int(args.get("top_n"), default=10) or 10,
    )


@register_capability("monitor.unreachable_devices")
def monitor_unreachable_devices(args: Dict[str, Any]) -> list:
    """返回不可达设备清单（ping 或 监控协议不通），含设备名 / 管理 IP / 协议。

    仅把明确探测为不可达（False）的设备列为异常；从未探测（None）不误报。
    """
    from app.services.ai.service_factory import get_device_service, get_monitor_service
    all_devs = get_device_service().get_all_devices(
        page_size=_ALL_DEVICES_PAGE_SIZE)["devices"]
    device_ids = [d["id"] for d in all_devs]
    devs = {d["id"]: d for d in all_devs}
    summary = get_monitor_service().get_devices_monitor_summary(device_ids)
    out = []
    for did, s in summary.items():
        ping = s.get("ping_reachable")
        mon = s.get("monitor_reachable")
        if ping is False or mon is False:
            d = devs.get(did, {})
            out.append({
                "device_id": did,
                "device_name": d.get("device_name"),
                "management_ip": d.get("management_ip"),
                "ping_reachable": ping,
                "monitor_reachable": mon,
                "monitor_protocol": s.get("monitor_protocol"),
            })
    return out



@register_capability("ports.by_device")
def ports_by_device(args: Dict[str, Any]) -> list:
    """列出某设备的全部端口。"""
    from app.services.network_port_service import NetworkPortService
    from app.persistence.switch_port_repository import NetworkPortRepository
    device_id = _coerce_int(args.get("device_id"))
    if device_id is None:
        raise ValueError("device_id 必填")
    return NetworkPortService(NetworkPortRepository()).get_ports_by_device(device_id)


@register_capability("ports.available")
def ports_available(args: Dict[str, Any]) -> list:
    """列出某设备的空闲端口。"""
    from app.services.network_port_service import NetworkPortService
    from app.persistence.switch_port_repository import NetworkPortRepository
    device_id = _coerce_int(args.get("device_id"))
    if device_id is None:
        raise ValueError("device_id 必填")
    return NetworkPortService(NetworkPortRepository()).get_available_ports(device_id)


def _coerce_int(value, default=None):
    """把占位符可能传入的字符串安全转为 int；None / 空返回 default。"""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default



@register_capability("devices.get_by_id")
def get_device_by_id(args: Dict[str, Any]) -> dict:
    """按 ID 查设备详情（A9：经数据域校验后才查库）。

    只读能力，data_scope 服务故障时按 fail-open 放行（不因鉴权旁路阻断查询）。
    """
    device_id = _coerce_int(args.get("device_id"))
    if device_id is None:
        raise ValueError("device_id 必填")

    from app.services.ai.capabilities.device_scope import check_device_access
    allowed, reason = check_device_access(device_id)
    if not allowed:
        return {"supported": False, "hint": reason}

    from app.services.ai.service_factory import get_device_service
    return get_device_service().get_device_by_id(device_id)


@register_capability("monitor.get_device_status")
def get_device_status(args: Dict[str, Any]) -> dict:
    """查单设备监控状态。"""
    from app.services.ai.service_factory import get_monitor_service
    device_id = _coerce_int(args.get("device_id"))
    if device_id is None:
        raise ValueError("device_id 必填")
    return get_monitor_service().get_device_status(device_id)


@register_capability("rag.retrieve")
def rag_retrieve(args: Dict[str, Any]) -> list:
    """RAG 混合检索：返回与 query 最相关的 top_k 个文档片段。

    Phase 1.3：改调 hybrid_search（向量+关键词两路召回），并支持 domain 参数过滤。
    设计文档第十三节要求：domain 过滤必须实测生效，不能只检查代码写了 domain 就当作生效。
    hybrid_search 内部把 domain 传给 keyword_search（FTS5 WHERE domain=?），
    向量检索目前不按 domain 过滤（chromadb collection 单一，未按 domain 分库），
    故 domain 过滤仅在关键词路生效——这是已知限制，在 evidence 中标注 source 区分。
    """
    from app.services.ai.rag_store import get_rag_store
    from app.services.ai.prompt_guard import sanitize_user_input, truncate_text
    query = truncate_text(sanitize_user_input(args.get("query", "")), _MAX_QUERY_CHARS)
    top_k = _coerce_int(args.get("top_k"), default=3) or 3
    domain = args.get("domain") or "code_wiki"
    chunks = get_rag_store().hybrid_search(query, domain=domain, top_k=top_k)
    if not chunks:
        return []
    if all(isinstance(c, dict) for c in chunks):
        return chunks
    return [c if isinstance(c, str) else c.get("text", str(c)) for c in chunks]


@register_capability("ticket.create_from_inspection", requires_permission="ai:execute")
def create_ticket_from_inspection(args: Dict[str, Any]) -> dict:
    """根据巡查结论创建工单（写操作，需 ai:execute 权限）。

    当前为占位实现：记录到审计日志并返回工单号。后续接入真实工单系统时替换。
    """
    device_id = _coerce_int(args.get("device_id"))
    conclusion = args.get("conclusion", "")
    logger.info("ticket created from inspection: device_id=%s conclusion=%s", device_id, conclusion)
    return {"ticket_id": f"INS-{device_id}", "device_id": device_id, "conclusion": conclusion}


@register_capability("builtin.noop")
def builtin_noop(args: Dict[str, Any]) -> None:
    """空操作：给 route 步骤的 normal 分支一个合法跳转目标。"""
    return None
