# -*- coding: utf-8 -*-
"""设备健康监控状态机

显式状态机 + 适配器分流 + 告警目标解析。

核心职责：
- 根据 device_type 选择监控协议（SNMP / Redfish / IPMI），按凭据可用情况分流；
- 消费适配器探测结果（ProbeResult），维护「可达性状态机」快照并落库；
- 基于连续失败阈值做抖动抑制 + 去重告警（episode 递增使幂等键不撞）；
- 解析告警目标（责任人 user / 兜底角色 role）并投递通知。
"""
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import threading
import time
from typing import Optional, Tuple

from flask import current_app

from app.utils.logging import get_logger
from app.core.enums import MonitorProtocolCode, NotificationTypeCode, ProbeErrorCode
from app.services.monitoring.adapters.base_adapter import (
    MonitorAdapter,
    ProbeResult,
    resolve_host_with_timeout,
    _is_ip_address,
    monitor_timeout_seconds,
)
from app.services.monitoring.protocol_registry import (
    device_type_to_protocols,
    protocol_requires_credential,
)
from app.services.notification_service import notification_service
from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository
from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
from app.persistence.monitor_timeseries_repository import MonitorTimeseriesRepository
from app.utils.transactional import transactional


logger = get_logger(__name__)

_ROLE_ACTIVE_USER_CACHE: dict = {}
_ROLE_ACTIVE_USER_TTL = 300
_ROLE_ACTIVE_USER_CACHE_LOCK = threading.Lock()

CONFIG_ERROR_CODES = frozenset({
    "no_host_ref",
    "no_api_url",
    "host_not_in_zabbix",
    "zabbix_empty_host_list",
})


@dataclass(frozen=True)
class AlertTarget:
    target_type: str
    target_id: object
    channels: tuple
    allow_broadcast: bool
    has_recipient: bool


@dataclass(frozen=True)
class _MonitorTransition:

    reachable: bool
    failures: int
    ever_reachable: bool
    became_down: bool
    recovered: bool
    re_alert_due: bool
    down_alerted: bool
    episode: int
    alert_action: str


def _compute_monitor_transition(
    *,
    reachable: bool,
    threshold: int,
    re_alert_interval: timedelta,
    now: datetime,
    old_failures: int,
    old_ever: bool,
    old_down_alerted: bool,
    old_episode: int,
    last_alerted_at: Optional[str],
) -> _MonitorTransition:
    failures = 0 if reachable else old_failures + 1
    ever_reachable = old_ever or reachable

    became_down = (not reachable) and (failures >= threshold) and (not old_down_alerted)
    recovered = reachable and old_down_alerted

    re_alert_due = False
    if (not reachable) and (failures >= threshold) and old_down_alerted:
        if last_alerted_at is None:
            re_alert_due = True
        else:
            try:
                if isinstance(last_alerted_at, datetime):
                    ts = last_alerted_at
                else:
                    ts = datetime.fromisoformat(str(last_alerted_at))
                if ts.tzinfo is None and now.tzinfo is not None:
                    ts = ts.replace(tzinfo=now.tzinfo)
                re_alert_due = (now - ts) >= re_alert_interval
            except (ValueError, TypeError):
                re_alert_due = True

    if became_down:
        down_alerted = True
        episode = old_episode + 1
    elif recovered:
        down_alerted = False
        episode = old_episode
    else:
        down_alerted = old_down_alerted
        episode = old_episode

    if became_down or re_alert_due:
        alert_action = "unreachable"
    elif recovered:
        alert_action = "recovered"
    else:
        alert_action = ""

    return _MonitorTransition(
        reachable=reachable,
        failures=failures,
        ever_reachable=ever_reachable,
        became_down=became_down,
        recovered=recovered,
        re_alert_due=re_alert_due,
        down_alerted=down_alerted,
        episode=episode,
        alert_action=alert_action,
    )


class MonitorService:

    def __init__(
        self,
        snmp_adapter,
        ipmi_adapter,
        zabbix_adapter,
        ping_adapter,
        credential_service,
        status_repo: DeviceMonitorStatusRepository,
        credential_repo=None,
        device_repo=None,
        notify=None,
        template_repo=None,
    ):
        self.snmp_adapter = snmp_adapter
        self.ipmi_adapter = ipmi_adapter
        self.zabbix_adapter = zabbix_adapter
        self.ping_adapter = ping_adapter
        self.credential_service = credential_service
        self.status_repo = status_repo
        if credential_repo is None:
            from app.persistence.monitor_credential_repository import MonitorCredentialRepository
            credential_repo = MonitorCredentialRepository()
        if device_repo is None:
            from app.persistence.device_repository import DeviceRepository
            device_repo = DeviceRepository()
        if template_repo is None:
            from app.persistence.monitor_metric_template_repository import (
                MonitorMetricTemplateRepository,
            )
            template_repo = MonitorMetricTemplateRepository()
        self._credential_repo = credential_repo
        self._device_repo = device_repo
        self._template_repo = template_repo
        self._tpl_cache: dict = {}
        self.notify = notify or notification_service
        self._adapters = {
            MonitorProtocolCode.SNMP.value: snmp_adapter,
            MonitorProtocolCode.IPMI.value: ipmi_adapter,
            MonitorProtocolCode.ZABBIX.value: zabbix_adapter,
            MonitorProtocolCode.PING.value: ping_adapter,
        }


    def _cfg(self, name: str, default, session=None):
        from app.services.monitoring.dynamic_config import MonitorDynamicConfig

        val = MonitorDynamicConfig.get(name, session=session)
        if val is not None:
            return val
        return current_app.config.get(name, default)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    _CFG_KEYS = (
        "MONITOR_CONSECUTIVE_FAILURES_THRESHOLD",
        "MONITOR_REALERT_INTERVAL_MINUTES",
        "MONITOR_FALLBACK_ROLE",
        "MONITOR_BLINDSPOT_ROLE",
    )
    _CFG_DEFAULTS = {
        "MONITOR_CONSECUTIVE_FAILURES_THRESHOLD": 2,
        "MONITOR_REALERT_INTERVAL_MINUTES": 360,
        "MONITOR_FALLBACK_ROLE": "admin",
        "MONITOR_BLINDSPOT_ROLE": "admin",
    }

    def _batch_cfg(self, session=None) -> tuple:
        from app.services.monitoring.dynamic_config import MonitorDynamicConfig
        batch = MonitorDynamicConfig.get_batch(list(self._CFG_KEYS), session=session)
        vals = []
        for k in self._CFG_KEYS:
            v = batch.get(k)
            if v is None:
                v = current_app.config.get(k, self._CFG_DEFAULTS[k])
            vals.append(v)
        return tuple(vals)


    def _candidate_protocols(self, device) -> list:
        device_type = getattr(device, "device_type", None)
        return device_type_to_protocols(device_type)

    def get_monitored_device_ids(self, protocols: list) -> list:
        if protocols and all(not protocol_requires_credential(p) for p in protocols):
            return self._credential_repo.find_enabled_device_ids_all(
                monitor_enabled_only=True
            )
        return self._credential_repo.find_enabled_device_ids(
            protocols, monitor_enabled_only=True
        )

    def _select_adapter(self, device):
        for protocol in self._candidate_protocols(device):
            adapter = self._adapters.get(protocol)
            if adapter is None:
                continue
            if not protocol_requires_credential(protocol):
                return adapter, None
            cred = self.credential_service.get_decrypted(device.id, protocol)
            if cred is not None:
                return adapter, cred
        return None


    def check_device(self, device) -> None:
        selected = self.probe_device(device)
        if selected is None:
            return
        result, protocol = selected
        if getattr(result, "skipped", False):
            return
        threshold, re_alert, fallback_role, blindspot_role = self._batch_cfg()
        self._persist(
            device, result, protocol,
            threshold=threshold, re_alert_interval_minutes=re_alert,
            fallback_role=fallback_role, blindspot_role=blindspot_role,
        )

    def check_device_in_session(self, device, session) -> None:
        selected = self.probe_device(device)
        if selected is None:
            return
        result, protocol = selected
        if getattr(result, "skipped", False):
            return
        threshold, re_alert, fallback_role, blindspot_role = self._batch_cfg(session=session)
        per_task_repo = DeviceMonitorStatusRepository(session=session)
        self.apply_result(
            device, result, protocol, status_repo=per_task_repo,
            threshold=threshold, re_alert_interval_minutes=re_alert,
            fallback_role=fallback_role, blindspot_role=blindspot_role,
        )
        session.commit()

    @transactional
    def _persist(self, device, result, protocol, threshold=None,
                 re_alert_interval_minutes=None, fallback_role=None,
                 blindspot_role=None) -> None:
        self.apply_result(
            device, result, protocol,
            threshold=threshold, re_alert_interval_minutes=re_alert_interval_minutes,
            fallback_role=fallback_role, blindspot_role=blindspot_role,
        )

    def probe_device(self, device) -> Optional[tuple[ProbeResult, str]]:
        selected = self._select_adapter(device)
        if selected is None:
            return None
        adapter, cred = selected
        host = MonitorAdapter.resolve_target_ip(device)
        if host and not _is_ip_address(host):
            resolved = resolve_host_with_timeout(host, monitor_timeout_seconds())
            if resolved is None:
                logger.warning(
                    "设备 %s 的连接目标 %s DNS 预解析失败（超时/不可解析），"
                    "跳过本轮探测，不视为设备不可达",
                    getattr(device, "id", None), host,
                )
                return ProbeResult(
                    reachable=False, error=ProbeErrorCode.DNS_RESOLVE_TIMEOUT.value, skipped=True
                ), adapter.protocol.value
        result = adapter.probe(device, cred)
        return result, adapter.protocol.value

    def probe_and_persist(self, device) -> Optional[tuple[ProbeResult, str]]:
        probed = self.probe_device(device)
        if probed is None:
            return None
        result, protocol = probed
        if getattr(result, "skipped", False):
            return result, protocol
        threshold = self._cfg("MONITOR_CONSECUTIVE_FAILURES_THRESHOLD", 2)
        re_alert = self._cfg("MONITOR_REALERT_INTERVAL_MINUTES", 360)
        fallback_role = self._cfg("MONITOR_FALLBACK_ROLE", "admin")
        blindspot_role = self._cfg("MONITOR_BLINDSPOT_ROLE", "admin")
        self.apply_result(
            device, result, protocol,
            threshold=threshold, re_alert_interval_minutes=re_alert,
            fallback_role=fallback_role, blindspot_role=blindspot_role,
        )
        return result, protocol

    def check_probe_cooldown(self, device_id: int) -> bool:
        try:
            from flask import current_app
            from app.services.monitoring.dynamic_config import MonitorDynamicConfig
            r = MonitorDynamicConfig._redis(current_app)
            if r is None:
                return True
            cooldown = current_app.config.get("MONITOR_PROBE_COOLDOWN_SECONDS", 30)
            key = f"monitor:probe:cooldown:{device_id}"
            return bool(r.set(key, "1", nx=True, ex=int(cooldown)))
        except Exception:
            logger.warning("探测冷却限流检查失败（降级为不限流） device_id=%s", device_id, exc_info=True)
            return True

    def check_batch(self, device_ids: list[int]) -> dict:
        from concurrent.futures import ThreadPoolExecutor
        from flask import current_app
        from sqlalchemy.orm import sessionmaker
        from extensions import db
        from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository

        targets, skipped = [], []
        for did in device_ids:
            if not self.check_probe_cooldown(did):
                skipped.append(did)
                continue
            device = self._device_repo.find_by_id(did)
            if not device:
                skipped.append(did)
                continue
            _ = device.hardware
            _ = getattr(device.hardware, "ipmi_address", None) if device.hardware else None
            targets.append(device)

        if not targets:
            return {"results": [], "skipped": skipped}

        for d in targets:
            db.session.expunge(d)

        app = current_app._get_current_object()
        Session = sessionmaker(bind=db.engine, expire_on_commit=False)

        def _check_one(device):
            with app.app_context():
                with Session() as session:
                    per_task_status_repo = DeviceMonitorStatusRepository(session=session)
                    selected = self.probe_device(device)
                    if selected is None:
                        return {
                            "device_id": device.id,
                            "reachable": None,
                            "latency_ms": None,
                            "extra": None,
                            "error": "no_credential",
                        }
                    result, protocol = selected
                    if getattr(result, "skipped", False):
                        return {
                            "device_id": device.id,
                            "reachable": None,
                            "latency_ms": None,
                            "extra": result.extra,
                            "error": result.error,
                        }
                    self.apply_result(
                        device, result, protocol, status_repo=per_task_status_repo,
                    )
                    session.commit()
                    return {
                        "device_id": device.id,
                        "reachable": result.reachable,
                        "latency_ms": result.latency_ms,
                        "extra": result.extra,
                        "error": result.error,
                    }

        pool_size = current_app.config.get("MONITOR_BATCH_POOL_SIZE", 10)
        if not hasattr(self, "_batch_executor") or self._batch_executor is None:
            self._batch_executor = ThreadPoolExecutor(
                max_workers=pool_size, thread_name_prefix="monitor-batch"
            )
        results = list(self._batch_executor.map(_check_one, targets))
        return {"results": results, "skipped": skipped}

    def collect_device_metrics(self, device) -> dict:
        selected = self._select_adapter(device)
        if selected is None:
            return {}
        adapter, cred = selected
        if not hasattr(adapter, "collect_metrics"):
            return {}
        try:
            from app.services.monitoring.metric_collector import MetricCollector

            collector = MetricCollector(self._template_repo, _tpl_cache=self._tpl_cache)
            return collector.collect(device, adapter, cred)
        except Exception:
            logger.warning(
                "设备 %s 指标采集失败（已降级跳过）",
                getattr(device, "id", None),
                exc_info=True,
            )
            return {}

    def get_device_status(self, device_id: int) -> dict:
        self._device_repo.find_by_id_or_404(device_id)
        creds = self._credential_repo.find_enabled_protocols(device_id)
        status = self.status_repo.find_by_device(device_id)

        credential_links = []
        for protocol in creds:
            linked = self._credential_repo.find_enabled(device_id, protocol)
            if linked is not None:
                credential_links.append(
                    {"protocol": protocol, "credential_id": linked.id, "name": linked.name}
                )

        return {
            "monitored": bool(creds),
            "configured_protocols": creds,
            "credentials": credential_links,
            "status": status.to_dict() if status else None,
        }

    def get_device_status_with_alerts(self, device_id: int) -> dict:
        from app.persistence.device_metric_alert_state_repository import (
            DeviceMetricAlertStateRepository,
        )
        data = self.get_device_status(device_id)
        alert_state_repo = DeviceMetricAlertStateRepository()
        alert_agg = alert_state_repo.active_alerts_by_device().get(device_id, {})
        data["active_metric_alerts"] = alert_agg.get("alert_count", 0)
        data["max_alert_severity"] = alert_agg.get("max_severity", 0)
        data["monitor_interrupted"] = device_id in alert_state_repo.interrupted_device_ids()
        return data

    def get_devices_monitor_summary(self, device_ids: list) -> dict:
        if not device_ids:
            return {}
        from app.persistence.device_metric_alert_state_repository import (
            DeviceMetricAlertStateRepository,
        )

        status_map = self.status_repo.find_by_device_ids(device_ids)
        monitor_cred_ids = set(
            self._credential_repo.find_enabled_device_ids(
                protocols=["snmp", "zabbix", "ipmi"]
            )
        )
        alert_state_repo = DeviceMetricAlertStateRepository()
        alert_agg = alert_state_repo.active_alerts_by_device()
        interrupted_ids = alert_state_repo.interrupted_device_ids()

        monitor_protocols = {"snmp", "zabbix", "ipmi"}
        result: Dict[int, dict] = {}
        for did in device_ids:
            status = status_map.get(did)
            has_cred = did in monitor_cred_ids
            agg = alert_agg.get(did, {})
            interrupted = did in interrupted_ids

            ping_reachable = None
            if status and status.extra:
                ping_reachable = status.extra.get("ping_reachable")

            monitor_reachable = None
            monitor_protocol = None
            if status and status.protocol in monitor_protocols:
                monitor_reachable = bool(status.reachable)
                monitor_protocol = status.protocol

            if (
                status is None
                and not has_cred
                and not agg
                and not interrupted
            ):
                continue

            result[did] = {
                "ping_reachable": ping_reachable,
                "has_monitor_credential": has_cred,
                "monitor_reachable": monitor_reachable,
                "monitor_protocol": monitor_protocol,
                "active_metric_alerts": agg.get("alert_count", 0),
                "max_alert_severity": agg.get("max_severity", 0),
                "monitor_interrupted": interrupted,
            }
        return result

    def get_device_metric_dashboard(self, device_id: int) -> dict:
        device = self._device_repo.find_by_id_or_404(device_id)
        creds = self._credential_repo.find_enabled_protocols(device_id)
        has_credential = bool(creds)
        has_zabbix = "zabbix" in creds

        from app.services.monitoring.metric_template_group_service import (
            MetricTemplateGroupService,
        )
        group_service = MetricTemplateGroupService()
        template_group = None
        grouped = False
        group_templates = []
        if device.metric_template_group_id:
            template_group = group_service.get_group_detail(device.metric_template_group_id)
            if template_group and template_group.get("templates"):
                group_templates = template_group["templates"]
                grouped = True
        if not grouped:
            candidates = [p for p in creds if p != "ping"]
            for source in candidates:
                matched = self._find_matched_template_group(
                    device.device_type, source, device.brand
                )
                if matched:
                    detail = group_service.get_group_detail(matched["id"])
                    if detail and detail.get("templates"):
                        template_group = detail
                        group_templates = detail["templates"]
                        grouped = True
                    break

        status = self.status_repo.find_by_device(device_id)
        reachable = status.reachable if status else None
        last_error = status.last_error if status else None
        last_checked_at = status.last_checked_at.isoformat() if status and status.last_checked_at else None
        overall_status, status_reason = self._dashboard_overall_status(
            has_credential, status, grouped
        )

        actual_source = next(
            (p for p in ("snmp", "ipmi", "zabbix") if p in creds), None
        )
        metric_status = []
        if overall_status in ("normal", "breached"):
            from app.persistence.device_metric_latest_repository import (
                DeviceMetricLatestRepository,
            )
            latest_rows = DeviceMetricLatestRepository().find_by_device(device_id)
            latest_map: dict = {}
            for row in latest_rows:
                if row.metric_key not in latest_map:
                    latest_map[row.metric_key] = row

            if grouped:
                seen_keys = {t.get("metric_key") for t in group_templates}
                display_templates = list(group_templates)
                try:
                    generic_tpls = self._template_repo.find_enabled_by_device_type(
                        getattr(device, "device_type", None) or "other", vendor=None
                    )
                    for t in generic_tpls:
                        if t.metric_key not in seen_keys and t.metric_key.startswith("if_"):
                            display_templates.append({
                                "metric_key": t.metric_key,
                                "display_name": t.display_name,
                                "source": t.source,
                            })
                            seen_keys.add(t.metric_key)
                except Exception:
                    logger.warning(
                        "dashboard 合并通用 if_* 模板失败 device_id=%s", device_id, exc_info=True
                    )
                for t in display_templates:
                    key = t.get("metric_key")
                    latest = latest_map.get(key)
                    metric_status.append(
                        {
                            "metric_key": key,
                            "metric_name": t.get("display_name") or key,
                            "source": actual_source or t.get("source"),
                            "value": latest.value if latest else None,
                            "severity": latest.severity if latest else None,
                            "breached": bool(latest.breached) if latest else False,
                            "collected_at": latest.collected_at.isoformat() if latest and latest.collected_at else None,
                        }
                    )
                if not metric_status:
                    overall_status, status_reason = "no_data", "模板组已命中但尚未采集到指标数据"
                elif any(m["breached"] for m in metric_status):
                    overall_status, status_reason = "breached", "存在超阈值指标，请关注"
            else:
                tpl_map: dict = {}
                try:
                    for t in self._template_repo.find_enabled_by_device_type(
                        getattr(device, "device_type", None) or "other"
                    ):
                        tpl_map[t.metric_key] = {
                            "display_name": t.display_name,
                        }
                except Exception:
                    logger.warning(
                        "metric_status 模板映射查询失败 device_id=%s", device_id, exc_info=True
                    )
                for key, latest in latest_map.items():
                    tpl_meta = tpl_map.get(key, {})
                    metric_status.append(
                        {
                            "metric_key": key,
                            "metric_name": tpl_meta.get("display_name") or key,
                            "source": actual_source,
                            "value": latest.value,
                            "severity": latest.severity,
                            "breached": bool(latest.breached),
                            "collected_at": latest.collected_at.isoformat() if latest.collected_at else None,
                        }
                    )
                if any(m["breached"] for m in metric_status):
                    overall_status, status_reason = "breached", "存在超阈值指标，请关注"
                elif not metric_status:
                    overall_status, status_reason = "no_data", "尚未采集到指标数据"

        return {
            "device_id": device_id,
            "has_credential": has_credential,
            "has_zabbix": has_zabbix,
            "configured_protocols": creds,
            "template_group": template_group,
            "grouped": grouped,
            "metric_status": metric_status,
            "overall_status": overall_status,
            "status_reason": status_reason,
            "reachable": reachable,
            "last_error": last_error,
            "last_checked_at": last_checked_at,
        }

    def _find_matched_template_group(self, device_type: str, source: str, brand: str | None) -> dict | None:
        from app.persistence.monitor_metric_template_group_repository import (
            MonitorMetricTemplateGroupRepository,
        )
        groups = MonitorMetricTemplateGroupRepository().find_enabled_by_device_type(
            device_type, source, vendor=brand
        )
        if not groups:
            return None
        group = groups[0]
        return {"id": group.id, "name": group.name}

    def _dashboard_overall_status(self, has_credential: bool, status, grouped: bool) -> tuple[str, str]:
        if not has_credential:
            return "no_credential", "设备未关联任何监控凭据"
        if status is None:
            return "not_probed", "已配置凭据，等待首次探测"
        if not status.reachable:
            if status.last_error in CONFIG_ERROR_CODES:
                return "credential_error", "监控凭据或配置异常，指标无法采集"
            return "unreachable", "设备当前不可达，暂无指标数据"
        if not grouped:
            return "normal", "未命中模板组，按默认规则采集指标"
        return "normal", "指标采集正常"

    def set_device_monitor_enabled(self, device_id: int, enabled: bool) -> dict:
        device = self._device_repo.find_by_id_or_404(device_id)
        existing = self.status_repo.find_by_device(device_id)
        if existing is not None:
            existing.monitor_enabled = enabled
            self.status_repo.session.flush()
        else:
            candidates = self._candidate_protocols(device)
            protocol = candidates[0] if candidates else MonitorProtocolCode.SNMP
            self.status_repo.upsert(
                device_id=device_id,
                protocol=protocol,
                reachable=False,
                last_checked_at=datetime.now(timezone.utc),
                monitor_enabled=enabled,
            )
        return {"device_id": device_id, "monitor_enabled": enabled}

    def batch_set_monitor_enabled(self, device_ids: list[int], enabled: bool) -> dict:
        updated = 0
        skipped = 0
        device_map = self._device_repo.find_by_ids(list(device_ids))
        status_map = self.status_repo.find_by_device_ids(list(device_ids))
        for did in device_ids:
            device = device_map.get(did)
            if device is None:
                skipped += 1
                continue
            existing = status_map.get(did)
            if existing is not None:
                existing.monitor_enabled = enabled
                self.status_repo.session.flush()
            else:
                candidates = self._candidate_protocols(device)
                protocol = candidates[0] if candidates else MonitorProtocolCode.SNMP
                self.status_repo.upsert(
                    device_id=did,
                    protocol=protocol,
                    reachable=False,
                    last_checked_at=datetime.now(timezone.utc),
                    monitor_enabled=enabled,
                )
            updated += 1
        return {"updated": updated, "skipped": skipped}

    def _apply_config_error(self, device, result: ProbeResult, protocol: str,
                            repo, old, now) -> None:
        repo.upsert(
            device_id=device.id,
            protocol=protocol,
            reachable=(old.reachable if old else bool(result.reachable)),
            ever_reachable=(old.ever_reachable if old else False),
            down_alerted=(old.down_alerted if old else False),
            down_episode=(old.down_episode if old else 0),
            consecutive_failures=(old.consecutive_failures if old else 0),
            latency_ms=result.latency_ms,
            extra={**((old.extra or {}) if old else {}), **(result.extra or {})},
            last_error=result.error,
            last_checked_at=now,
            last_reachable_at=(old.last_reachable_at if old else None),
            last_unreachable_at=(old.last_unreachable_at if old else None),
        )

    def apply_result(self, device, result: ProbeResult, protocol: str,
                     status_repo=None, threshold=None,
                     re_alert_interval_minutes=None, fallback_role=None,
                     blindspot_role=None) -> None:
        if getattr(result, "skipped", False):
            logger.warning(
                "探测被跳过（%s），不更新状态、不告警 device_id=%s",
                result.error, device.id,
            )
            return

        repo = status_repo or self.status_repo

        now = self._now()
        if threshold is None:
            threshold = self._cfg(
                "MONITOR_CONSECUTIVE_FAILURES_THRESHOLD", 2, session=repo.session
            )
        if re_alert_interval_minutes is None:
            re_alert_interval_minutes = self._cfg(
                "MONITOR_REALERT_INTERVAL_MINUTES", 360, session=repo.session
            )
        re_alert_interval = timedelta(minutes=re_alert_interval_minutes)

        old = repo.find_by_device(device.id)
        old_failures = old.consecutive_failures if old else 0
        old_ever = old.ever_reachable if old else False
        old_down_alerted = old.down_alerted if old else False
        old_episode = old.down_episode if old else 0
        old_extra = (old.extra or {}) if old else {}
        old_reachable_at = old.last_reachable_at if old else None
        old_unreachable_at = old.last_unreachable_at if old else None

        reachable = bool(result.reachable)

        if (not reachable) and result.error in CONFIG_ERROR_CODES:
            self._apply_config_error(device, result, protocol, repo, old, now)
            return

        tr = _compute_monitor_transition(
            reachable=reachable,
            threshold=threshold,
            re_alert_interval=re_alert_interval,
            now=now,
            old_failures=old_failures,
            old_ever=old_ever,
            old_down_alerted=old_down_alerted,
            old_episode=old_episode,
            last_alerted_at=old_extra.get("last_alerted_at"),
        )

        monitor_extra: dict = dict(old_extra)
        resolved = None

        if tr.became_down or tr.re_alert_due:
            resolved = self._resolve_alert_target(
                device, status_repo=repo,
                fallback_role=fallback_role, blindspot_role=blindspot_role,
            )
            has_recipient = resolved.has_recipient
            seq = 0 if tr.became_down else old_extra.get("re_alert_seq", 0) + 1
            monitor_extra["re_alert_seq"] = seq
            monitor_extra["last_alerted_at"] = now.isoformat()
            if not has_recipient:
                monitor_extra["alert_blindspot_at"] = now.isoformat()
            else:
                monitor_extra.pop("alert_blindspot_at", None)
        elif tr.recovered:
            monitor_extra.pop("alert_blindspot_at", None)
            monitor_extra["re_alert_seq"] = 0

        if protocol == MonitorProtocolCode.PING.value:
            monitor_extra["ping_reachable"] = bool(tr.reachable)

        fields = {
            "device_id": device.id,
            "protocol": protocol,
            "reachable": tr.reachable,
            "ever_reachable": tr.ever_reachable,
            "down_alerted": tr.down_alerted,
            "down_episode": tr.episode,
            "consecutive_failures": tr.failures,
            "latency_ms": result.latency_ms,
            "extra": {**(result.extra or {}), **monitor_extra},
            "last_error": result.error,
            "last_checked_at": now,
            "last_reachable_at": now if reachable else old_reachable_at,
            "last_unreachable_at": now if (not reachable) else old_unreachable_at,
        }

        repo.upsert(**fields)

        MonitorTimeseriesRepository(session=repo.session).add_event(
            device_id=device.id,
            protocol=protocol,
            reachable=tr.reachable,
            latency_ms=result.latency_ms,
            consecutive_failures=tr.failures,
            episode=tr.episode,
            is_alert=bool(tr.alert_action),
            error=result.error,
            extra={**(result.extra or {})},
            probed_at=now,
        )


        if tr.alert_action == "unreachable":
            self._enqueue_alert(
                device, NotificationTypeCode.DEVICE_UNREACHABLE, "critical", result, tr.episode, protocol,
                re_alert_seq=monitor_extra.get("re_alert_seq", 0), resolved=resolved,
                session=repo.session, now=now,
            )
        elif tr.alert_action == "recovered":
            self._enqueue_alert(
                device, NotificationTypeCode.DEVICE_RECOVERED, "info", result, tr.episode, protocol, 0,
                resolved=None, session=repo.session, now=now,
            )


    def _resolve_alert_target(self, device, status_repo=None,
                              fallback_role=None, blindspot_role=None) -> AlertTarget:
        responsible = getattr(device, "responsible_person", None)
        if responsible:
            return AlertTarget("user", responsible, ("inbox", "wechat_work", "feishu"), True, True)

        if fallback_role is None:
            fallback_role = self._cfg("MONITOR_FALLBACK_ROLE", "admin")
        if self._role_has_active_user(fallback_role, status_repo=status_repo):
            return AlertTarget("role", fallback_role, ("inbox",), False, True)

        if blindspot_role is None:
            blindspot_role = self._cfg("MONITOR_BLINDSPOT_ROLE", "admin")
        if blindspot_role != fallback_role and self._role_has_active_user(blindspot_role, status_repo=status_repo):
            logger.warning(
                "监控告警兜底角色 %s 无活跃用户，已回退到盲区应急组 %s (device_id=%s)",
                fallback_role, blindspot_role, getattr(device, "id", None),
            )
            return AlertTarget("role", blindspot_role, ("inbox",), False, True)

        logger.critical(
            "监控告警盲区：设备 %s 责任人缺失且兜底角色 %s / 盲区角色 %s 均无活跃用户，"
            "critical 告警将无法投递，请检查角色配置",
            getattr(device, "id", None), fallback_role, blindspot_role,
        )
        return AlertTarget("role", blindspot_role, ("inbox",), False, False)

    def _role_has_active_user(self, role_name: str, status_repo=None) -> bool:
        cached = _ROLE_ACTIVE_USER_CACHE.get(role_name)
        if cached is not None and cached[1] > time.monotonic():
            return cached[0]

        from app.models.user import User
        from app.models.rbac import Role, UserRole

        with _ROLE_ACTIVE_USER_CACHE_LOCK:
            cached = _ROLE_ACTIVE_USER_CACHE.get(role_name)
            if cached is not None and cached[1] > time.monotonic():
                return cached[0]

            session = (status_repo or self.status_repo).session
            result = (
                session.query(User)
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .filter(Role.name == role_name, User.status == 0)
                .first()
                is not None
            )
            _ROLE_ACTIVE_USER_CACHE[role_name] = (result, time.monotonic() + _ROLE_ACTIVE_USER_TTL)
            return result

    def _build_alert_payload(self, device, alert_type: str, severity: str, result: ProbeResult,
                              episode: int, protocol: str, re_alert_seq: int = 0,
                              resolved=None, now=None) -> dict:
        if resolved is None:
            resolved = self._resolve_alert_target(device)
        target_type = resolved.target_type
        target_id = resolved.target_id
        channels = resolved.channels
        allow_broadcast = resolved.allow_broadcast

        metadata = {
            "device_id": device.id,
            "device_name": getattr(device, "device_name", None),
            "management_ip": getattr(device, "management_ip", None),
            "protocol": protocol,
            "episode": episode,
            "error": result.error,
        }

        source = (result.extra or {}).get("source")

        if alert_type == NotificationTypeCode.DEVICE_RECOVERED:
            metadata["reachable"] = True
            if source == "zabbix":
                title = f"设备恢复（Zabbix）：{getattr(device, 'device_name', device.id)}"
                content = "Zabbix 监控显示设备已恢复。"
            else:
                title = f"设备恢复：{getattr(device, 'device_name', device.id)}"
                content = "设备已恢复可达。"
        else:
            metadata["reachable"] = False
            if source == "zabbix":
                title = f"设备异常（Zabbix）：{getattr(device, 'device_name', device.id)}"
                content = (
                    (result.error or "Zabbix 监控判定设备异常")
                    + "；注意 Zabbix available 状态未必等于设备网络直接不可达，请结合 Zabbix 面板确认。"
                )
            else:
                title = f"设备不可达：{getattr(device, 'device_name', device.id)}"
                content = result.error or "设备连续探测失败，已达到不可达阈值。"

        alert_type_str = getattr(alert_type, "value", alert_type)
        idempotency_now = now or self._now()
        from app.services.monitoring.alert_ingress import build_dedup_key
        _conn_index = f"{idempotency_now.date().isoformat()}_{episode}_{re_alert_seq}"
        _conn_action = "recover" if "recover" in alert_type_str else "raise"
        idempotency_key = build_dedup_key(
            alert_type_str, device.id, None, _conn_index, _conn_action
        )
        source_module = f"monitor:{device.id}"

        return {
            "type": alert_type,
            "severity": severity,
            "title": title,
            "content": content,
            "payload": metadata,
            "source_module": source_module,
            "target_type": target_type,
            "target_id": target_id,
            "channels": channels,
            "idempotency_key": idempotency_key,
            "allow_broadcast": allow_broadcast,
        }

    def _enqueue_alert(self, device, alert_type: str, severity: str, result: ProbeResult,
                       episode: int, protocol: str, re_alert_seq: int = 0,
                       resolved=None, session=None, now=None) -> None:
        payload = self._build_alert_payload(
            device, alert_type, severity, result, episode, protocol,
            re_alert_seq=re_alert_seq, resolved=resolved, now=now,
        )

        try:
            from app.core.enums import DeviceStatus
            if device.status == DeviceStatus.MAINTENANCE:
                logger.info(
                    "设备维护中，告警静默 device=%s alert_type=%s",
                    device.id, getattr(alert_type, "value", alert_type),
                )
                return
        except Exception:
            logger.warning("维护模式判定失败（fail-open 不阻断）", exc_info=True)

        try:
            from app.services.monitoring.silence_service import is_silenced
            alert_type_str = getattr(alert_type, "value", alert_type)
            if is_silenced(device.id, alert_type_str):
                logger.info(
                    "告警被静默规则命中 device=%s alert_type=%s",
                    device.id, alert_type_str,
                )
                return
        except Exception:
            logger.warning("告警抑制判定失败（fail-open 不阻断）", exc_info=True)

        try:
            from app.services.monitoring.alert_suppression_service import should_emit
            decision = should_emit(payload["idempotency_key"])
            if decision["suppressed"]:
                logger.info(
                    "告警被风暴抑制 device=%s alert_type=%s dedup_key=%s next_allowed_at=%s",
                    device.id, alert_type, payload["idempotency_key"],
                    decision.get("next_allowed_at"),
                )
                return
            if decision["aggregated"]:
                payload = dict(payload)
                payload["suppressed_count"] = decision["suppressed_count"]
        except Exception:
            logger.warning("告警抑制判定失败（fail-open 不阻断入箱）", exc_info=True)

        outbox_row = MonitorAlertOutboxRepository(session=session).add(
            device.id, alert_type, severity, payload["idempotency_key"], payload,
        )

        try:
            import json
            import time as _time
            from app.services.monitoring.data_scope_service import (
                get_users_with_device_access,
            )
            from app.services.switch_events import _redis_publish_global

            target_user_ids = get_users_with_device_access(device.id)
            alert_type_str = getattr(alert_type, "value", alert_type)
            _redis_publish_global(json.dumps({
                "event_type": "monitor_alert",
                "device_id": device.id,
                "alert_type": alert_type_str,
                "severity": severity,
                "dedup_key": payload["idempotency_key"],
                "outbox_id": outbox_row.id,
                "timestamp": _time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", _time.gmtime()
                ),
                "target_user_ids": target_user_ids if target_user_ids else None,
                "payload": payload,
            }, ensure_ascii=False))
        except Exception:
            logger.warning("SSE 推送失败（不影响告警入箱）", exc_info=True)


def get_overview(failure_threshold: int = 2) -> dict:
    from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository
    from app.persistence.device_metric_alert_state_repository import DeviceMetricAlertStateRepository
    status_repo = DeviceMonitorStatusRepository()
    _metric_alert_state_repo = DeviceMetricAlertStateRepository()
    stats = status_repo.overview_stats(failure_threshold=failure_threshold)
    by_protocol = status_repo.distribution_by_protocol()
    by_device_type = status_repo.distribution_by_device_type()
    recent = status_repo.recent_alerts(limit=20)
    alert_stats = _metric_alert_state_repo.overview_alert_stats()
    return {
        **stats,
        **alert_stats,
        "by_protocol": by_protocol,
        "by_device_type": by_device_type,
        "recent_alerts": recent,
    }


def list_statuses(status_filter: str = None, page: int = 1, per_page: int = 20,
                  keyword: str = None) -> dict:
    from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository
    from app.persistence.device_metric_alert_state_repository import DeviceMetricAlertStateRepository
    status_repo = DeviceMonitorStatusRepository()
    _metric_alert_state_repo = DeviceMetricAlertStateRepository()
    device_ids = None
    if status_filter == "metric_alerting":
        device_ids = list(_metric_alert_state_repo.active_alerts_by_device().keys())
    elif status_filter == "interrupted":
        device_ids = list(_metric_alert_state_repo.interrupted_device_ids())

    total, items = status_repo.list_with_device(
        status_filter=status_filter, page=page, per_page=per_page, device_ids=device_ids,
        keyword=keyword,
    )
    alert_by_device = _metric_alert_state_repo.active_alerts_by_device()
    interrupted_ids = _metric_alert_state_repo.interrupted_device_ids()
    for row in items:
        agg = alert_by_device.get(row["device_id"], {})
        row["active_metric_alerts"] = agg.get("alert_count", 0)
        row["max_alert_severity"] = agg.get("max_severity", 0)
        row["monitor_interrupted"] = row["device_id"] in interrupted_ids
    return {"total": total, "items": items}


def list_alerts(params: dict) -> dict:
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    alert_repo = MonitorAlertOutboxRepository()
    page = params.get("page") or 1
    per_page = params.get("per_page") or 20

    device_ids = None
    if params.get("scope") == "mine":
        user_id = params.get("user_id")
        if user_id is not None:
            from app.models.device import Device
            device_ids = [
                d.id for d in
                alert_repo.session.query(Device.id)
                .filter(Device.responsible_person == user_id, Device.deleted_at.is_(None))
                .all()
            ]

    total, items = alert_repo.list_with_device(
        alert_type=params.get("alert_type"),
        severity=params.get("severity"),
        status=params.get("status"),
        device_id=params.get("device_id"),
        start_date=params.get("start_date"),
        end_date=params.get("end_date"),
        page=page,
        per_page=per_page,
        device_ids=device_ids,
        metric_key=params.get("metric_key"),
        index_key=params.get("index_key"),
    )
    return {"total": total, "items": items, "page": page, "per_page": per_page}


def get_alert_detail(alert_id: int) -> dict:
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    from app.exceptions.business import BusinessLogicError
    alert_repo = MonitorAlertOutboxRepository()
    item = alert_repo.get_by_id_with_device(alert_id)
    if item is None:
        raise BusinessLogicError("告警记录不存在", status_code=404)
    return item


def retry_alert(alert_id: int) -> dict:
    from app.models.monitor_alert_outbox import MonitorAlertOutbox
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    from app.exceptions.business import BusinessLogicError
    alert_repo = MonitorAlertOutboxRepository()
    ok = alert_repo.reset_to_pending(alert_id)
    if not ok:
        existing = alert_repo.session.get(MonitorAlertOutbox, alert_id)
        if existing is None:
            raise BusinessLogicError("告警记录不存在", status_code=404)
        return {
            "retried": False,
            "alert_id": alert_id,
            "status": existing.status,
            "message": "该告警非 failed 状态，无需重试",
        }
    return {"retried": True, "alert_id": alert_id, "status": "pending"}


def ack_alert(alert_id: int, user: str, note: Optional[str] = None) -> dict:
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    from app.exceptions.business import BusinessLogicError
    alert_repo = MonitorAlertOutboxRepository()
    row = alert_repo.acknowledge(alert_id, user=user, note=note)
    if row is None:
        raise BusinessLogicError("告警记录不存在", status_code=404)
    return {
        "id": row.id,
        "acknowledged_by": row.acknowledged_by,
        "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
        "ack_note": row.ack_note,
    }


def batch_ack_alert(ids: list, user: str, note: Optional[str] = None) -> dict:
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    alert_repo = MonitorAlertOutboxRepository()
    return alert_repo.batch_acknowledge(ids, user=user, note=note)


def batch_retry_alert(ids: list) -> dict:
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    alert_repo = MonitorAlertOutboxRepository()
    return alert_repo.batch_reset_to_pending(ids)


def close_alert(alert_id: int, user: str, reason: Optional[str] = None) -> dict:
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    from app.exceptions.business import BusinessLogicError
    alert_repo = MonitorAlertOutboxRepository()
    row = alert_repo.close_alert(alert_id, user=user, reason=reason)
    if row is None:
        raise BusinessLogicError("告警记录不存在", status_code=404)
    return {
        "id": row.id,
        "closed_by": row.closed_by,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "close_reason": row.close_reason,
    }


def batch_close_alert(ids: list, user: str, reason: Optional[str] = None) -> dict:
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    alert_repo = MonitorAlertOutboxRepository()
    return alert_repo.batch_close(ids, user=user, reason=reason)


def get_probe_trends(
    device_id: int,
    from_: Optional[datetime] = None,
    to_: Optional[datetime] = None,
    protocol: Optional[str] = None,
) -> dict:
    if to_ is None:
        to_ = datetime.now(timezone.utc).replace(tzinfo=None)
    if from_ is None:
        from_ = to_ - timedelta(days=7)

    retention_floor = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
    ts_repo = MonitorTimeseriesRepository()
    if from_ >= retention_floor:
        agg = ts_repo.aggregate_events(
            device_id, from_=from_, to_=to_, protocol=protocol
        )
    else:
        agg = ts_repo.aggregate_hourly(
            device_id, from_=from_, to_=to_, protocol=protocol
        )
    return agg


def aggregate_alerts(
    window_minutes: int = 5,
    start_date=None,
    end_date=None,
    severity: Optional[str] = None,
    only_active: bool = True,
    max_groups: int = 50,
) -> list:
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    repo = MonitorAlertOutboxRepository()
    return repo.aggregate_alerts(
        window_minutes=window_minutes,
        start_date=start_date,
        end_date=end_date,
        severity=severity,
        only_active=only_active,
        max_groups=max_groups,
    )


def get_alert_statistics(
    start_date=None,
    end_date=None,
    device_id: Optional[int] = None,
    severity: Optional[str] = None,
    bucket: str = "hour",
    top_n: int = 10,
) -> dict:
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    from datetime import datetime

    def _parse_dt(v):
        if v is None or isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(v)
        except (ValueError, TypeError):
            return None

    repo = MonitorAlertOutboxRepository()
    return repo.statistics(
        start_date=_parse_dt(start_date),
        end_date=_parse_dt(end_date),
        device_id=device_id,
        severity=severity,
        bucket=bucket,
        top_n=top_n,
    )
