# -*- coding: utf-8 -*-
"""指标采集器（MetricCollector）

把「指标模板 → 适配器采集 → 阈值评估」串起来，供 worker 的 snmp loop 在
连通性探测之后对设备做业务指标采集。

流程：
1. 查询设备类型对应的启用指标模板（MonitorMetricTemplateRepository）。
2. 调用适配器 ``collect_metrics`` 采集（SNMP 走 MIB 符号 / IPMI 走传感器）。
3. 用 ``MetricThresholdService`` 按 metric_type 评估每条指标，产出告警判定。

告警入箱（AlertOutbox）由上层调用方负责；本类只负责「采集 + 判定」并返回结果，
保持职责单一、便于单测。

返回结构::

    {
      "metric_key": {
        "index": {"value": ..., "severity": "crit|warn|ok", "breached": bool}
      }
    }
"""
import threading

from app.services.monitoring.metric_threshold_service import MetricThresholdService


class MetricCollector:

    def __init__(self, template_repo, threshold_service=None, _tpl_cache=None):
        self._template_repo = template_repo
        self._threshold_service = threshold_service or MetricThresholdService()
        self._tpl_cache = _tpl_cache if _tpl_cache is not None else {}
        self._tpl_cache_lock = threading.Lock()

    def _templates_for(self, device_type: str, vendor: str | None = None) -> list:
        cache_key = (device_type, vendor)
        cached = self._tpl_cache.get(cache_key)
        if cached is not None:
            return cached
        with self._tpl_cache_lock:
            cached = self._tpl_cache.get(cache_key)
            if cached is not None:
                return cached
            templates = self._template_repo.find_enabled_by_device_type(device_type, vendor=vendor)
            specs = [self._to_spec(t) for t in templates] if templates else []
            self._tpl_cache[cache_key] = specs or []
            return self._tpl_cache[cache_key]

    def collect(self, device, adapter, credential) -> dict:
        group_id = getattr(device, "metric_template_group_id", None)
        if group_id:
            vendor_templates = self._templates_for_group(group_id)
            device_type = getattr(device, "device_type", "other") or "other"
            generic_templates = self._templates_for(device_type, vendor=None)
            seen_keys = {t["metric_key"] for t in vendor_templates}
            templates = vendor_templates + [
                t for t in generic_templates
                if t["metric_key"] not in seen_keys
                and t["metric_key"].startswith("if_")
            ]
        else:
            device_type = getattr(device, "device_type", "other") or "other"
            vendor = getattr(device, "brand", None)
            templates = self._templates_for(device_type, vendor=vendor)
        if not templates:
            return {}

        raw = adapter.collect_metrics(device, credential, templates)
        return self._evaluate(raw, templates)

    def _templates_for_group(self, group_id: int) -> list:
        cache_key = ("group", group_id)
        cached = self._tpl_cache.get(cache_key)
        if cached is not None:
            return cached
        with self._tpl_cache_lock:
            cached = self._tpl_cache.get(cache_key)
            if cached is not None:
                return cached
            from app.persistence.monitor_metric_template_group_repository import (
                MonitorMetricTemplateGroupRepository,
            )
            group_repo = MonitorMetricTemplateGroupRepository()
            tpls = group_repo.list_templates_in_group(group_id)
            tpls = [t for t in tpls if t.enabled]
            specs = [self._to_spec(t) for t in tpls]
            self._tpl_cache[cache_key] = specs
            return specs

    def _to_spec(self, tpl) -> dict:
        return {
            "metric_key": tpl.metric_key,
            "mib": tpl.mib,
            "oid_symbol": tpl.oid_symbol,
            "oid": tpl.oid,
            "zabbix_item_key": tpl.zabbix_item_key,
            "index_kind": tpl.index_kind,
            "metric_type": tpl.metric_type,
            "unit": tpl.unit,
            "threshold": tpl.threshold,
        }

    @staticmethod
    def _format_timeticks(value) -> str:
        try:
            total_cs = int(value)
        except (TypeError, ValueError):
            return value
        if total_cs < 0:
            return str(value)
        total_seconds = total_cs // 100
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}天")
        if hours:
            parts.append(f"{hours}小时")
        if minutes:
            parts.append(f"{minutes}分")
        if seconds or not parts:
            parts.append(f"{seconds}秒")
        return "".join(parts)

    _TIMETICKS_OID_PREFIXES = (
        "1.3.6.1.2.1.1.3.",
        "1.3.6.1.2.1.25.1.1.",
    )

    @classmethod
    def _is_timeticks(cls, tpl: dict) -> bool:
        if tpl.get("metric_type") == "timeticks":
            return True
        oid = tpl.get("oid") or ""
        return any(oid.startswith(p) for p in cls._TIMETICKS_OID_PREFIXES)

    def _evaluate(self, raw: dict, templates) -> dict:
        tpl_by_key = {t["metric_key"]: t for t in templates}
        result: dict = {}
        for metric_key, table in (raw or {}).items():
            tpl = tpl_by_key.get(metric_key)
            if tpl is None:
                continue
            evaluated: dict = {}
            is_timeticks = self._is_timeticks(tpl)
            for index, value in (table or {}).items():
                severity, breached = self._threshold_service.evaluate(
                    tpl["metric_type"], value, tpl.get("threshold")
                )
                if is_timeticks:
                    value = self._format_timeticks(value)
                evaluated[str(index)] = {
                    "value": value,
                    "severity": severity,
                    "breached": breached,
                }
            result[metric_key] = evaluated
        return result
