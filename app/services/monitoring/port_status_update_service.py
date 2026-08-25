# -*- coding: utf-8 -*-
"""端口状态更新服务（PortStatusUpdateService）— 公用核心

抽取端口状态更新的公用逻辑，供三个流程复用：
1. SSH 全量替换（incremental_update 内部调用）
2. 非网管设备端口同步（PortSyncService 四元组匹配替换）
3. 网管设备仅状态更新（ManagedPortStatusSyncService 按 port_name 匹配 + 不匹配告警）

核心职责：
- 更新 NetworkPort.link_status
- 联动 usage_status（通过 NetworkPort.derive_usage_status）
- 更新 last_collected_at
- 可选：端口状态变化时产生 port_status_changed 告警
- 可选：端口名不匹配时产生 port_name_mismatch 告警

连接状态联动：NetworkConnection.to_dict() 实时计算 derived_status，
端口 link_status 更新后连接状态自动正确，无需额外写库。

设计要点：
- 不直接 commit，由调用方统一事务边界
- 告警通过 MetricAlertService._enqueue 入箱，与现有告警体系一致
- 状态变化检测：对比新旧 link_status，仅变化时告警（避免每轮重复告警）
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.models.network_port import NetworkPort

logger = logging.getLogger(__name__)


class PortStatusUpdateService:
    """公用端口状态更新服务。

    提供原子级端口状态更新操作，供 SSH / 非网管同步 / 网管状态更新复用。
    """

    def __init__(self, session=None):
        from extensions import db
        self._session = session or db.session

    def update_port_status(
        self,
        port: NetworkPort,
        link_status: str | None,
        now: datetime | None = None,
        emit_alert: bool = False,
        device_id: int | None = None,
    ) -> bool:
        """更新单个端口的 link_status + 联动 usage_status。

        Args:
            port: NetworkPort ORM 对象
            link_status: 新的链路状态（up/down/admin_down/...）
            now: 时间戳，缺省 datetime.now()
            emit_alert: 是否在状态变化时产生 port_status_changed 告警
            device_id: 设备 ID（emit_alert=True 时必填）

        Returns:
            bool: 状态是否发生变化（True=变化，False=未变）
        """
        if now is None:
            now = datetime.now()

        old_link_status = port.link_status
        if old_link_status == link_status:
            port.last_collected_at = now
            return False

        port.link_status = link_status
        port.usage_status = NetworkPort.derive_usage_status(link_status, port.port_name)
        port.last_collected_at = now

        if emit_alert and device_id is not None:
            is_key_port = (port.usage_status or "").lower() in ("occupied", "in_use", "uplink", "core")
            if is_key_port:
                self._emit_status_change_alert(
                    device_id, port.port_name, old_link_status, link_status,
                )

        return True

    def batch_update_status(
        self,
        device_id: int,
        port_status_map: dict[str, str | None],
        now: datetime | None = None,
        emit_alert: bool = False,
    ) -> dict:
        """批量更新端口状态（按 port_name 匹配）。

        Args:
            device_id: 设备 ID
            port_status_map: {port_name: link_status}
            now: 时间戳
            emit_alert: 是否产生状态变化告警

        Returns:
            dict: {"updated": int, "unchanged": int, "not_found": list[str]}
        """
        if now is None:
            now = datetime.now()

        existing_ports = (
            self._session.query(NetworkPort)
            .filter(NetworkPort.device_id == device_id)
            .all()
        )
        existing_by_name = {p.port_name: p for p in existing_ports}

        updated = 0
        unchanged = 0
        not_found: list[str] = []

        for port_name, link_status in port_status_map.items():
            port = existing_by_name.get(port_name)
            if port is None:
                not_found.append(port_name)
                continue
            changed = self.update_port_status(
                port, link_status, now=now,
                emit_alert=emit_alert, device_id=device_id,
            )
            if changed:
                updated += 1
            else:
                unchanged += 1

        return {"updated": updated, "unchanged": unchanged, "not_found": not_found}

    def _emit_status_change_alert(
        self,
        device_id: int,
        port_name: str,
        old_status: str | None,
        new_status: str | None,
    ) -> None:
        """端口状态变化告警（port_status_changed）。

        复用 MetricAlertService._enqueue 入箱，与现有告警体系一致。
        同时更新 device_metric_alert_state，使前端告警明细能查到。
        """
        try:
            from app.services.monitoring.metric_alert_service import MetricAlertService
            from app.models.device_metric_alert_state import DeviceMetricAlertState
            svc = MetricAlertService(session=self._session)
            index = port_name
            value = f"{old_status}->{new_status}"
            breached = (new_status or "").lower() not in ("up", "")
            severity = "warn" if breached else "info"
            svc._enqueue(
                device_id, "port_status_changed", severity,
                "port_updown", index, value, breached=breached,
            )
            state = (
                self._session.query(DeviceMetricAlertState)
                .filter_by(
                    device_id=device_id,
                    metric_key="port_updown",
                    index_key=index,
                )
                .first()
            )
            if state is None:
                state = DeviceMetricAlertState(
                    device_id=device_id,
                    metric_key="port_updown",
                    index_key=index,
                    alert_type="port_status_changed",
                )
                self._session.add(state)
            state.breached = breached
            state.severity = severity
            state.last_value = value
            self._session.flush()
        except Exception:  # noqa: BLE001 - 告警失败不阻断状态更新
            logger.warning(
                "端口状态变化告警入箱失败 device_id=%s port=%s",
                device_id, port_name, exc_info=True,
            )

    def emit_port_name_mismatch_alert(
        self,
        device_id: int,
        port_names: list[str],
    ) -> None:
        """端口名不匹配告警（port_name_mismatch）。

        网管设备监控轮询采集到端口，但 DB 中无匹配 port_name 时调用。
        每个不匹配端口产生一条告警，提示用户端口命名不一致。
        """
        if not port_names:
            return
        try:
            from app.services.monitoring.metric_alert_service import MetricAlertService
            svc = MetricAlertService(session=self._session)
            for port_name in port_names:
                svc._enqueue(
                    device_id, "port_status_changed", "warn",
                    "port_updown", f"端口名不匹配: {port_name}",
                    f"采集到端口 {port_name} 但 DB 中无匹配记录",
                    breached=True,
                )
        except Exception:  # noqa: BLE001 - 告警失败不阻断
            logger.warning(
                "端口名不匹配告警入箱失败 device_id=%s ports=%s",
                device_id, port_names, exc_info=True,
            )
