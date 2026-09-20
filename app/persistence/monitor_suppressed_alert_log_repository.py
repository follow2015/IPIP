# -*- coding: utf-8 -*-
"""被依赖抑制告警留痕仓储

项目 C5 约束：DB 访问必须走 Repository 层，禁止在 Service 内裸写 query。
"""
from typing import Dict, Iterable, Optional

from app.models.monitor_suppressed_alert_log import MonitorSuppressedAlertLog
from extensions import db


def device_names_of(device_ids: Iterable[Optional[int]]) -> Dict[int, str]:
    """批量取设备名（``{id: name}``，一次 IN 查询）。

    供写入留痕时**同时**填充两个快照列用：逐条查会退化成 2N 条查询
    （L2 聚合一次要落 30+ 条留痕），所以这里显式做成批量原型。

    不存在的 ID 不出现在返回值里（调用方据此保持快照为 NULL）。
    """
    from app.models.device import Device

    ids = [i for i in device_ids if i]
    if not ids:
        return {}
    rows = (
        db.session.query(Device.id, Device.device_name)
        .filter(Device.id.in_(set(ids)))
        .all()
    )
    return {r[0]: r[1] for r in rows if r[1]}


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

        写入时**一并落设备名快照**（两个 ID 合成一次查询）。理由：本表的
        ``device_id`` 会在设备彻底删除时被置空，置空后 ``device_name`` 是这行
        唯一的可读标识；若创建时不写，新产出的行在设备删除前一直显示裸 ID、
        删除后才有名字 —— 而"删除前"才是绝大多数时间。
        设备不存在（写入时已删）时快照留 NULL，不编造。
        """
        names = device_names_of([device_id, upstream_device_id])
        row = MonitorSuppressedAlertLog(
            device_id=device_id,
            device_name=names.get(device_id),
            alert_type=alert_type,
            severity=severity,
            reason_code=reason_code,
            upstream_device_id=upstream_device_id,
            upstream_device_name=(
                names.get(upstream_device_id) if upstream_device_id else None
            ),
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
