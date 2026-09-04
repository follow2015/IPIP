# -*- coding: utf-8 -*-
"""根因分析增强：检查同机房/同上游/同网段设备是否同时异常。

设计文档第四节：定位故障域而非单设备；把"当前值 vs 基线偏离倍数"作为结构化事实
喂给 LLM，而不是让 LLM 自己判断"这个值算不算高"。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.device import Device
from app.models.device_metric_latest import DeviceMetricLatest
from app.services.ai.baseline_service import BaselineService
from app.utils.logging import get_logger
from extensions import db

logger = get_logger(__name__)


class RootCauseAnalyzer:
    """根因分析：单设备异常 → 故障域定位。"""

    def __init__(self, baseline_service: Optional[BaselineService] = None):
        self.baseline = baseline_service or BaselineService()

    def analyze_fault_domain(
        self,
        device_id: int,
        anomalous_metric: str,
    ) -> Dict[str, Any]:
        """分析故障域：同机房/同上游设备是否同时异常。

        Args:
            device_id: 异常设备 ID。
            anomalous_metric: 异常指标 key（如 cpu_usage）。

        Returns:
            {"fault_domain", "related_anomalies", "scope"}
            - fault_domain: "single"（单设备）/ "room"（同机房）/ "uplink"（同上游）
            - related_anomalies: 同时异常的设备列表
            - scope: 故障范围描述
        """
        device = db.session.get(Device, device_id)
        if device is None:
            return {"fault_domain": "unknown", "related_anomalies": [], "scope": "设备不存在"}

        related: List[Dict[str, Any]] = []

        cabinet_id = device.cabinet_id
        if cabinet_id:
            room_devices = (
                db.session.query(Device)
                .filter(Device.cabinet_id == cabinet_id, Device.id != device_id)
                .all()
            )
            for d in room_devices:
                anomaly = self._check_device_anomaly(d.id, anomalous_metric)
                if anomaly:
                    related.append({"device_id": d.id, "device_name": d.device_name,
                                    "relation": "same_cabinet", **anomaly})

        try:
            uplink_id = device.uplink_device_id
        except Exception:
            uplink_id = None
        if uplink_id:
            from app.models.device_switch_ext import DeviceSwitchExt
            downstream_exts = (
                db.session.query(DeviceSwitchExt)
                .filter_by(uplink_device_id=uplink_id)
                .all()
            )
            for ext in downstream_exts:
                if ext.device_id == device_id or ext.device is None:
                    continue
                anomaly = self._check_device_anomaly(ext.device_id, anomalous_metric)
                if anomaly:
                    related.append({"device_id": ext.device_id,
                                    "device_name": ext.device.device_name,
                                    "relation": "same_uplink", **anomaly})

        if not related:
            return {
                "fault_domain": "single",
                "related_anomalies": [],
                "scope": "仅单设备异常，疑似设备本地问题",
            }
        relations = {r["relation"] for r in related}
        if "same_uplink" in relations:
            domain = "uplink"
            scope = f"同上游设备 {len(related)} 台同时异常，疑似上游链路/汇聚设备问题"
        else:
            domain = "room"
            scope = f"同机房 {len(related)} 台设备同时异常，疑似机房级故障（电源/网络/环境）"
        return {"fault_domain": domain, "related_anomalies": related, "scope": scope}

    def _check_device_anomaly(
        self, device_id: int, metric_key: str
    ) -> Optional[Dict[str, Any]]:
        """检查单设备某指标是否异常（基线偏离）。"""
        latest = (
            db.session.query(DeviceMetricLatest)
            .filter_by(device_id=device_id, metric_key=metric_key)
            .first()
        )
        if latest is None or latest.value is None:
            return None
        try:
            current = float(latest.value)
        except (TypeError, ValueError):
            return None
        result = self.baseline.detect_anomaly(device_id, metric_key, current)
        if result.get("is_anomaly"):
            return {
                "metric": metric_key,
                "current": current,
                "deviation_pct": result.get("deviation_pct"),
                "reason": result.get("reason"),
            }
        return None

    def build_structured_facts(
        self,
        device_id: int,
        inspection_result: Dict[str, Any],
    ) -> List[str]:
        """把"当前值 vs 基线偏离倍数"转为结构化事实列表，喂给 LLM。

        设计文档第四节：不让 LLM 自己判断"这个值算不算高"，
        而是把计算好的偏离倍数作为事实提供。

        Args:
            device_id: 设备 ID。
            inspection_result: device.live_inspection 的返回（含 checks）。

        Returns:
            结构化事实列表，如 ["CPU 86%（基线 41%，偏离 +110%，命中 3-sigma）"]
        """
        facts: List[str] = []
        checks = inspection_result.get("checks", {}) if isinstance(inspection_result, dict) else {}
        for check_name, result in checks.items():
            if not isinstance(result, dict) or result.get("supported") is False:
                continue
            value = result.get("value")
            metric_key = result.get("metric_key", check_name)
            if value is None:
                continue
            anomaly = self.baseline.detect_anomaly(device_id, metric_key, float(value))
            baseline = anomaly.get("baseline") or {}
            mean = baseline.get("mean")
            deviation = anomaly.get("deviation_pct")
            reason = anomaly.get("reason", "")

            parts = [f"{check_name} {value}"]
            if mean is not None:
                parts.append(f"基线 {mean:.1f}")
            if deviation is not None:
                parts.append(f"偏离 {deviation:+.0f}%")
            if reason == "baseline_3sigma":
                parts.append("命中 3-sigma")
            elif reason == "insufficient_samples":
                parts.append("基线样本不足")
            facts.append("（".join([parts[0], "，".join(parts[1:])]) + "）" if len(parts) > 1 else parts[0])
        return facts
