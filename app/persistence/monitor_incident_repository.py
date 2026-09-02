# -*- coding: utf-8 -*-
"""监控事件仓储

项目 C5 约束：DB 访问必须走 Repository 层，禁止在 Service 内裸写 query。
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, or_

from app.models.monitor_alert_outbox import MonitorAlertOutbox
from app.models.monitor_incident import MonitorIncident
from app.models.monitor_suppressed_alert_log import MonitorSuppressedAlertLog
from extensions import db


class IncidentRepository:
    """事件的读写封装"""

    def __init__(self, session=None):
        self.session = session or db.session

    def create(
        self,
        incident_key: str,
        title: str,
        severity: str,
        root_device_id: Optional[int],
        reason_code: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> MonitorIncident:
        """新建事件（alert_count / device_count 从 1 起算）。

        Args:
            now: 事件首末告警时间（测试注入）；None 取当前 UTC 时间。
        """
        ts = now if now is not None else datetime.now(timezone.utc)
        inc = MonitorIncident(
            incident_key=incident_key,
            title=title,
            severity=severity,
            status="active",
            reason_code=reason_code,
            root_device_id=root_device_id,
            alert_count=1,
            device_count=1,
            first_alert_at=ts,
            last_alert_at=ts,
        )
        self.session.add(inc)
        self.session.flush()
        return inc

    def find_active_by_key(self, incident_key: str) -> Optional[MonitorIncident]:
        """按归并键查活跃事件（status != closed）。

        只返回活跃事件：已关闭的事件不应再被新告警命中，否则一起新故障
        会被错误地归到历史事故上。
        """
        return (
            self.session.query(MonitorIncident)
            .filter(
                MonitorIncident.incident_key == incident_key,
                MonitorIncident.status != "closed",
            )
            .order_by(MonitorIncident.id.desc())
            .first()
        )

    def get(self, incident_id: int) -> Optional[MonitorIncident]:
        return self.session.get(MonitorIncident, incident_id)

    def touch(self, incident_id: int, device_id: Optional[int] = None,
              now: Optional[datetime] = None) -> None:
        """事件被新告警命中：累加计数并刷新 last_alert_at。

        Args:
            incident_id: 事件 ID。
            device_id: 本次告警的设备（用于刷新影响设备数）。
            now: 本次告警时间（测试注入）；None 取当前 UTC 时间。
        """
        inc = self.get(incident_id)
        if inc is None:
            return
        inc.alert_count = (inc.alert_count or 0) + 1
        inc.last_alert_at = now if now is not None else datetime.now(timezone.utc)
        self.session.flush()
        if device_id is not None:
            self.refresh_device_count(incident_id)

    def refresh_device_count(self, incident_id: int) -> int:
        """重算并写回影响设备数。

        影响面 = 根因设备 ∪ 入箱告警涉及的设备 ∪ 被抑制留痕涉及的设备（去重）。

        - 仅靠入箱告警会严重低估影响：一次上游宕机下游 30 台的告警全部
          被依赖抑制、根本没入箱。
        - 必须显式并入 root_device_id：告警入箱与事件关联存在先后顺序，
          刚创建事件时 outbox 行尚未回填 incident_id，若不包含根因设备
          会短暂出现 device_count=0。

        Returns:
            重算后的设备数。
        """
        inc = self.get(incident_id)
        if inc is None:
            return 0

        outbox_q = (
            self.session.query(MonitorAlertOutbox.device_id)
            .filter(
                MonitorAlertOutbox.incident_id == incident_id,
                MonitorAlertOutbox.device_id.isnot(None),
            )
            .distinct()
        )
        log_q = (
            self.session.query(MonitorSuppressedAlertLog.device_id)
            .filter(
                MonitorSuppressedAlertLog.incident_id == incident_id,
                MonitorSuppressedAlertLog.device_id.isnot(None),
            )
            .distinct()
        )
        query = outbox_q.union(log_q)
        count = query.count()
        if inc.root_device_id is not None:
            present = (
                self.session.query(MonitorAlertOutbox.device_id)
                .filter(
                    MonitorAlertOutbox.incident_id == incident_id,
                    MonitorAlertOutbox.device_id == inc.root_device_id,
                )
                .first()
            ) is not None or (
                self.session.query(MonitorSuppressedAlertLog.device_id)
                .filter(
                    MonitorSuppressedAlertLog.incident_id == incident_id,
                    MonitorSuppressedAlertLog.device_id == inc.root_device_id,
                )
                .first()
            ) is not None
            if not present:
                count += 1
        inc.device_count = count
        self.session.flush()
        return count

    def close(self, incident_id: int) -> None:
        """关闭事件（不再被新告警命中）。"""
        inc = self.get(incident_id)
        if inc is None:
            return
        inc.status = "closed"
        inc.closed_at = datetime.now(timezone.utc)
        self.session.flush()

    def list_active(self, limit: int = 50, offset: int = 0) -> list:
        """列出活跃事件，按末次告警时间倒序。"""
        return (
            self.session.query(MonitorIncident)
            .filter(MonitorIncident.status != "closed")
            .order_by(MonitorIncident.last_alert_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def list_by_status(self, status: str, limit: int = 50, offset: int = 0) -> list:
        """按状态列事件（支持显式查 closed）。"""
        return (
            self.session.query(MonitorIncident)
            .filter(MonitorIncident.status == status)
            .order_by(MonitorIncident.last_alert_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count_active(self) -> int:
        """活跃事件总数（用于分页 total）。"""
        return (
            self.session.query(MonitorIncident)
            .filter(MonitorIncident.status != "closed")
            .count()
        )

    def count_by_status(self, status: str) -> int:
        """指定状态事件总数（用于分页 total）。"""
        return (
            self.session.query(MonitorIncident)
            .filter(MonitorIncident.status == status)
            .count()
        )

    def list_alerts_by_incident(self, incident_id: int, limit: int = 200) -> list:
        """事件关联的入箱告警（按时间倒序，最多 limit 条）。

        Service/Route 层禁止裸查 outbox，统一走此方法。
        """
        return (
            self.session.query(MonitorAlertOutbox)
            .filter(MonitorAlertOutbox.incident_id == incident_id)
            .order_by(MonitorAlertOutbox.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_suppressed_by_incident(self, incident_id: int, limit: int = 200) -> list:
        """事件关联的被抑制下游设备留痕（按时间倒序，最多 limit 条）。"""
        return (
            self.session.query(MonitorSuppressedAlertLog)
            .filter(MonitorSuppressedAlertLog.incident_id == incident_id)
            .order_by(MonitorSuppressedAlertLog.created_at.desc())
            .limit(limit)
            .all()
        )
