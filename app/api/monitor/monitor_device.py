# -*- coding: utf-8 -*-
"""设备监控状态 / 历史 / 趋势 / 手动探测 / 批量探测。"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import request

from extensions import db

from app.api.base import APIResponse, ErrorCode
from app.exceptions.business import BusinessLogicError
from app.exceptions.validation import ValidationError
from app.api.monitor import (
    _ALLOWED_PROTOCOLS,
    _credential_upsert_schema,
    _audit_credential_change,
    credential_repo,
    credential_service,
    device_repo,
    logger,
    monitor_bp,
    monitor_service,
    monitor_ts_repo,
    status_repo,
    _metric_alert_state_repo,
)
from app.openapi.doc import doc
from app.schemas.monitor import MonitorCheckBatchSchema
from app.services.monitoring.monitor_service import get_probe_trends as _probe_trends
from app.utils import login_required, permission_required
from app.utils.transactional import transactional


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """解析查询参数中的 ISO 时间；非法格式抛 ValueError。"""
    if not value:
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    return dt.replace(tzinfo=None)


@monitor_bp.route("/devices/<int:device_id>/status", methods=["GET"])
@doc(summary="查询设备监控状态", tags=["监控"], responses={200: "DeviceMonitorStatusResponse"})
@login_required
@permission_required("monitor:view")
def get_device_status(device_id: int):
    """查询设备监控状态（含指标告警聚合）。"""
    data = monitor_service.get_device_status_with_alerts(device_id)
    return APIResponse.success(data=data)


@monitor_bp.route("/devices/<int:device_id>/metric-dashboard", methods=["GET"])
@doc(summary="查询设备监控数据（Zabbix 流量 + 模板指标状态）", tags=["监控"], responses={200: "DeviceMetricDashboardResponse"})
@login_required
@permission_required("monitor:view")
def get_device_metric_dashboard(device_id: int):
    """查询设备监控数据聚合：凭据/模板组命中情况 + 模板指标当前状态。

    供前端「监控数据」卡片使用：上半部分为 Zabbix 端口流量（has_zabbix 控制），
    下半部分为模板指标状态（metric_status，grouped 标记是否命中模板组）。
    """
    data = monitor_service.get_device_metric_dashboard(device_id)
    return APIResponse.success(data=data)


@monitor_bp.route("/devices/<int:device_id>/credentials", methods=["PUT"])
@doc(summary="配置监控凭据", tags=["监控"], responses={200: "MonitorCredentialConfigResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def put_credentials(device_id: int):
    """配置（新增/更新）某设备的单协议监控凭据。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")

    errors = _credential_upsert_schema.validate(body)
    if errors:
        raise ValidationError(f"请求参数校验失败: {errors}")

    protocol = body["protocol"]
    payload = body["payload"]
    name = body.get("name")
    device_ids = body.get("device_ids") or [device_id]

    for did in device_ids:
        credential_service.upsert(did, protocol, payload, name)
    _audit_credential_change(
        "monitor_credential:upsert",
        {"protocol": protocol, "device_ids": device_ids, "count": len(device_ids), "name": name},
    )
    return APIResponse.success(data={"configured": True, "protocol": protocol, "linked": len(device_ids)})


@monitor_bp.route("/devices/<int:device_id>/history", methods=["GET"])
@doc(summary="查询设备探测历史时序", tags=["监控"], responses={200: "MonitorProbeHistoryResponse"})
@login_required
@permission_required("monitor:view")
def get_probe_history(device_id: int):
    """分页返回设备探测历史时序（时间升序），支持时间范围 / 协议过滤。"""
    raw_from = (request.args.get("from") or "").strip() or None
    raw_to = (request.args.get("to") or "").strip() or None
    protocol = (request.args.get("protocol") or "").strip() or None
    if protocol and protocol not in _ALLOWED_PROTOCOLS:
        raise ValidationError(f"protocol 必须为 {sorted(_ALLOWED_PROTOCOLS)}")
    try:
        from_ = _parse_dt(raw_from)
        to_ = _parse_dt(raw_to)
    except ValueError:
        raise ValidationError("from/to 必须为合法 ISO datetime")
    if from_ and to_ and from_ > to_:
        raise ValidationError("from 不能晚于 to")

    try:
        limit = min(max(int(request.args.get("limit", 500)), 1), 2000)
    except ValueError:
        raise ValidationError("limit 必须为正整数")

    if to_ is None:
        to_ = datetime.now(timezone.utc).replace(tzinfo=None)
    if from_ is None:
        from_ = to_ - timedelta(days=7)

    items = monitor_ts_repo.list_events(
        device_id, from_=from_, to_=to_, protocol=protocol, limit=limit,
    )
    return APIResponse.success(data={
        "items": items,
        "total": len(items),
        "from": from_.isoformat(),
        "to": to_.isoformat(),
        "protocol": protocol,
    })


@monitor_bp.route("/devices/<int:device_id>/trends", methods=["GET"])
@doc(summary="查询设备监控趋势统计", tags=["监控"], responses={200: "MonitorProbeTrendsResponse"})
@login_required
@permission_required("monitor:view")
def get_probe_trends(device_id: int):
    """聚合统计（供趋势卡片）：可达率 / 延迟统计 / 不可达周期数。"""
    raw_from = (request.args.get("from") or "").strip() or None
    raw_to = (request.args.get("to") or "").strip() or None
    protocol = (request.args.get("protocol") or "").strip() or None
    if protocol and protocol not in _ALLOWED_PROTOCOLS:
        raise ValidationError(f"protocol 必须为 {sorted(_ALLOWED_PROTOCOLS)}")
    try:
        from_ = _parse_dt(raw_from)
        to_ = _parse_dt(raw_to)
    except ValueError:
        raise ValidationError("from/to 必须为合法 ISO datetime")
    if from_ and to_ and from_ > to_:
        raise ValidationError("from 不能晚于 to")

    if to_ is None:
        to_ = datetime.now(timezone.utc).replace(tzinfo=None)
    if from_ is None:
        from_ = to_ - timedelta(days=7)

    agg = _probe_trends(
        device_id, from_=from_, to_=to_, protocol=protocol
    )
    return APIResponse.success(data=agg)


@monitor_bp.route("/devices/<int:device_id>/check", methods=["POST"])
@doc(summary="手动触发设备探测", tags=["监控"], responses={200: "MonitorProbeResultResponse"})
@login_required
@permission_required("monitor:config")
def check_device_now(device_id: int):
    """手动触发一次探测。网络 I/O 在事务外，落库 + 告警在事务内（P0-6）。

    事务边界（勿合并回整体 @transactional）：
    1. 事务外：读设备 + 预加载探测所需 lazy 关系，随后 db.session.remove()
       释放 DB 连接；
    2. 事务外：probe_device 执行最长 timeout+3s 的网络探测——期间不持有
       DB 连接与未提交事务，探测风暴不致耗尽连接池；
    3. 事务内：_persist_check_result 以 @transactional 收口 apply_result
       （状态 upsert + 时序事件 + 告警入箱原子提交）。
    """
    if not monitor_service.check_probe_cooldown(device_id):
        raise BusinessLogicError("该设备探测冷却中，请稍后再试", status_code=429)

    device = device_repo.find_by_id_or_404(device_id)
    _ = device.hardware
    _ = getattr(device.hardware, "ipmi_address", None) if device.hardware else None
    db.session.expunge(device)
    db.session.commit()

    probed = monitor_service.probe_device(device)
    if probed is None:
        raise BusinessLogicError("设备未配置监控凭据", status_code=400)
    result, protocol = probed
    if getattr(result, "skipped", False):
        raise BusinessLogicError(
            f"本轮探测被跳过：{result.error}（监控基础设施 / DNS 解析问题，非设备不可达）",
            status_code=409,
        )
    cfg = monitor_service.get_probe_runtime_config()
    return _persist_check_result(device_id, result, protocol, cfg)


@transactional
def _persist_check_result(device_id: int, result, protocol: str, cfg: dict):
    """事务内收口：落库 + 告警（apply_result 唯一入口）。

    设备可能在探测期间被删除 → find_by_id_or_404 抛 404，由 @transactional
    统一回滚上浮。
    """
    device = device_repo.find_by_id_or_404(device_id)
    monitor_service.apply_result(device, result, protocol, **cfg)
    return APIResponse.success(data=_probe_result_to_dict(result))


@monitor_bp.route("/check-batch", methods=["POST"])
@doc(summary="批量手动触发设备探测", tags=["监控"], responses={200: "MonitorCheckBatchResponse"})
@login_required
@permission_required("monitor:config")
def check_batch():
    """批量手动触发探测（最多 50 台）。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")

    errors = MonitorCheckBatchSchema().validate(body)
    if errors:
        raise ValidationError(f"请求参数校验失败: {errors}")

    device_ids = body["device_ids"]
    data = monitor_service.check_batch(device_ids)
    return APIResponse.success(data=data)


def _probe_result_to_dict(result) -> dict:
    """将 ProbeResult 序列化为响应字典。"""
    return {
        "reachable": result.reachable,
        "latency_ms": result.latency_ms,
        "extra": result.extra,
        "error": result.error,
    }


