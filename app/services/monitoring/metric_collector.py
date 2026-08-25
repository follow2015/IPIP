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
    """指标采集器（组合模板仓库 + 适配器 + 阈值评估）"""

    def __init__(self, template_repo, threshold_service=None, _tpl_cache=None):
        """G15 优化 A：``_tpl_cache`` 为「本轮内」共享的 device_type → 模板缓存。

        由调用方（worker）每轮传入一个共享 dict，轮末 clear，避免跨轮脏数据；
        同 ``device_type`` 的 N 台设备一轮内模板查询次数由 N 次降为 1 次（DB QPS 优化）。
        """
        self._template_repo = template_repo
        self._threshold_service = threshold_service or MetricThresholdService()
        self._tpl_cache = _tpl_cache if _tpl_cache is not None else {}
        self._tpl_cache_lock = threading.Lock()

    def _templates_for(self, device_type: str, vendor: str | None = None) -> list:
        """本轮内缓存 (device_type, vendor) → 启用模板（展平成 dict）；命中直接返回，减少 DB 查询。

        线程安全：double-checked locking 防止并发 miss 时重复查库。

        返回 dict 列表而非 ORM 对象：worker 每台设备在独立 session 内查询，
        finally: db.session.remove() 会使 ORM 实例 detached；若缓存 ORM 对象，
        下一台设备命中缓存时访问属性即触发 DetachedInstanceError。
        展平成 dict 后缓存与 session 生命周期解耦，安全跨设备复用。
        """
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
        """对设备按启用模板采集并判定指标，返回结构化结果。

        adapter 需实现 ``collect_metrics(device, credential, templates) -> dict``
        （SNMPAdapter 已实现；IPMIAdapter 将于后续扩展）。

        模板选择优先级：
        1. 设备显式绑定组（device.metric_template_group_id）→ 采该组内启用模板
           + 自动合并通用组（vendor=None）模板，按 metric_key 去重（厂商组优先）；
        2. 未绑定 → 按 device_type + vendor 自动匹配（vendor=None 的通用模板始终命中）。
        """
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
        """返回显式绑定组内启用模板（展平成 dict）。

        显式绑定时不混入通用组模板，避免同 OID 重复采集。
        """
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
        """将 SNMP TimeTicks（1/100 秒原始整数）转为可读时长。

        sysUpTime 等 TimeTicks 类型在 SNMP 协议中以 1/100 秒为单位计数，
        直接展示裸数字（如 599151395）对用户无意义。此处转为
        "X天Y小时Z分W秒" 格式（不足的高位单位省略）。

        非 numeric 输入（如 "No Such Object" 错误字符串）原样返回。
        """
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
        """判定模板是否为 TimeTicks 类型。

        优先看 metric_type 字段；若标错（如 hrSystemUptime 误标为 gauge），
        按 OID 前缀兜底识别已知 TimeTicks OID。
        """
        if tpl.get("metric_type") == "timeticks":
            return True
        oid = tpl.get("oid") or ""
        return any(oid.startswith(p) for p in cls._TIMETICKS_OID_PREFIXES)

    def _evaluate(self, raw: dict, templates) -> dict:
        """对原始采集结果按模板阈值评估，产出告警判定。

        templates 为 dict 列表（_templates_for 展平），用 dict 取值而非 ORM 属性。
        """
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
