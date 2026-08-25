# -*- coding: utf-8 -*-
"""指标告警状态仓库（DeviceMetricAlertStateRepository）

基于 ``device_metric_alert_state``（breached=True 的行）聚合「当前活跃指标告警」，
供前端健康态势展示：

- ``overview_alert_stats``：全网活跃指标告警统计（告警中设备数 / 严重告警设备数 / 监控中断数）；
- ``active_alerts_by_device``：各设备活跃指标告警（数量 + 最高 severity），供设备列表联表；
- ``active_metric_alerts``：某设备的活跃指标告警明细。

监控中断（monitor_interrupted）单独归类：它不属于 SNMP/IPMI 采集的指标，而是
worker 侧判定「设备超时无新指标」写入的状态，见 MetricAlertService。
"""
from typing import Dict, List, Optional

from sqlalchemy import func

from extensions import db
from app.models.device_metric_alert_state import DeviceMetricAlertState

_SEVERITY_RANK = {"ok": 0, "info": 1, "warn": 2, "warning": 2, "crit": 3, "critical": 3}


class DeviceMetricAlertStateRepository:

    def __init__(self, session=None):
        self.session = session or db.session


    def overview_alert_stats(self) -> Dict[str, int]:
        rows = (
            self.session.query(
                DeviceMetricAlertState.device_id,
                DeviceMetricAlertState.alert_type,
                DeviceMetricAlertState.severity,
            )
            .filter(DeviceMetricAlertState.breached.is_(True))
            .all()
        )
        alerting: set = set()
        crit: set = set()
        warn: set = set()
        interrupted: set = set()
        for device_id, alert_type, severity in rows:
            alerting.add(device_id)
            if alert_type == "monitor_interrupted":
                interrupted.add(device_id)
            sev = str(severity or "").lower()
            if _SEVERITY_RANK.get(sev, 0) >= 3:
                crit.add(device_id)
            elif _SEVERITY_RANK.get(sev, 0) >= 2:
                warn.add(device_id)
        return {
            "alerting_devices": len(alerting),
            "crit_alert_devices": len(crit),
            "warn_alert_devices": len(warn),
            "interrupted_devices": len(interrupted),
        }


    def active_alerts_by_device(self) -> Dict[int, Dict[str, int]]:
        rows = (
            self.session.query(
                DeviceMetricAlertState.device_id,
                DeviceMetricAlertState.severity,
                func.count(DeviceMetricAlertState.id).label("cnt"),
            )
            .filter(DeviceMetricAlertState.breached.is_(True))
            .group_by(DeviceMetricAlertState.device_id, DeviceMetricAlertState.severity)
            .all()
        )
        result: Dict[int, Dict[str, int]] = {}
        for device_id, severity, cnt in rows:
            entry = result.setdefault(device_id, {"alert_count": 0, "max_severity": 0})
            entry["alert_count"] += int(cnt or 0)
            sev = _SEVERITY_RANK.get(str(severity or "").lower(), 0)
            if sev > entry["max_severity"]:
                entry["max_severity"] = sev
        return result

    def active_metric_alerts(self, device_id: int) -> List[DeviceMetricAlertState]:
        return (
            self.session.query(DeviceMetricAlertState)
            .filter(
                DeviceMetricAlertState.device_id == device_id,
                DeviceMetricAlertState.breached.is_(True),
            )
            .all()
        )

    def is_monitor_interrupted(self, device_id: int) -> bool:
        return device_id in self.interrupted_device_ids()

    def interrupted_device_ids(self) -> set:
        rows = (
            self.session.query(DeviceMetricAlertState.device_id)
            .filter(
                DeviceMetricAlertState.alert_type == "monitor_interrupted",
                DeviceMetricAlertState.breached.is_(True),
            )
            .all()
        )
        return {r[0] for r in rows}
