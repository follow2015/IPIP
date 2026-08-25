# -*- coding: utf-8 -*-
"""监控总览 / 状态列表 / 告警历史 / 重试 / 监控启停。"""
from flask import current_app, request
from marshmallow import ValidationError as MarshmallowValidationError

from app.api.base import APIResponse, ErrorCode
from app.api.monitor import (
    _alert_list_schema,
    _audit_monitor_enabled,
    _batch_monitor_enabled_schema,
    _device_monitor_enabled_schema,
    logger,
    monitor_bp,
    monitor_service,
)
from app.exceptions.validation import ValidationError
from app.openapi.doc import doc
from app.services.audit_service import AuditService
from app.utils import login_required, permission_required
from app.utils.auth import get_current_user_id
from app.utils.transactional import transactional


@monitor_bp.route("/overview", methods=["GET"])
@doc(summary="监控总览统计", tags=["监控"], responses={200: "MonitorOverviewResponse"})
@login_required
@permission_required("monitor:view")
def get_overview():
    """返回全网监控态势：总数/可达/不可达/抖动/告警盲区/从未可达 + 协议与设备类型分布 + 最近告警。"""
    from app.services.monitoring.monitor_service import get_overview as _get
    threshold = current_app.config.get("MONITOR_CONSECUTIVE_FAILURES_THRESHOLD", 2)
    data = _get(failure_threshold=threshold)
    return APIResponse.success(data=data)


@monitor_bp.route("/statuses", methods=["GET"])
@doc(summary="批量查询设备监控状态", tags=["监控"], responses={200: "MonitorStatusListResponse"})
@login_required
@permission_required("monitor:view")
def list_statuses():
    """分页返回监控状态列表（联表 device_name/type/ip），支持按状态过滤。"""
    status_filter = (request.args.get("status_filter") or "").strip() or None
    allowed_filters = ("unreachable", "flapping", "blindspot", "metric_alerting", "interrupted")
    if status_filter and status_filter not in allowed_filters:
        raise ValidationError(f"status_filter 必须为 {'/'.join(allowed_filters)}")

    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 20)), 1), 100)
    except ValueError:
        raise ValidationError("page/per_page 必须为正整数")

    keyword = (request.args.get("keyword") or "").strip() or None

    from app.services.monitoring.monitor_service import list_statuses as _list
    result = _list(status_filter=status_filter, page=page, per_page=per_page, keyword=keyword)
    return APIResponse.paginated(data=result["items"], page=page, per_page=per_page, total=result["total"])


@monitor_bp.route("/alerts", methods=["GET"])
@doc(summary="查询告警历史", tags=["监控"], responses={200: "MonitorAlertListResponse"})
@login_required
@permission_required("monitor:view")
def list_alerts():
    """分页查询告警投递历史。"""
    raw = {
        "alert_type": (request.args.get("alert_type") or "").strip() or None,
        "severity": (request.args.get("severity") or "").strip() or None,
        "status": (request.args.get("status") or "").strip() or None,
        "device_id": (request.args.get("device_id") or "").strip() or None,
        "start_date": (request.args.get("start_date") or "").strip() or None,
        "end_date": (request.args.get("end_date") or "").strip() or None,
        "scope": (request.args.get("scope") or "").strip() or None,
        "metric_key": (request.args.get("metric_key") or "").strip() or None,
        "index_key": (request.args.get("index_key") or "").strip() or None,
        "page": (request.args.get("page") or "").strip() or None,
        "per_page": (request.args.get("per_page") or "").strip() or None,
    }
    try:
        params = _alert_list_schema.load(raw)
    except MarshmallowValidationError as e:
        raise ValidationError(f"查询参数校验失败: {e.messages}")

    if params.get("scope") == "mine":
        params["user_id"] = get_current_user_id()

    from app.services.monitoring.monitor_service import list_alerts as _list
    result = _list(params)
    return APIResponse.paginated(data=result["items"], page=result["page"], per_page=result["per_page"], total=result["total"])


@monitor_bp.route("/alerts/aggregations", methods=["GET"])
@doc(summary="告警聚合/事件关联", tags=["监控"], responses={200: "MonitorAlertAggregationResponse"})
@login_required
@permission_required("monitor:view")
def list_alert_aggregations():
    """P2-10: 告警聚合视图。按 (alert_type, severity, device_id) 聚类，返回风暴组。

    query 参数:
    - window_minutes: 聚类时间窗口（默认 5）
    - severity: 仅聚合指定级别
    - start_date / end_date: 时间范围
    - only_active: 1/0 仅未关闭（默认 1）
    - max_groups: 最多返回组数（默认 50）
    """
    from app.services.monitoring.monitor_service import aggregate_alerts

    window_minutes = request.args.get("window_minutes", 5, type=int)
    severity = request.args.get("severity") or None
    start_date = request.args.get("start_date") or None
    end_date = request.args.get("end_date") or None
    only_active = request.args.get("only_active", "1") not in ("0", "false", "False")
    max_groups = request.args.get("max_groups", 50, type=int)

    if window_minutes < 1 or window_minutes > 1440:
        raise ValidationError("window_minutes 须在 1~1440 之间")
    if max_groups < 1 or max_groups > 200:
        raise ValidationError("max_groups 须在 1~200 之间")

    data = aggregate_alerts(
        window_minutes=window_minutes,
        start_date=start_date,
        end_date=end_date,
        severity=severity,
        only_active=only_active,
        max_groups=max_groups,
    )
    return APIResponse.success(data=data)


@monitor_bp.route("/alerts/statistics", methods=["GET"])
@doc(summary="告警统计报表", tags=["监控"], responses={200: "MonitorAlertStatisticsResponse"})
@login_required
@permission_required("monitor:view")
def get_alert_statistics():
    """P2-15: 告警多维度统计报表。

    query 参数:
    - start_date / end_date: 时间范围（ISO）
    - device_id: 仅统计指定设备
    - severity: 仅统计指定级别
    - bucket: density 桶粒度（hour/day，默认 hour）
    - top_n: Top N 取多少条（默认 10，最大 50）
    """
    from app.services.monitoring.monitor_service import get_alert_statistics as _stat

    start_date = (request.args.get("start_date") or "").strip() or None
    end_date = (request.args.get("end_date") or "").strip() or None
    severity = (request.args.get("severity") or "").strip() or None
    bucket = (request.args.get("bucket") or "hour").strip()
    if bucket not in ("hour", "day"):
        raise ValidationError("bucket 必须为 hour 或 day")

    device_id = None
    did_raw = (request.args.get("device_id") or "").strip()
    if did_raw:
        try:
            device_id = int(did_raw)
        except ValueError:
            raise ValidationError("device_id 必须为整数")

    top_n = request.args.get("top_n", 10, type=int)
    if top_n < 1 or top_n > 50:
        raise ValidationError("top_n 须在 1~50 之间")

    data = _stat(
        start_date=start_date,
        end_date=end_date,
        device_id=device_id,
        severity=severity,
        bucket=bucket,
        top_n=top_n,
    )
    return APIResponse.success(data=data)


@monitor_bp.route("/alerts/<int:alert_id>", methods=["GET"])
@doc(summary="告警详情", tags=["监控"], responses={200: "MonitorAlertDetail"})
@login_required
@permission_required("monitor:view")
def get_alert_detail(alert_id: int):
    """P1-6: 查询单条告警详情（含 device 展示字段 + acknowledged_* + payload 解析）。"""
    from app.services.monitoring.monitor_service import get_alert_detail as _detail
    data = _detail(alert_id)
    return APIResponse.success(data=data)


@monitor_bp.route("/alerts/<int:alert_id>/retry", methods=["POST"])
@doc(summary="重试失败告警", tags=["监控"], responses={200: "MonitorAlertRetryResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def retry_alert(alert_id: int):
    """乐观锁重试：仅当告警处于 failed 状态时重置为 pending。"""
    from app.services.monitoring.monitor_service import retry_alert as _retry
    data = _retry(alert_id)
    return APIResponse.success(data=data)


@monitor_bp.route("/alerts/<int:alert_id>/ack", methods=["POST"])
@doc(summary="确认/认领告警", tags=["监控"], responses={200: "MonitorAlertAckResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def ack_alert(alert_id: int):
    """G9: 人工确认/认领告警。

    幂等：已确认告警再次确认将刷新 acknowledged_at 与 ack_note。
    不变更 status（保持 sent），仅填充 acknowledged_by/at/note。
    已确认告警不再进入升级扫描（escalation_service 通过 acknowledged_at IS NULL 过滤）。
    """
    from flask import g
    from app.services.monitoring.monitor_service import ack_alert as _ack

    body = request.get_json(silent=True) or {}
    note = body.get("note")
    if note is not None and not isinstance(note, str):
        raise ValidationError("note 必须为字符串")

    current_user = getattr(g, "current_user", None) or {}
    user = current_user.get("username") or current_user.get("user_identifier") or "unknown"
    data = _ack(alert_id, user=user, note=note)

    try:
        AuditService().log(
            user_id=get_current_user_id(),
            action="monitor:alert:ack",
            resource="monitor_alert",
            detail={"alert_id": alert_id, "acknowledged_by": user, "ack_note": note},
            ip_address=request.remote_addr,
        )
    except Exception:
        logger.warning("告警确认审计记录失败", exc_info=True)

    return APIResponse.success(data=data)


@monitor_bp.route("/alerts/<int:alert_id>/close", methods=["POST"])
@doc(summary="手动关闭告警", tags=["监控"], responses={200: "MonitorAlertCloseResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def close_alert(alert_id: int):
    """P2-16: 手动关闭告警。

    幂等：已关闭告警再次关闭将刷新 closed_at 与 close_reason。
    不变更 status（保持 sent），仅填充 closed_by/at/reason。
    已关闭告警不再计入活跃告警（前端按 closed_at IS NULL 过滤）。
    """
    from flask import g
    from app.services.monitoring.monitor_service import close_alert as _close

    body = request.get_json(silent=True) or {}
    reason = body.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise ValidationError("reason 必须为字符串")

    current_user = getattr(g, "current_user", None) or {}
    user = current_user.get("username") or current_user.get("user_identifier") or "unknown"
    data = _close(alert_id, user=user, reason=reason)

    try:
        AuditService().log(
            user_id=get_current_user_id(),
            action="monitor:alert:close",
            resource="monitor_alert",
            detail={"alert_id": alert_id, "closed_by": user, "close_reason": reason},
            ip_address=request.remote_addr,
        )
    except Exception:
        logger.warning("告警关闭审计记录失败", exc_info=True)

    return APIResponse.success(data=data)


@monitor_bp.route("/alerts/batch-ack", methods=["POST"])
@doc(summary="批量确认/认领告警", tags=["监控"], responses={200: "MonitorAlertBatchAckResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def batch_ack_alerts():
    """G9 批量确认/认领告警。幂等。"""
    from flask import g
    from app.services.monitoring.monitor_service import batch_ack_alert as _batch_ack

    body = request.get_json(silent=True) or {}
    alert_ids = body.get("alert_ids")
    if not isinstance(alert_ids, list) or not alert_ids:
        raise ValidationError("alert_ids 必须是非空数组")
    if len(alert_ids) > 500:
        raise ValidationError("单次批量最多 500 条")
    note = body.get("note")
    if note is not None and not isinstance(note, str):
        raise ValidationError("note 必须为字符串")

    current_user = getattr(g, "current_user", None) or {}
    user = current_user.get("username") or current_user.get("user_identifier") or "unknown"
    data = _batch_ack([int(i) for i in alert_ids], user=user, note=note)

    try:
        AuditService().log(
            user_id=get_current_user_id(),
            action="monitor:alert:batch_ack",
            resource="monitor_alert",
            detail={"alert_ids": alert_ids, "acknowledged": data["acknowledged"], "ack_note": note},
            ip_address=request.remote_addr,
        )
    except Exception:
        logger.warning("批量告警确认审计记录失败", exc_info=True)

    return APIResponse.success(data=data)


@monitor_bp.route("/alerts/batch-retry", methods=["POST"])
@doc(summary="批量重试失败告警", tags=["监控"], responses={200: "MonitorAlertBatchRetryResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def batch_retry_alerts():
    """批量乐观锁重试：仅当 status=='failed' 时重置为 pending。"""
    from app.services.monitoring.monitor_service import batch_retry_alert as _batch_retry

    body = request.get_json(silent=True) or {}
    alert_ids = body.get("alert_ids")
    if not isinstance(alert_ids, list) or not alert_ids:
        raise ValidationError("alert_ids 必须是非空数组")
    if len(alert_ids) > 500:
        raise ValidationError("单次批量最多 500 条")

    data = _batch_retry([int(i) for i in alert_ids])

    try:
        AuditService().log(
            user_id=get_current_user_id(),
            action="monitor:alert:batch_retry",
            resource="monitor_alert",
            detail={"alert_ids": alert_ids, "retried": data["retried"], "skipped": data["skipped"]},
            ip_address=request.remote_addr,
        )
    except Exception:
        logger.warning("批量告警重试审计记录失败", exc_info=True)

    return APIResponse.success(data=data)


@monitor_bp.route("/alerts/batch-close", methods=["POST"])
@doc(summary="批量手动关闭告警", tags=["监控"], responses={200: "MonitorAlertBatchCloseResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def batch_close_alerts():
    """P2-16: 批量手动关闭告警。幂等。"""
    from flask import g
    from app.services.monitoring.monitor_service import batch_close_alert as _batch_close

    body = request.get_json(silent=True) or {}
    alert_ids = body.get("alert_ids")
    if not isinstance(alert_ids, list) or not alert_ids:
        raise ValidationError("alert_ids 必须是非空数组")
    if len(alert_ids) > 500:
        raise ValidationError("单次批量最多 500 条")
    reason = body.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise ValidationError("reason 必须为字符串")

    current_user = getattr(g, "current_user", None) or {}
    user = current_user.get("username") or current_user.get("user_identifier") or "unknown"
    data = _batch_close([int(i) for i in alert_ids], user=user, reason=reason)

    try:
        AuditService().log(
            user_id=get_current_user_id(),
            action="monitor:alert:batch_close",
            resource="monitor_alert",
            detail={"alert_ids": alert_ids, "closed": data["closed"], "close_reason": reason},
            ip_address=request.remote_addr,
        )
    except Exception:
        logger.warning("批量告警关闭审计记录失败", exc_info=True)

    return APIResponse.success(data=data)


@monitor_bp.route("/devices/<int:device_id>/monitor-enabled", methods=["PATCH"])
@doc(summary="设备级监控启停", tags=["监控"], responses={200: "MonitorDeviceMonitorEnabledResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def patch_device_monitor_enabled(device_id: int):
    """设备级监控启停。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = _device_monitor_enabled_schema.load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")

    enabled = data["enabled"]
    result = monitor_service.set_device_monitor_enabled(device_id, enabled)
    _audit_monitor_enabled(device_id, enabled)
    return APIResponse.success(data=result)


@monitor_bp.route("/batch-monitor-enabled", methods=["PATCH"])
@doc(summary="批量设备级监控启停", tags=["监控"], responses={200: "MonitorDeviceMonitorEnabledResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def patch_batch_monitor_enabled():
    """批量设备级监控启停。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = _batch_monitor_enabled_schema.load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")

    device_ids = data["device_ids"]
    enabled = data["enabled"]
    result = monitor_service.batch_set_monitor_enabled(device_ids, enabled)

    try:
        AuditService().log(
            user_id=get_current_user_id(),
            action="monitor:batch:monitor_enabled",
            resource="monitor_device",
            detail={"device_ids": device_ids, "monitor_enabled": enabled, **result},
            ip_address=request.remote_addr,
        )
    except Exception:
        logger.warning("批量监控启停审计记录失败", exc_info=True)

    return APIResponse.success(
        data=result,
        message=f"已更新 {result['updated']} 台，跳过 {result['skipped']} 台",
    )
