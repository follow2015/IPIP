# -*- coding: utf-8 -*-
"""根因分析增强：检查同机柜/同机房/同上游设备是否同时异常。

设计文档第四节：定位故障域而非单设备；把"当前值 vs 基线偏离倍数"作为结构化事实
喂给 LLM，而不是让 LLM 自己判断"这个值算不算高"。

故障域分三级（范围由小到大）：cabinet（同机柜）→ room（同机房）→ uplink（同上游）。
机柜级（PDU/接入交换机）与机房级（电源/环境/汇聚）的处置动作完全不同，必须分开判定，
不可混用"机房"口径描述同机柜设备。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.models.device import Device
from app.models.device_metric_latest import DeviceMetricLatest
from app.services.ai.baseline_service import BaselineService
from app.utils.logging import get_logger
from extensions import db

logger = get_logger(__name__)

MAX_PEER_DEVICES = 200

RELATION_PRIORITY = ("same_uplink", "same_room", "same_cabinet")
RELATION_LABEL = {
    "same_uplink": "同上游设备",
    "same_room": "同机房其它机柜",
    "same_cabinet": "同机柜",
}


class RootCauseAnalyzer:
    """根因分析：单设备异常 → 故障域定位。"""

    def __init__(self, baseline_service: Optional[BaselineService] = None):
        self.baseline = baseline_service or BaselineService()

    def analyze_fault_domain(
        self,
        device_id: int,
        anomalous_metric: str,
    ) -> Dict[str, Any]:
        """分析故障域：同机柜/同机房/同上游设备是否同时异常。

        Args:
            device_id: 异常设备 ID。
            anomalous_metric: 异常指标 key（如 cpu_usage）。

        Returns:
            {"fault_domain", "related_anomalies", "scope"}
            - fault_domain: "unknown"（设备不存在）/ "single"（单设备）
              / "cabinet"（同机柜）/ "room"（同机房，跨机柜）/ "uplink"（同上游）
            - related_anomalies: 同时异常的设备列表，每项带 relation
              （same_cabinet / same_room / same_uplink）。一台设备可能同时命中
              多级，此时取**范围最大**的那一级作标签，且只做一次基线检测
            - scope: 故障范围描述
        """
        device = db.session.get(Device, device_id)
        if device is None:
            return {"fault_domain": "unknown", "related_anomalies": [], "scope": "设备不存在"}

        cabinet_id = device.cabinet_id
        levels: Dict[str, Dict[int, Device]] = {}
        if cabinet_id:
            levels["same_cabinet"] = {
                d.id: d
                for d in db.session.query(Device)
                .filter(Device.cabinet_id == cabinet_id, Device.id != device_id)
                .limit(MAX_PEER_DEVICES)
                .all()
            }

        room_id = self._resolve_room_id(cabinet_id)
        if room_id:
            from app.models.cabinet import Cabinet

            peer_cabinet_ids = [
                row[0]
                for row in db.session.query(Cabinet.id)
                .filter(Cabinet.room_id == room_id, Cabinet.id != cabinet_id)
                .all()
            ]
            if peer_cabinet_ids:
                levels["same_room"] = {
                    d.id: d
                    for d in db.session.query(Device)
                    .filter(Device.cabinet_id.in_(peer_cabinet_ids))
                    .limit(MAX_PEER_DEVICES)
                    .all()
                }

        try:
            uplink_id = device.uplink_device_id
        except Exception:  # noqa: BLE001
            uplink_id = None
        if uplink_id:
            from app.models.device_switch_ext import DeviceSwitchExt

            levels["same_uplink"] = {
                ext.device_id: ext.device
                for ext in db.session.query(DeviceSwitchExt)
                .filter_by(uplink_device_id=uplink_id)
                .all()
                if ext.device is not None and ext.device_id != device_id
            }

        merged: Dict[int, Tuple[str, Device]] = {}
        for relation in RELATION_PRIORITY:
            for dev_id, dev in levels.get(relation, {}).items():
                if dev_id not in merged:
                    merged[dev_id] = (relation, dev)

        related: List[Dict[str, Any]] = []
        for dev_id, (relation, dev) in merged.items():
            anomaly = self._check_device_anomaly(dev_id, anomalous_metric)
            if anomaly:
                related.append({"device_id": dev_id, "device_name": dev.device_name,
                                "relation": relation, **anomaly})

        if not related:
            return {
                "fault_domain": "single",
                "related_anomalies": [],
                "scope": "仅单设备异常，疑似设备本地问题",
            }
        present = {r["relation"] for r in related}
        for relation, domain, hint in (
            ("same_uplink", "uplink", "上游链路/汇聚设备故障"),
            ("same_room", "room", "机房级故障（电源/网络/环境）"),
            ("same_cabinet", "cabinet", "机柜级故障（PDU/接入交换机/布线）"),
        ):
            if relation in present:
                count = sum(1 for r in related if r["relation"] == relation)
                return {
                    "fault_domain": domain,
                    "related_anomalies": related,
                    "scope": f"{RELATION_LABEL[relation]} {count} 台设备同时异常，疑似{hint}",
                }
        return {"fault_domain": "single", "related_anomalies": related,
                "scope": "仅单设备异常，疑似设备本地问题"}

    @staticmethod
    def _resolve_room_id(cabinet_id: Optional[int]) -> Optional[int]:
        """取机柜所属机房；机柜缺失（已物理删除）时返回 None。"""
        if not cabinet_id:
            return None
        from app.models.cabinet import Cabinet

        cabinet = db.session.get(Cabinet, cabinet_id)
        return cabinet.room_id if cabinet else None

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
