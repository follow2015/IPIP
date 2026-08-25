# -*- coding: utf-8 -*-
"""
G5: 监控数据导出服务

流式 CSV 生成，避免大文件导出内存峰值（目标 < 100MB）。
支持告警历史导出与设备探测历史导出。
"""
import csv
import io
from app.utils.logging import get_logger
from datetime import datetime
from typing import Any, Iterable, Optional

from app.models.device import Device
from app.models.monitor_alert_outbox import MonitorAlertOutbox
from extensions import db

logger = get_logger(__name__)


ALERT_CSV_HEADERS = [
    "id", "device_id", "device_name", "device_type", "management_ip",
    "alert_type", "severity", "dedup_key", "status", "attempts",
    "last_error", "created_at", "sent_at",
    "acknowledged_by", "acknowledged_at", "ack_note",
]


def _query_alerts(alert_type, severity, status, device_id, start_date, end_date):
    q = (
        db.session.query(
            MonitorAlertOutbox.id,
            MonitorAlertOutbox.device_id,
            Device.device_name,
            Device.device_type,
            Device.management_ip,
            MonitorAlertOutbox.alert_type,
            MonitorAlertOutbox.severity,
            MonitorAlertOutbox.dedup_key,
            MonitorAlertOutbox.status,
            MonitorAlertOutbox.attempts,
            MonitorAlertOutbox.last_error,
            MonitorAlertOutbox.created_at,
            MonitorAlertOutbox.sent_at,
            MonitorAlertOutbox.acknowledged_by,
            MonitorAlertOutbox.acknowledged_at,
            MonitorAlertOutbox.ack_note,
        )
        .select_from(MonitorAlertOutbox)
        .outerjoin(Device, Device.id == MonitorAlertOutbox.device_id)
    )
    if alert_type:
        q = q.filter(MonitorAlertOutbox.alert_type == alert_type)
    if severity:
        q = q.filter(MonitorAlertOutbox.severity == severity)
    if status:
        q = q.filter(MonitorAlertOutbox.status == status)
    if device_id is not None:
        q = q.filter(MonitorAlertOutbox.device_id == device_id)
    if start_date is not None:
        q = q.filter(MonitorAlertOutbox.created_at >= start_date)
    if end_date is not None:
        q = q.filter(MonitorAlertOutbox.created_at <= end_date)
    return q.order_by(
        MonitorAlertOutbox.created_at.desc(),
        MonitorAlertOutbox.id.desc(),
    )


def stream_alerts_csv(alert_type=None, severity=None, status=None,
                      device_id=None, start_date=None, end_date=None,
                      batch_size: int = 1000) -> Iterable[str]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(ALERT_CSV_HEADERS)
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate(0)

    q = _query_alerts(alert_type, severity, status, device_id, start_date, end_date)
    for row in q.yield_per(batch_size):
        writer.writerow([
            row.id,
            row.device_id,
            row.device_name,
            row.device_type,
            row.management_ip,
            row.alert_type,
            row.severity,
            row.dedup_key,
            row.status,
            row.attempts,
            row.last_error,
            row.created_at.isoformat() if row.created_at else "",
            row.sent_at.isoformat() if row.sent_at else "",
            row.acknowledged_by or "",
            row.acknowledged_at.isoformat() if row.acknowledged_at else "",
            row.ack_note or "",
        ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)


def stream_history_csv(device_id: int, start_date=None, end_date=None,
                       batch_size: int = 1000) -> Iterable[str]:
    from app.models.device_monitor_status import DeviceMonitorStatus
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "device_id", "protocol", "reachable", "last_checked_at",
        "latency_ms", "consecutive_failures", "last_error",
        "last_reachable_at", "last_unreachable_at",
    ])
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate(0)

    q = (
        db.session.query(DeviceMonitorStatus)
        .filter(DeviceMonitorStatus.device_id == device_id)
    )
    if start_date is not None:
        q = q.filter(DeviceMonitorStatus.last_checked_at >= start_date)
    if end_date is not None:
        q = q.filter(DeviceMonitorStatus.last_checked_at <= end_date)
    q = q.order_by(DeviceMonitorStatus.last_checked_at.desc())

    for row in q.yield_per(batch_size):
        writer.writerow([
            row.id,
            row.device_id,
            row.protocol,
            int(row.reachable) if row.reachable is not None else "",
            row.last_checked_at.isoformat() if row.last_checked_at else "",
            row.latency_ms if row.latency_ms is not None else "",
            row.consecutive_failures,
            row.last_error or "",
            row.last_reachable_at.isoformat() if row.last_reachable_at else "",
            row.last_unreachable_at.isoformat() if row.last_unreachable_at else "",
        ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
