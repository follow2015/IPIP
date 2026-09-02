# -*- coding: utf-8 -*-
"""被依赖抑制告警留痕仓储

项目 C5 约束：DB 访问必须走 Repository 层，禁止在 Service 内裸写 query。
"""
from typing import Optional

from app.models.monitor_suppressed_alert_log import MonitorSuppressedAlertLog
from extensions import db


class SuppressedAlertLogRepository:
    """留痕表的读写封装"""

    def __init__(self, session=None):
        self.session = session or db.session

    def add(
        self,
        device_id: int,
        alert_type: str,
        severity: str,
        reason_code: str,
        upstream_device_id: Optional[int] = None,
        incident_id: Optional[int] = None,
    ) -> MonitorSuppressedAlertLog:
        """写入一条留痕。

        Args:
            device_id: 被抑制告警的设备 ID。
            alert_type: 告警类型。
            severity: 严重级别。
            reason_code: L2_manual_rule / L2_topology。
            upstream_device_id: 命中的上游设备 ID（根因侧）。
            incident_id: 已归属事件时直接写入，否则留待 L2 聚合回填。
        """
        row = MonitorSuppressedAlertLog(
            device_id=device_id,
            alert_type=alert_type,
            severity=severity,
            reason_code=reason_code,
            upstream_device_id=upstream_device_id,
            incident_id=incident_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def attach_to_incident(
        self,
        upstream_device_id: int,
        alert_type: str,
        incident_id: int,
    ) -> int:
        """把尚未归属的留痕行批量归属到指定事件。

        只回填 incident_id IS NULL 的行，避免重复聚合时把已归属的行改绑
        —— 尤其在多起事件时间重叠时，改绑会造成影响面统计错乱。

        Returns:
            更新的行数。
        """
        return (
            self.session.query(MonitorSuppressedAlertLog)
            .filter(
                MonitorSuppressedAlertLog.upstream_device_id == upstream_device_id,
                MonitorSuppressedAlertLog.alert_type == alert_type,
                MonitorSuppressedAlertLog.incident_id.is_(None),
            )
            .update(
                {MonitorSuppressedAlertLog.incident_id: incident_id},
                synchronize_session=False,
            )
        )

    def count_distinct_devices(self, incident_id: int) -> int:
        """统计某事件的影响设备数（按 device_id 去重）。

        同一台设备在窗口内可能产生多条留痕，去重后才是有意义的「影响面」。
        """
        return (
            self.session.query(MonitorSuppressedAlertLog.device_id)
            .filter(MonitorSuppressedAlertLog.incident_id == incident_id)
            .distinct()
            .count()
        )
