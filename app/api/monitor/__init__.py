# -*- coding: utf-8 -*-
"""设备健康监控 API 模块。

按功能分拆为 6 个子模块，全部挂在 monitor_bp 下，注册到 `/api/monitor`：
- monitor_device.py       设备状态/历史/趋势/探测/批量探测
- monitor_credentials.py  凭据 CRUD + 链接 + 密文更新
- monitor_alerts.py       总览/状态/告警/重试/监控开关
- monitor_config.py       配置 + 指标模板 + 指标告警 + Zabbix 流量
- monitor_rules.py        静默规则 + 阈值覆盖 + 升级策略
- monitor_oid.py          OID 分类规则 + 推荐 + 厂商 + MIB 扫描

核心约束：
- POST /check 的网络 I/O 必须在事务外（先 probe_device，再 @transactional 落库 + 告警）。
- 凭据明文绝不回显到响应；加密由 MonitorCredentialService 内部完成。
- GET /status 对未配置凭据的设备返回 200 + monitored=False，而非 404。
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, current_app, request, g
from marshmallow import ValidationError as MarshmallowValidationError
from sqlalchemy.orm import sessionmaker

from app.api.base import APIResponse, ErrorCode, RequestValidator, api_exception_handler
from app.core.enums import MonitorProtocolCode
from app.models.monitor_alert_outbox import MonitorAlertOutbox
from app.openapi.doc import doc
from app.persistence.device_metric_alert_state_repository import DeviceMetricAlertStateRepository
from app.persistence.device_metric_override_repository import DeviceMetricOverrideRepository
from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository
from app.persistence.device_repository import DeviceRepository
from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
from app.persistence.monitor_credential_repository import MonitorCredentialRepository
from app.persistence.monitor_device_type_recommend_repository import MonitorDeviceTypeRecommendRepository
from app.persistence.monitor_escalation_policy_repository import MonitorEscalationPolicyRepository
from app.persistence.monitor_metric_template_repository import MonitorMetricTemplateRepository
from app.persistence.monitor_oid_category_rule_repository import MonitorOidCategoryRuleRepository
from app.persistence.monitor_silence_rule_repository import MonitorSilenceRuleRepository
from app.persistence.monitor_timeseries_repository import MonitorTimeseriesRepository
from app.schemas.monitor import (
    MonitorBatchMonitorEnabledSchema,
    MonitorCheckBatchSchema,
    MonitorConfigUpdateSchema,
    MonitorCredentialPayloadUpdateSchema,
    MonitorCredentialUpsertSchema,
    MonitorAlertListQuerySchema,
    MonitorDeviceMonitorEnabledSchema,
)
from app.services.audit_service import AuditService
from app.services.monitoring.credential_service import MonitorCredentialService
from app.services.monitoring.dynamic_config import CAMEL_TO_KEY, MonitorDynamicConfig, all_entries
from app.services.monitoring.monitor_service import MonitorService
from app.services.monitoring.protocol_registry import build_adapter
from app.utils import login_required, permission_required
from app.utils.auth import get_current_user_id
from app.utils.logging import get_logger
from app.utils.transactional import transactional

logger = get_logger(__name__)

monitor_bp = Blueprint("monitor", __name__)

_ALLOWED_PROTOCOLS = {e.value for e in MonitorProtocolCode}

_ALLOWED_METRIC_SOURCE = {"snmp", "ipmi", "zabbix"}
_ALLOWED_METRIC_TYPE = {"gauge", "counter", "state", "event"}

_credential_upsert_schema = MonitorCredentialUpsertSchema()
_credential_payload_schema = MonitorCredentialPayloadUpdateSchema()
_alert_list_schema = MonitorAlertListQuerySchema()
_device_monitor_enabled_schema = MonitorDeviceMonitorEnabledSchema()
_batch_monitor_enabled_schema = MonitorBatchMonitorEnabledSchema()
_monitor_config_update_schema = MonitorConfigUpdateSchema()

credential_service = MonitorCredentialService()
status_repo = DeviceMonitorStatusRepository()
credential_repo = MonitorCredentialRepository()
device_repo = DeviceRepository()
alert_repo = MonitorAlertOutboxRepository()
monitor_ts_repo = MonitorTimeseriesRepository()
_metric_alert_state_repo = DeviceMetricAlertStateRepository()
_metric_template_repo = MonitorMetricTemplateRepository()
_silence_rule_repo = MonitorSilenceRuleRepository()
_override_repo = DeviceMetricOverrideRepository()
_escalation_policy_repo = MonitorEscalationPolicyRepository()
_oid_category_rule_repo = MonitorOidCategoryRuleRepository()
_device_type_recommend_repo = MonitorDeviceTypeRecommendRepository()

monitor_service = MonitorService(
    build_adapter(MonitorProtocolCode.SNMP.value),
    build_adapter(MonitorProtocolCode.IPMI.value),
    build_adapter(MonitorProtocolCode.ZABBIX.value),
    build_adapter(MonitorProtocolCode.PING.value),
    credential_service,
    status_repo,
    credential_repo=credential_repo,
    device_repo=device_repo,
)


def _audit_credential_change(action: str, detail: dict) -> None:
    """记录监控凭据变更审计（独立 session，失败不影响主流程）。"""
    try:
        AuditService().log(
            user_id=get_current_user_id(),
            action=action,
            resource="monitor_credential",
            detail=detail,
            ip_address=request.remote_addr,
        )
    except Exception:
        logger.warning("监控凭据审计写入失败（已忽略）", exc_info=True)


def _audit_monitor_enabled(device_id: int, enabled: bool) -> None:
    """记录设备级监控启停审计（独立 session，失败不影响主流程）。"""
    try:
        AuditService().log(
            user_id=get_current_user_id(),
            action="monitor:device:monitor_enabled",
            resource="monitor_device",
            detail={"device_id": device_id, "monitor_enabled": bool(enabled)},
            ip_address=request.remote_addr,
        )
    except Exception:
        logger.warning("设备级监控启停审计写入失败（已忽略）", exc_info=True)


def _audit_config_change(updates: dict, updated: list) -> None:
    """记录监控运行配置在线修改审计（独立 session，失败不影响主流程）。"""
    try:
        AuditService().log(
            user_id=get_current_user_id(),
            action="monitor:config:update",
            resource="monitor_config",
            detail={"updates": updates, "updated": updated},
            ip_address=request.remote_addr,
        )
    except Exception:
        logger.warning("监控配置审计写入失败（已忽略）", exc_info=True)


from app.api.monitor import monitor_device  # noqa: E402,F401
from app.api.monitor import monitor_credentials  # noqa: E402,F401
from app.api.monitor import monitor_alerts  # noqa: E402,F401
from app.api.monitor import monitor_config  # noqa: E402,F401
from app.api.monitor import monitor_rules  # noqa: E402,F401
from app.api.monitor import monitor_oid  # noqa: E402,F401
from app.api.monitor import incident_routes  # noqa: E402,F401
