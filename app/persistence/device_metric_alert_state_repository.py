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
    """指标告警状态仓库"""

    def __init__(self, session=None):
        self.session = session or db.session


    def overview_alert_stats(self) -> Dict[str, int]:
        """返回活跃指标告警的全网统计（基于 breached=True 且按设备去重）。

        - alerting_devices：存在任一活跃指标告警（含监控中断）的设备数
        - crit_alert_devices：活跃告警中最高 severity 为 crit/critical 的设备数
        - warn_alert_devices：最高为 warn/warning 的设备数
        - interrupted_devices：处于监控中断的设备数
        """
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
        """返回各设备活跃指标告警聚合：{device_id: {alert_count, max_severity}}。

        仅统计 breached=True 的行；max_severity 取该设备活跃告警的最高级别数字。
        """
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
        """返回某设备的活跃指标告警明细。"""
        return (
            self.session.query(DeviceMetricAlertState)
            .filter(
                DeviceMetricAlertState.device_id == device_id,
                DeviceMetricAlertState.breached.is_(True),
            )
            .all()
        )


    def list_by_device(self, device_id: int) -> List[DeviceMetricAlertState]:
        """取该设备全部告警态行（调用方构造 {(metric_key, index_key): state} 映射）。

        P1-1 修复的批量预取入口：一次取全替代逐 (metric, index) 的 N+1。
        """
        return (
            self.session.query(DeviceMetricAlertState)
            .filter(DeviceMetricAlertState.device_id == device_id)
            .all()
        )

    def find_by_identity(
        self, device_id: int, metric_key: str, index_key: str,
    ) -> Optional[DeviceMetricAlertState]:
        """按 (device_id, metric_key, index_key) 取一行（可能不存在 ⇒ None）。

        三元组是唯一键 ⇒ ``one_or_none`` 与 ``first`` 同结果（两种调用点共用本方法）。
        """
        return (
            self.session.query(DeviceMetricAlertState)
            .filter(
                DeviceMetricAlertState.device_id == device_id,
                DeviceMetricAlertState.metric_key == metric_key,
                DeviceMetricAlertState.index_key == index_key,
            )
            .one_or_none()
        )

    def require_by_identity(
        self, device_id: int, metric_key: str, index_key: str,
    ) -> DeviceMetricAlertState:
        """同上，但**必须命中**（``.one()`` 语义，缺行抛 NoResultFound）。

        用途：MySQL ODKU upsert 后的回查 —— 刚写入的行必然存在，缺行说明
        写入失败，应显式报错而非静默返回 None。
        """
        return (
            self.session.query(DeviceMetricAlertState)
            .filter(
                DeviceMetricAlertState.device_id == device_id,
                DeviceMetricAlertState.metric_key == metric_key,
                DeviceMetricAlertState.index_key == index_key,
            )
            .one()
        )

    def upsert_alert_state(
        self, device_id: int, metric_key: str, index_key: str, alert_type: str,
        breached, severity, last_value,
    ) -> DeviceMetricAlertState:
        """原子 upsert 一行告警态，返回持久化后的 ORM 对象。

        用 ``INSERT ... ON DUPLICATE KEY UPDATE`` 替代裸 ``session.add``，避免
        ``(device_id, metric_key, index_key)`` 重复时 IntegrityError 污染会话。
        upsert 后从 DB 重新查回该行，确保拿到自增 id 与最新字段值。

        dialect 兼容：MySQL 走原生 ``ON DUPLICATE KEY UPDATE``（生产）；
        SQLite/其他 dialect（单测）走 ``query + add/update`` fallback——单测用
        SQLite 无法编译 MySQL 专属 DML。
        """
        from sqlalchemy.dialects.mysql import insert as mysql_insert

        dialect_name = self.session.get_bind().dialect.name
        if dialect_name == "mysql":
            stmt = mysql_insert(DeviceMetricAlertState).values(
                device_id=device_id,
                metric_key=metric_key,
                index_key=index_key,
                alert_type=alert_type,
                breached=breached,
                severity=severity,
                last_value=last_value,
            )
            stmt = stmt.on_duplicate_key_update(
                breached=stmt.inserted.breached,
                severity=stmt.inserted.severity,
                last_value=stmt.inserted.last_value,
            )
            self.session.execute(stmt)
            self.session.flush()
            return self.require_by_identity(device_id, metric_key, index_key)

        state = self.find_by_identity(device_id, metric_key, index_key)
        if state is None:
            state = DeviceMetricAlertState(
                device_id=device_id,
                metric_key=metric_key,
                index_key=index_key,
                alert_type=alert_type,
            )
            self.session.add(state)
        state.breached = breached
        state.severity = severity
        state.last_value = last_value
        self.session.flush()
        return state

    def delete_by_device(self, device_id: int) -> int:
        """清空该设备的指标告警态行（B-44 收敛：设备彻底删除的清理面）。"""
        return (
            self.session.query(DeviceMetricAlertState)
            .filter_by(device_id=device_id)
            .delete()
        )

    def is_monitor_interrupted(self, device_id: int) -> bool:
        return device_id in self.interrupted_device_ids()

    def interrupted_device_ids(self) -> set:
        """返回当前处于监控中断态的设备 ID 集合（基于 alert_type=monitor_interrupted 且 breached）。"""
        rows = (
            self.session.query(DeviceMetricAlertState.device_id)
            .filter(
                DeviceMetricAlertState.alert_type == "monitor_interrupted",
                DeviceMetricAlertState.breached.is_(True),
            )
            .all()
        )
        return {r[0] for r in rows}
