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



@register_capability("ip.mac_lookup")
def ip_mac_lookup(args: Dict[str, Any]) -> dict:
    """按 MAC 地址反查其所在的交换机 / 端口 / 机房。"""
    mac = args.get("mac")
    if not mac:
        raise ValueError("mac 必填")
    from app.persistence.ip_repositories import IPSwitchInfoRepository
    rows = IPSwitchInfoRepository().find_by_mac_address(mac)
    return {
        "mac": mac,
        "count": len(rows),
        "locations": [
            {
                "ip_address": r.ip_address,
                "switch_id": r.switch_id,
                "port": r.port,
                "room_id": r.room_id,
            }
            for r in rows
        ],
    }


@register_capability("ip.ping")
def ip_ping(args: Dict[str, Any]) -> dict:
    """探测单个 IP 是否在线（ICMP ping，内网限速）。"""
    ip = args.get("ip")
    if not ip:
        raise ValueError("ip 必填")
    from app.services.ai.service_factory import get_ip_crud_service
    reachable = get_ip_crud_service().ping_ip(ip)
    return {"ip": ip, "reachable": bool(reachable)}


@register_capability("ip.subnet_utilization")
def ip_subnet_utilization(args: Dict[str, Any]) -> dict:
    """统计某网段的 IP 状态分布（活跃 / 离线 / 封禁 / 空闲）。"""
    cidr = args.get("cidr")
    if not cidr:
        raise ValueError("cidr 必填")
    from app.persistence.ip_repositories import IPManagerRepository
    stats = IPManagerRepository().get_status_statistics_by_cidr(cidr)
    return {"cidr": cidr, **stats}


@register_capability("ip.history")
def ip_history(args: Dict[str, Any]) -> dict:
    """查询某 IP 的归属变更与封禁审计流（合并 allocation / ban 两表）。"""
    ip = args.get("ip")
    if not ip:
        raise ValueError("ip 必填")
    from app.persistence.ip_audit_repository import IPAuditRepository
    from app.services.ip_audit_service import IPAuditService
    return IPAuditService(IPAuditRepository()).query_audit_logs(
        ip_address=ip,
        page=_coerce_int(args.get("page"), default=1) or 1,
        per_page=_coerce_int(args.get("per_page"), default=20) or 20,
    )


@register_capability("ip.allocate_suggest")
def ip_allocate_suggest(args: Dict[str, Any]) -> dict:
    """在指定机房推荐空闲 IP（状态为未使用 / 离线）。"""
    room_id = _coerce_int(args.get("room_id"))
    if room_id is None:
        raise ValueError("room_id 必填")
    limit = _coerce_int(args.get("limit"), default=20) or 20
    from app.core.enums import IPStatus
    from app.persistence.ip_repositories import IPManagerRepository
    ips = IPManagerRepository().find_unused_inactive_ips_by_rooms(
        [room_id], [int(IPStatus.UNUSED), int(IPStatus.INACTIVE)]
    )
    return {
        "room_id": room_id,
        "suggested_count": min(limit, len(ips)),
        "ips": ips[:limit],
    }


@register_capability("ip.reconcile_check")
def ip_reconcile_check(args: Dict[str, Any]) -> dict:
    """只读对账：发现台账（ip_addresses）与实际（定位 / 封禁）的不一致。

    区别于 ip_reconcile_service.reconcile 的写动作，本能力仅统计差异，不写库。
    """
    room_id = _coerce_int(args.get("room_id"))
    if room_id is None:
        raise ValueError("room_id 必填")
    from sqlalchemy import text

    from app.core.enums import IPStatus
    from app.persistence.ip_repositories import IPManagerRepository

    repo = IPManagerRepository()
    active_no_loc = repo.session.execute(text(
        "SELECT COUNT(*) FROM ip_addresses ia "
        "LEFT JOIN ip_switch_info si "
        "  ON si.ip_address = ia.ip_address AND si.room_id = ia.room_id "
        "WHERE ia.room_id = :rid AND ia.status = :active AND si.id IS NULL"
    ), {"rid": room_id, "active": int(IPStatus.ACTIVE)}).scalar() or 0
    banned_no_record = repo.session.execute(text(
        "SELECT COUNT(*) FROM ip_addresses ia "
        "LEFT JOIN ip_ban_records br "
        "  ON br.ip_address = ia.ip_address AND br.room_id = ia.room_id "
        "WHERE ia.room_id = :rid AND ia.status = :banned AND br.id IS NULL"
    ), {"rid": room_id, "banned": int(IPStatus.BANNED)}).scalar() or 0
    return {
        "room_id": room_id,
        "active_without_location": int(active_no_loc),
        "banned_without_record": int(banned_no_record),
        "consistent": int(active_no_loc) == 0 and int(banned_no_record) == 0,
    }


@register_capability("vlan.by_device")
def vlan_by_device(args: Dict[str, Any]) -> list:
    """列出某设备的所有 VLAN（含端口成员预加载）。"""
    device_id = _coerce_int(args.get("device_id"))
    if device_id is None:
        raise ValueError("device_id 必填")
    from app.persistence.vlan_repository import VLANRepository
    from app.services.vlan_service import VLANService
    vlans = VLANService(VLANRepository()).get_by_device(device_id)
    return [v.to_dict() for v in vlans]


@register_capability("vlan.members")
def vlan_members(args: Dict[str, Any]) -> list:
    """列出某 VLAN 的成员端口（按 device_id + vlan_id 定位）。"""
    device_id = _coerce_int(args.get("device_id"))
    vlan_id = _coerce_int(args.get("vlan_id"))
    if device_id is None or vlan_id is None:
        raise ValueError("device_id 与 vlan_id 必填")
    from app.persistence.vlan_repository import VLANRepository
    from app.services.vlan_service import VLANService
    vlan = VLANRepository().find_by_device_and_vlan_id(device_id, vlan_id)
    if vlan is None:
        return []
    return VLANService(VLANRepository()).get_members(vlan.id)



@register_capability("root_cause.analyze")
def root_cause_analyze(args: Dict[str, Any]) -> dict:
    """单设备异常 → 故障域定位（同机柜 / 同机房 / 同上游是否同时异常）。"""
    device_id = _coerce_int(args.get("device_id"))
    metric = args.get("metric")
    if device_id is None:
        raise ValueError("device_id 必填")
    if not metric:
        raise ValueError("metric 必填（异常指标 key，如 cpu_usage）")
    from app.services.ai.root_cause_analyzer import RootCauseAnalyzer
    return RootCauseAnalyzer().analyze_fault_domain(device_id, metric)


@register_capability("capacity.trend")
def capacity_trend(args: Dict[str, Any]) -> dict:
    """查询某设备某指标的历史趋势（均值 / 极值 / 越限点数 + 原始序列）。"""
    from datetime import timedelta

    from app.utils.time_utils import now_utc_naive

    from app.persistence.device_metric_timeseries_repository import (
        DeviceMetricTimeseriesRepository,
    )
    device_id = _coerce_int(args.get("device_id"))
    metric_key = args.get("metric_key")
    if device_id is None:
        raise ValueError("device_id 必填")
    if not metric_key:
        raise ValueError("metric_key 必填")
    hours = _coerce_int(args.get("hours"), default=24) or 24
    index_key = args.get("index_key")  # 可选：端口号等实例索引
    limit = _coerce_int(args.get("limit"), default=500) or 500

    since = now_utc_naive() - timedelta(hours=hours)
    rows = DeviceMetricTimeseriesRepository().list_by_metric(
        device_id, metric_key, index_key=index_key, from_=since, limit=limit,
    )
    series = [r.to_dict() for r in rows]
    nums, breached = [], 0
    for r in rows:
        if r.breached:
            breached += 1
        try:
            nums.append(float(r.value))
        except (TypeError, ValueError):
            pass
    summary = {
        "samples": len(rows),
        "breached_points": breached,
        "avg": round(sum(nums) / len(nums), 2) if nums else None,
        "min": min(nums) if nums else None,
        "max": max(nums) if nums else None,
        "last_value": series[-1]["value"] if series else None,
    }
    return {
        "device_id": device_id,
        "metric_key": metric_key,
        "index_key": index_key,
        "window": {"hours": hours, "from": since.isoformat(),
                   "to": now_utc_naive().isoformat()},
        "summary": summary,
        "series": series,
    }


@register_capability("diag.timeline")
def diag_timeline(args: Dict[str, Any]) -> dict:
    """聚合某设备跨源事件时间线 + Incident 级上下文。

    events（扁平时间线）：监控事件 + 探测可达性告警 + 历史诊断会话。
    incidents（事件上下文）：每个事件附 reason_code（归并原因）、suppressed
    （L2 被抑制的连坐下游）、change（L3 故障前配置变更，回查审计表复算）、
    diagnosis（该事件是否已有进行中/已完成诊断，可直接复用结论）。
    """
    from datetime import timedelta

    from app.utils.time_utils import now_utc_naive

    from extensions import db
    from app.models.device_monitor_probe_events import DeviceMonitorProbeEvents
    from app.models.monitor_incident import MonitorIncident
    from app.services.ai.diagnosis_session_service import DiagnosisSessionService

    device_id = _coerce_int(args.get("device_id"))
    if device_id is None:
        raise ValueError("device_id 必填")
    hours = _coerce_int(args.get("hours"), default=24) or 24
    since = now_utc_naive() - timedelta(hours=hours)

    events: list = []

    incidents = (
        db.session.query(MonitorIncident)
        .filter(MonitorIncident.root_device_id == device_id,
                MonitorIncident.first_alert_at >= since)
        .order_by(MonitorIncident.first_alert_at.asc())
        .all()
    )
    for inc in incidents:
        events.append({
            "ts": inc.first_alert_at.isoformat() if inc.first_alert_at else None,
            "source": "incident",
            "kind": inc.severity,
            "summary": inc.title,
            "status": inc.status,
        })

    probes = (
        db.session.query(DeviceMonitorProbeEvents)
        .filter(DeviceMonitorProbeEvents.device_id == device_id,
                DeviceMonitorProbeEvents.probed_at >= since,
                DeviceMonitorProbeEvents.is_alert.is_(True))
        .order_by(DeviceMonitorProbeEvents.probed_at.asc())
        .all()
    )
    for p in probes:
        events.append({
            "ts": p.probed_at.isoformat() if p.probed_at else None,
            "source": "probe",
            "kind": "unreachable" if not p.reachable else "recovered",
            "summary": "探测" + ("不可达" if not p.reachable else "恢复")
                       + (f"（{p.error}）" if p.error else ""),
            "latency_ms": p.latency_ms,
        })

    for s in DiagnosisSessionService().get_history_by_device(device_id, limit=20):
        events.append({
            "ts": s.get("created_at"),
            "source": "diagnosis",
            "kind": s.get("status"),
            "summary": s.get("question"),
            "skill": s.get("skill_name"),
        })

    events.sort(key=lambda e: e["ts"] or "")

    from app.services.ai.capabilities.device_scope import resolve_visible_scope

    ok, visible, reason = resolve_visible_scope()
    if not ok:
        return {"supported": False, "hint": reason}
    if visible is not None and device_id not in visible:
        return {"supported": False, "hint": "无权查看该设备"}

    from app.services.ai.incident_context import collect_incident_contexts

    incidents = collect_incident_contexts(device_id, since, visible=visible)

    return {
        "device_id": device_id,
        "window": {"hours": hours, "from": since.isoformat(),
                   "to": now_utc_naive().isoformat()},
        "event_count": len(events),
        "events": events,
        "incident_count": len(incidents),
        "incidents": incidents,
    }



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
