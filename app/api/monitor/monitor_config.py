# -*- coding: utf-8 -*-
"""监控运行配置 + 指标模板 + 指标告警 + Zabbix 流量。"""
from datetime import datetime, timedelta, timezone

from flask import request
from marshmallow import ValidationError as MarshmallowValidationError

from app.api.base import APIResponse
from app.exceptions.business import BusinessLogicError
from app.exceptions.validation import ValidationError
from app.api.monitor import (
    _ALLOWED_METRIC_SOURCE,
    _ALLOWED_METRIC_TYPE,
    _audit_config_change,
    _metric_alert_state_repo,
    _monitor_config_update_schema,
    credential_service,
    device_repo,
    monitor_bp,
)
from app.core.enums import MonitorProtocolCode
from app.openapi.doc import doc
from app.utils import login_required, permission_required
from app.utils.auth import get_current_user_id
from app.utils.logging import get_logger
from app.utils.transactional import transactional

logger = get_logger(__name__)


@monitor_bp.route("/config", methods=["GET"])
@doc(summary="查询监控运行配置", tags=["监控"], responses={200: "MonitorConfigResponse"})
@login_required
@permission_required("monitor:view")
def get_config():
    """返回当前生效的监控运行参数。"""
    from app.services.monitoring.dynamic_config import get_all
    data = get_all()
    return APIResponse.success(data=data)


@monitor_bp.route("/config", methods=["PUT"])
@doc(summary="在线修改监控运行配置", tags=["监控"], responses={200: "MonitorConfigUpdateResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def put_config():
    """在线修改监控运行参数（白名单内 editable 项）。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        data = _monitor_config_update_schema.load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"配置校验失败: {e.messages}")

    updates = data["updates"]
    from app.services.monitoring.dynamic_config import update_batch
    updated = update_batch(updates, updated_by=str(get_current_user_id() or "unknown"))

    _audit_config_change(updates, updated)
    return APIResponse.success(data={"updated": updated, "requires_restart": []})


@monitor_bp.route("/devices/<int:device_id>/metric-alerts", methods=["GET"])
@doc(
    summary="查询设备活跃指标告警明细",
    tags=["监控"],
    responses={200: "DeviceMetricAlertListResponse"},
)
@login_required
@permission_required("monitor:view")
def get_device_metric_alerts(device_id: int):
    """返回某设备的活跃指标告警明细。"""
    device = device_repo.find_by_id(device_id)
    if not device:
        raise BusinessLogicError("设备不存在", status_code=404)
    rows = _metric_alert_state_repo.active_metric_alerts(device_id)
    items = [row.to_dict() for row in rows]
    return APIResponse.success(data={"items": items})


@monitor_bp.get("/metric-templates")
@doc(summary="列出全部指标模板", tags=["监控"], responses={200: "MetricTemplateListResponse"})
@login_required
@permission_required("monitor:view")
def list_metric_templates():
    """列出全部指标模板。"""
    from app.services.monitoring.metric_template_service import list_metric_templates as _list
    data = _list()
    return APIResponse.paginated(data=data, page=1, per_page=len(data) or 1, total=len(data))


@monitor_bp.put("/metric-templates")
@doc(summary="新增/更新指标模板（幂等）", tags=["监控"], responses={200: "MetricTemplateUpsertResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def upsert_metric_template():
    """按 (device_type, metric_key) 幂等新增/更新指标模板。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    device_type = body.get("device_type")
    metric_key = body.get("metric_key")
    if device_type not in ("network", "server", "other") or not metric_key:
        raise ValidationError("device_type / metric_key 不合法")
    source = body.get("source", "snmp")
    metric_type = body.get("metric_type", "gauge")
    if source not in _ALLOWED_METRIC_SOURCE or metric_type not in _ALLOWED_METRIC_TYPE:
        raise ValidationError("source / metric_type 不合法")
    if source == "zabbix" and not body.get("zabbix_item_key"):
        raise ValidationError("source=zabbix 时 zabbix_item_key 必填")

    from app.services.monitoring.metric_template_service import upsert as _upsert
    data = _upsert(body)
    return APIResponse.success(data=data)


@monitor_bp.post("/metric-templates/seed")
@doc(summary="写入内置默认指标模板（幂等）", tags=["监控"], responses={200: "MetricTemplateSeedResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def seed_metric_templates():
    """写入内置默认指标模板（幂等）。"""
    from app.services.monitoring.metric_template_service import seed_defaults
    created = seed_defaults()
    return APIResponse.success(data={"created": created})


@monitor_bp.delete("/metric-templates/<int:template_id>")
@doc(summary="删除指标模板", tags=["监控"], responses={200: "MetricTemplateDeleteResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def delete_metric_template(template_id: int):
    """删除指标模板。"""
    from app.services.monitoring.metric_template_service import delete as _delete
    data = _delete(template_id)
    return APIResponse.success(data=data)


@monitor_bp.route("/metric-templates/batch", methods=["DELETE"])
@doc(summary="批量删除指标模板", tags=["监控"], responses={200: "MetricTemplateDeleteResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def batch_delete_metric_templates():
    """批量删除指标模板。"""
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids:
        raise ValidationError("ids 必须为非空数组")
    if not all(isinstance(i, int) for i in ids):
        raise ValidationError("ids 元素必须为整数")
    from app.services.monitoring.metric_template_service import batch_delete
    data = batch_delete(ids)
    return APIResponse.success(data=data)


@monitor_bp.route("/metric-templates/batch-enabled", methods=["PATCH"])
@doc(summary="批量启停指标模板", tags=["监控"], responses={200: "MetricTemplateDeleteResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def batch_toggle_metric_templates_enabled():
    """批量启用/停用指标模板。"""
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")
    enabled = body.get("enabled")
    if not isinstance(ids, list) or not ids:
        raise ValidationError("ids 必须为非空数组")
    if not all(isinstance(i, int) for i in ids):
        raise ValidationError("ids 元素必须为整数")
    if not isinstance(enabled, bool):
        raise ValidationError("enabled 必须为布尔值")
    from app.services.monitoring.metric_template_service import batch_set_enabled
    data = batch_set_enabled(ids, enabled)
    return APIResponse.success(data=data)



_graph_service = None


def _get_graph_service():
    global _graph_service
    if _graph_service is None:
        from app.services.monitoring.zabbix_graph_service import ZabbixGraphService
        _graph_service = ZabbixGraphService()
    return _graph_service


@monitor_bp.get("/devices/<int:device_id>/traffic/ports")
@doc(summary="Zabbix 端口流量可用端口列表", tags=["监控"], responses={200: "DeviceTrafficPortsResponse"})
@login_required
@permission_required("monitor:view")
def get_device_traffic_ports(device_id: int):
    """返回设备所有有流量 item 的端口列表（轻量，不拉历史）。"""
    device = device_repo.find_by_id_or_404(device_id)
    try:
        cred = credential_service.get_decrypted(device_id, MonitorProtocolCode.ZABBIX.value)
    except Exception:
        logger.warning("Zabbix 凭据解密失败 device_id=%s", device_id, exc_info=True)
        return APIResponse.success(data={"ports": [], "configured": False, "error": "credential_error"})
    if not cred:
        return APIResponse.success(data={"ports": [], "configured": False, "error": None})
    try:
        ports = _get_graph_service().list_ports(cred, device)
    except Exception:
        logger.warning("Zabbix 端口列表拉取失败 device_id=%s", device_id, exc_info=True)
        return APIResponse.success(data={"ports": [], "configured": False, "error": "fetch_error"})
    return APIResponse.success(data={"ports": ports, "configured": True, "error": None})


@monitor_bp.get("/devices/<int:device_id>/traffic")
@doc(summary="Zabbix 端口流量时间序列", tags=["监控"], responses={200: "DeviceTrafficResponse"})
@login_required
@permission_required("monitor:view")
def get_device_traffic(device_id: int):
    """按设备+端口拉取 Zabbix 端口流量时间序列。"""
    device = device_repo.find_by_id_or_404(device_id)
    try:
        cred = credential_service.get_decrypted(device_id, MonitorProtocolCode.ZABBIX.value)
    except Exception:
        logger.warning("Zabbix 凭据解密失败 device_id=%s", device_id, exc_info=True)
        cred = None
    if not cred:
        return APIResponse.success(
            data={"port": None, "time": [], "rx_bps": [], "tx_bps": [], "configured": False}
        )

    port = request.args.get("port", type=str)
    if not port:
        raise ValidationError("port 参数必填")
    now = int(datetime.now(timezone.utc).timestamp())
    try:
        time_from = int(request.args.get("from", now - 3600))
        time_till = int(request.args.get("till", now))
    except (TypeError, ValueError):
        raise ValidationError("from/till 必须是 unix 时间戳")

    series = _get_graph_service().get_port_traffic(
        cred, device, port, time_from, time_till,
        ports=_get_graph_service().list_ports(cred, device),
    )
    series["configured"] = True
    return APIResponse.success(data=series)




@monitor_bp.get("/metric-template-groups")
@doc(summary="列出全部指标模板组", tags=["监控"], responses={200: "MetricTemplateGroupListResponse"})
@login_required
@permission_required("monitor:view")
def list_metric_template_groups():
    """列出全部指标模板组（含每组模板数）。"""
    from app.services.monitoring.metric_template_group_service import MetricTemplateGroupService
    data = MetricTemplateGroupService().list_groups()
    return APIResponse.success(data=data)


@monitor_bp.post("/metric-template-groups")
@doc(summary="新建指标模板组", tags=["监控"], responses={200: "MetricTemplateGroupMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def create_metric_template_group():
    """新建指标模板组（校验 device_type+source 唯一性）。"""
    body = request.get_json(silent=True) or {}
    from app.services.monitoring.metric_template_group_service import MetricTemplateGroupService
    data = MetricTemplateGroupService().create_group(body)
    return APIResponse.success(data=data)


@monitor_bp.get("/metric-template-groups/<int:group_id>")
@doc(summary="查询模板组详情（含组内模板）", tags=["监控"], responses={200: "MetricTemplateGroupDetailResponse"})
@login_required
@permission_required("monitor:view")
def get_metric_template_group(group_id: int):
    """查询模板组详情（含组内模板列表）。"""
    from app.services.monitoring.metric_template_group_service import MetricTemplateGroupService
    data = MetricTemplateGroupService().get_group_detail(group_id)
    return APIResponse.success(data=data)


@monitor_bp.put("/metric-template-groups/<int:group_id>")
@doc(summary="更新指标模板组", tags=["监控"], responses={200: "MetricTemplateGroupMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def update_metric_template_group(group_id: int):
    """更新指标模板组（校验组内模板兼容性）。"""
    body = request.get_json(silent=True) or {}
    from app.services.monitoring.metric_template_group_service import MetricTemplateGroupService
    data = MetricTemplateGroupService().update_group(group_id, body)
    return APIResponse.success(data=data)


@monitor_bp.delete("/metric-template-groups/<int:group_id>")
@doc(summary="删除指标模板组", tags=["监控"], responses={200: "MetricTemplateGroupMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def delete_metric_template_group(group_id: int):
    """删除指标模板组（级联删除组-模板关联）。"""
    from app.services.monitoring.metric_template_group_service import MetricTemplateGroupService
    data = MetricTemplateGroupService().delete_group(group_id)
    return APIResponse.success(data=data)


@monitor_bp.post("/metric-template-groups/<int:group_id>/items")
@doc(summary="勾选指标模板入组（批量）", tags=["监控"], responses={200: "MetricTemplateGroupMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def add_templates_to_group(group_id: int):
    """批量勾选指标模板入组（幂等，校验 device_type+source 一致）。"""
    body = request.get_json(silent=True) or {}
    template_ids = body.get("template_ids") or []
    if not isinstance(template_ids, list) or not template_ids:
        raise ValidationError("template_ids 必须是非空数组")
    from app.services.monitoring.metric_template_group_service import MetricTemplateGroupService
    data = MetricTemplateGroupService().batch_add_templates(group_id, template_ids)
    return APIResponse.success(data=data)


@monitor_bp.delete("/metric-template-groups/<int:group_id>/items/<int:template_id>")
@doc(summary="从组中移除指标模板", tags=["监控"], responses={200: "MetricTemplateGroupMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def remove_template_from_group(group_id: int, template_id: int):
    """从组中移除指标模板。"""
    from app.services.monitoring.metric_template_group_service import MetricTemplateGroupService
    data = MetricTemplateGroupService().remove_template_from_group(group_id, template_id)
    return APIResponse.success(data=data)




@monitor_bp.get("/devices/<int:device_id>/metric-latest")
@doc(summary="查询设备指标当前值", tags=["监控"], responses={200: "DeviceMetricLatestListResponse"})
@login_required
@permission_required("monitor:view")
def get_device_metric_latest(device_id: int):
    """返回某设备的全部指标当前值（含正常值，按 metric_key 分组）。"""
    device = device_repo.find_by_id(device_id)
    if not device:
        raise BusinessLogicError("设备不存在", status_code=404)
    from app.persistence.device_metric_latest_repository import DeviceMetricLatestRepository
    rows = DeviceMetricLatestRepository().find_by_device(device_id)
    items = [row.to_dict() for row in rows]
    return APIResponse.success(data={"items": items})




def _parse_iso_dt(value: str) -> datetime | None:
    """解析查询参数中的 ISO 时间；非法格式抛 ValueError。"""
    if not value:
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    dt = datetime.fromisoformat(v)
    return dt.replace(tzinfo=None)


@monitor_bp.get("/devices/<int:device_id>/metric-keys")
@doc(summary="查询设备有历史时序的指标 key 列表", tags=["监控"], responses={200: "DeviceMetricKeysResponse"})
@login_required
@permission_required("monitor:view")
def get_device_metric_keys(device_id: int):
    """返回设备有历史时序数据的所有 metric_key（供前端指标选择器）。"""
    device = device_repo.find_by_id(device_id)
    if not device:
        raise BusinessLogicError("设备不存在", status_code=404)
    from app.persistence.device_metric_timeseries_repository import (
        DeviceMetricTimeseriesRepository,
    )
    keys = DeviceMetricTimeseriesRepository().list_metric_keys(device_id)
    return APIResponse.success(data={"items": keys})


@monitor_bp.get("/devices/<int:device_id>/metrics/<string:metric_key>/history")
@doc(summary="查询设备指标历史时序", tags=["监控"], responses={200: "DeviceMetricHistoryResponse"})
@login_required
@permission_required("monitor:view")
def get_device_metric_history(device_id: int, metric_key: str):
    """返回设备某指标的历史时序（时间升序），支持 index_key / 时间范围 / limit 过滤。"""
    device = device_repo.find_by_id(device_id)
    if not device:
        raise BusinessLogicError("设备不存在", status_code=404)

    raw_from = (request.args.get("from") or "").strip() or None
    raw_to = (request.args.get("to") or "").strip() or None
    index_key = (request.args.get("index_key") or "").strip() or None
    try:
        from_ = _parse_iso_dt(raw_from)
        to_ = _parse_iso_dt(raw_to)
    except ValueError:
        raise ValidationError("from/to 必须为合法 ISO datetime")
    if from_ and to_ and from_ > to_:
        raise ValidationError("from 不能晚于 to")

    try:
        limit = min(max(int(request.args.get("limit", 2000)), 1), 5000)
    except ValueError:
        raise ValidationError("limit 必须为正整数")

    if to_ is None:
        to_ = datetime.now(timezone.utc).replace(tzinfo=None)
    if from_ is None:
        from_ = to_ - timedelta(days=1)

    from app.persistence.device_metric_timeseries_repository import (
        DeviceMetricTimeseriesRepository,
    )
    rows = DeviceMetricTimeseriesRepository().list_by_metric(
        device_id, metric_key, index_key=index_key, from_=from_, to=to_, limit=limit,
    )
    items = [row.to_dict() for row in rows]
    return APIResponse.success(data={
        "items": items,
        "total": len(items),
        "from": from_.isoformat(),
        "to": to_.isoformat(),
        "index_key": index_key,
    })
