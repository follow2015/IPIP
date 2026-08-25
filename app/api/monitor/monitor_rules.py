# -*- coding: utf-8 -*-
"""静默规则 + 阈值覆盖 + 升级策略 CRUD。"""
from flask import request
from marshmallow import ValidationError as MarshmallowValidationError

from app.api.base import APIResponse
from app.api.monitor import monitor_bp
from app.exceptions.validation import ValidationError
from app.openapi.doc import doc
from app.schemas.monitor import (
    DeviceMetricOverrideUpsertSchema,
    MonitorAlertDependencyRuleCreateSchema,
    MonitorAlertDependencyRuleUpdateSchema,
    MonitorEscalationPolicyCreateSchema,
    MonitorEscalationPolicyUpdateSchema,
    MonitorSilenceRuleCreateSchema,
    MonitorSilenceRuleUpdateSchema,
    MonitorSlaTargetCreateSchema,
    MonitorSlaTargetUpdateSchema,
)
from app.utils import login_required, permission_required
from app.utils.auth import get_current_user_id
from app.utils.transactional import transactional


@monitor_bp.route("/silence-rules", methods=["GET"])
@doc(summary="列出全部静默规则", tags=["监控"], responses={200: "MonitorSilenceRuleItem"})
@login_required
@permission_required("monitor:view")
def list_silence_rules():
    from app.services.monitoring.silence_service import list_silence_rules as _list
    items = _list()
    return APIResponse.paginated(data=items, page=1, per_page=len(items) or 1, total=len(items))


@monitor_bp.route("/silence-rules", methods=["POST"])
@doc(summary="创建静默规则", tags=["监控"], responses={200: "MonitorSilenceRuleItem"})
@login_required
@permission_required("monitor:config")
@transactional
def create_silence_rule():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = MonitorSilenceRuleCreateSchema().load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")
    from app.services.monitoring.silence_service import create_rule as _create
    result = _create(data, user_id=get_current_user_id())
    return APIResponse.success(data=result)


@monitor_bp.route("/silence-rules/<int:rule_id>", methods=["PATCH"])
@doc(summary="更新静默规则", tags=["监控"], responses={200: "MonitorSilenceRuleItem"})
@login_required
@permission_required("monitor:config")
@transactional
def update_silence_rule(rule_id: int):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = MonitorSilenceRuleUpdateSchema().load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")
    from app.services.monitoring.silence_service import update_rule as _update
    result = _update(rule_id, data)
    return APIResponse.success(data=result)


@monitor_bp.route("/silence-rules/<int:rule_id>", methods=["DELETE"])
@doc(summary="删除静默规则", tags=["监控"], responses={200: "MonitorSilenceRuleItem"})
@login_required
@permission_required("monitor:config")
@transactional
def delete_silence_rule(rule_id: int):
    from app.services.monitoring.silence_service import delete_rule as _delete
    data = _delete(rule_id)
    return APIResponse.success(data=data)


@monitor_bp.route("/threshold-overrides", methods=["GET"])
@doc(summary="列出阈值覆盖", tags=["监控"], responses={200: "DeviceMetricOverrideItem"})
@login_required
@permission_required("monitor:view")
def list_threshold_overrides():
    device_id = request.args.get("device_id", type=int)
    metric_key = request.args.get("metric_key")
    from app.services.monitoring.threshold_override_service import list_threshold_overrides as _list
    items = _list(device_id=device_id, metric_key=metric_key)
    return APIResponse.paginated(data=items, page=1, per_page=len(items) or 1, total=len(items))


@monitor_bp.route("/threshold-overrides", methods=["POST"])
@doc(summary="upsert 阈值覆盖", tags=["监控"], responses={200: "DeviceMetricOverrideItem"})
@login_required
@permission_required("monitor:config")
@transactional
def upsert_threshold_override():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = DeviceMetricOverrideUpsertSchema().load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")
    from app.services.monitoring.threshold_override_service import upsert as _upsert
    result = _upsert(data)
    return APIResponse.success(data=result)


@monitor_bp.route("/threshold-overrides/<int:override_id>", methods=["DELETE"])
@doc(summary="删除阈值覆盖", tags=["监控"], responses={200: "DeviceMetricOverrideItem"})
@login_required
@permission_required("monitor:config")
@transactional
def delete_threshold_override(override_id: int):
    from app.services.monitoring.threshold_override_service import delete as _delete
    data = _delete(override_id)
    return APIResponse.success(data=data)


@monitor_bp.route("/escalation-policies", methods=["GET"])
@doc(summary="列出全部升级策略", tags=["监控"], responses={200: "MonitorEscalationPolicyItem"})
@login_required
@permission_required("monitor:view")
def list_escalation_policies():
    from app.services.monitoring.escalation_service import list_escalation_policies as _list
    items = _list()
    return APIResponse.paginated(data=items, page=1, per_page=len(items) or 1, total=len(items))


@monitor_bp.route("/escalation-policies", methods=["POST"])
@doc(summary="创建升级策略", tags=["监控"], responses={200: "MonitorEscalationPolicyItem"})
@login_required
@permission_required("monitor:config")
@transactional
def create_escalation_policy():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = MonitorEscalationPolicyCreateSchema().load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")
    from app.services.monitoring.escalation_service import create_policy as _create
    result = _create(data)
    return APIResponse.success(data=result)


@monitor_bp.route("/escalation-policies/<int:policy_id>", methods=["PATCH"])
@doc(summary="更新升级策略", tags=["监控"], responses={200: "MonitorEscalationPolicyItem"})
@login_required
@permission_required("monitor:config")
@transactional
def update_escalation_policy(policy_id: int):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = MonitorEscalationPolicyUpdateSchema().load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")
    from app.services.monitoring.escalation_service import update_policy as _update
    result = _update(policy_id, data)
    return APIResponse.success(data=result)


@monitor_bp.route("/escalation-policies/<int:policy_id>", methods=["DELETE"])
@doc(summary="删除升级策略", tags=["监控"], responses={200: "MonitorEscalationPolicyItem"})
@login_required
@permission_required("monitor:config")
@transactional
def delete_escalation_policy(policy_id: int):
    from app.services.monitoring.escalation_service import delete_policy as _delete
    data = _delete(policy_id)
    return APIResponse.success(data=data)


@monitor_bp.route("/alert-dependency-rules", methods=["GET"])
@doc(summary="列出全部告警依赖抑制规则", tags=["监控"], responses={200: "MonitorAlertDependencyRuleItem"})
@login_required
@permission_required("monitor:view")
def list_alert_dependency_rules():
    from app.services.monitoring.alert_dependency_service import list_rules as _list
    items = _list()
    return APIResponse.paginated(data=items, page=1, per_page=len(items) or 1, total=len(items))


@monitor_bp.route("/alert-dependency-rules", methods=["POST"])
@doc(summary="创建告警依赖抑制规则", tags=["监控"], responses={200: "MonitorAlertDependencyRuleItem"})
@login_required
@permission_required("monitor:config")
@transactional
def create_alert_dependency_rule():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = MonitorAlertDependencyRuleCreateSchema().load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")
    from app.services.monitoring.alert_dependency_service import create_rule as _create
    result = _create(data)
    return APIResponse.success(data=result)


@monitor_bp.route("/alert-dependency-rules/<int:rule_id>", methods=["PATCH"])
@doc(summary="更新告警依赖抑制规则", tags=["监控"], responses={200: "MonitorAlertDependencyRuleItem"})
@login_required
@permission_required("monitor:config")
@transactional
def update_alert_dependency_rule(rule_id: int):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = MonitorAlertDependencyRuleUpdateSchema().load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")
    from app.services.monitoring.alert_dependency_service import update_rule as _update
    result = _update(rule_id, data)
    return APIResponse.success(data=result)


@monitor_bp.route("/alert-dependency-rules/<int:rule_id>", methods=["DELETE"])
@doc(summary="删除告警依赖抑制规则", tags=["监控"], responses={200: "MonitorAlertDependencyRuleItem"})
@login_required
@permission_required("monitor:config")
@transactional
def delete_alert_dependency_rule(rule_id: int):
    from app.services.monitoring.alert_dependency_service import delete_rule as _delete
    data = _delete(rule_id)
    return APIResponse.success(data=data)


@monitor_bp.route("/sla-targets", methods=["GET"])
@doc(summary="列出全部 SLA 目标", tags=["监控"], responses={200: "MonitorSlaTargetItem"})
@login_required
@permission_required("monitor:view")
def list_sla_targets():
    from app.services.monitoring.sla_service import list_targets as _list
    items = _list()
    return APIResponse.paginated(data=items, page=1, per_page=len(items) or 1, total=len(items))


@monitor_bp.route("/sla-targets", methods=["POST"])
@doc(summary="创建 SLA 目标", tags=["监控"], responses={200: "MonitorSlaTargetItem"})
@login_required
@permission_required("monitor:config")
@transactional
def create_sla_target():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = MonitorSlaTargetCreateSchema().load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")
    from app.services.monitoring.sla_service import create_target as _create
    result = _create(data)
    return APIResponse.success(data=result)


@monitor_bp.route("/sla-targets/<int:target_id>", methods=["PATCH"])
@doc(summary="更新 SLA 目标", tags=["监控"], responses={200: "MonitorSlaTargetItem"})
@login_required
@permission_required("monitor:config")
@transactional
def update_sla_target(target_id: int):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = MonitorSlaTargetUpdateSchema().load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")
    from app.services.monitoring.sla_service import update_target as _update
    result = _update(target_id, data)
    return APIResponse.success(data=result)


@monitor_bp.route("/sla-targets/<int:target_id>", methods=["DELETE"])
@doc(summary="删除 SLA 目标", tags=["监控"], responses={200: "MonitorSlaTargetItem"})
@login_required
@permission_required("monitor:config")
@transactional
def delete_sla_target(target_id: int):
    from app.services.monitoring.sla_service import delete_target as _delete
    data = _delete(target_id)
    return APIResponse.success(data=data)


@monitor_bp.route("/sla-targets/<int:target_id>/report", methods=["GET"])
@doc(summary="查询单个 SLA 目标达成度", tags=["监控"], responses={200: "MonitorSlaAchievement"})
@login_required
@permission_required("monitor:view")
def get_sla_achievement(target_id: int):
    from app.services.monitoring.sla_service import compute_achievement
    from datetime import datetime as _dt
    start = request.args.get("start")
    end = request.args.get("end")
    start_dt = _dt.fromisoformat(start.replace("Z", "+00:00")) if start else None
    end_dt = _dt.fromisoformat(end.replace("Z", "+00:00")) if end else None
    result = compute_achievement(target_id, start=start_dt, end=end_dt)
    return APIResponse.success(data=result)


@monitor_bp.route("/sla-targets/achievements", methods=["GET"])
@doc(summary="查询全部启用 SLA 目标达成度", tags=["监控"], responses={200: "MonitorSlaAchievement"})
@login_required
@permission_required("monitor:view")
def list_sla_achievements():
    from app.services.monitoring.sla_service import compute_all_achievements
    from datetime import datetime as _dt
    start = request.args.get("start")
    end = request.args.get("end")
    start_dt = _dt.fromisoformat(start.replace("Z", "+00:00")) if start else None
    end_dt = _dt.fromisoformat(end.replace("Z", "+00:00")) if end else None
    items = compute_all_achievements(start=start_dt, end=end_dt)
    return APIResponse.paginated(data=items, page=1, per_page=len(items) or 1, total=len(items))
