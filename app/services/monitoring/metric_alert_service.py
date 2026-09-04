# -*- coding: utf-8 -*-
"""指标告警服务（MetricAlertService）

把 MetricCollector 的采集+判定结果，转成「按指标维度」的告警入箱（outbox）：

- breached=True 且此前非告警态 → 入箱告警，更新告警态；
- breached=False 且此前为告警态 → 入箱恢复通知，清除告警态；
- 状态不变（持续告警 / 持续正常）→ 不重复入箱（去重）。

复用现有 outbox 机制（MonitorAlertOutbox + MonitorOutboxSender）：本服务只负责
写入待发行（与告警态更新同一事务），投递由独立轮询器完成。

metric_key → alert_type 映射：
- temperature   → temperature_alert
- disk_failure  → disk_failure_alert
- port_updown   → port_status_changed
- raid_failure  → raid_failure_alert
- monitor_interrupted → monitor_interrupted
"""
import json

from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.core.enums import NotificationTypeCode
from app.models.device_metric_alert_state import DeviceMetricAlertState
from app.utils.logging import get_logger

logger = get_logger(__name__)

_METRIC_TO_ALERT_TYPE = {
    "temperature": NotificationTypeCode.TEMPERATURE_ALERT.value,
    "disk_failure": NotificationTypeCode.DISK_FAILURE_ALERT.value,
    "port_updown": NotificationTypeCode.PORT_STATUS_CHANGED.value,
    "raid_failure": NotificationTypeCode.RAID_FAILURE_ALERT.value,
    "monitor_interrupted": NotificationTypeCode.MONITOR_INTERRUPTED.value,
}


class MetricAlertService:
    """指标告警服务（按指标维度去重与恢复）"""

    def __init__(self, session=None):
        from extensions import db
        self._session = session or db.session

    def process(self, device_id: int, collector_result: dict) -> dict:
        """处理一轮采集结果，入箱状态变化的告警/恢复，返回入箱明细。

        ``collector_result`` 结构::

            {metric_key: {index: {"severity", "breached", "value"}}}

        返回::

            {"alerted": int, "recovered": int, "skipped": int}

        性能（P1-1 修复）：一次性批量预取该设备全部 alert state 到内存 dict，
        替代原先对每个 (device_id, metric_key, index) 单独一次 DB 查询（N+1），
        将 N×M 次查询降为 1 次。
        """
        states = (
            self._session.query(DeviceMetricAlertState)
            .filter(DeviceMetricAlertState.device_id == device_id)
            .all()
        )
        state_map: dict = {}
        for s in states:
            state_map[(s.metric_key, s.index_key)] = s

        alerted = recovered = skipped = 0
        try:
            for metric_key, instances in (collector_result or {}).items():
                alert_type = _METRIC_TO_ALERT_TYPE.get(metric_key)
                if alert_type is None:
                    continue
                for index, info in (instances or {}).items():
                    breached = bool(info.get("breached"))
                    action = self._apply_one(
                        device_id, metric_key, str(index), alert_type,
                        info, breached, state_map,
                    )
                    if action == "alert":
                        alerted += 1
                    elif action == "recover":
                        recovered += 1
                    else:
                        skipped += 1
        except Exception:
            self._session.rollback()
            raise
        return {"alerted": alerted, "recovered": recovered, "skipped": skipped}


    def _apply_one(self, device_id, metric_key, index, alert_type, info, breached,
                   state_map: dict) -> str:
        """处理单个指标实例，返回 "alert" / "recover" / "skip"。

        ``state_map`` 由 ``process`` 批量预取，键为 ``(metric_key, index)``。

        P0 修复：原实现用裸 ``session.add`` + ``flush`` 写新告警态行，当上一轮事务
        残留 / 跨事务并发导致 ``(device_id, metric_key, index_key)`` 已存在时，INSERT
        违反 ``uq_dmas_device_metric_index`` 唯一约束，flush 抛 IntegrityError 使会话
        进入 rollback-pending 态，后续所有操作级联抛 PendingRollbackError。改用
        MySQL ``INSERT ... ON DUPLICATE KEY UPDATE`` 原子 upsert，从根本上消除重复
        键冲突。
        """
        state = state_map.get((metric_key, index))

        if breached and (state is None or not state.breached):
            if state is None:
                state = self._upsert_alert_state(
                    device_id, metric_key, index, alert_type,
                    breached=True,
                    severity=info.get("severity", "warn"),
                    last_value=str(info.get("value", "")),
                )
                state_map[(metric_key, index)] = state
            else:
                state.breached = True
                state.severity = info.get("severity", "warn")
                state.last_value = str(info.get("value", ""))
                self._session.flush()
            self._enqueue(device_id, alert_type, state.severity, metric_key, index,
                          info.get("value"), breached=True)
            return "alert"

        if not breached and state is not None and state.breached:
            state.breached = False
            state.severity = "ok"
            state.last_value = str(info.get("value", ""))
            self._session.flush()
            self._enqueue(device_id, alert_type, "info", metric_key, index,
                          info.get("value"), breached=False)
            return "recover"

        return "skip"

    def _upsert_alert_state(self, device_id, metric_key, index, alert_type,
                            breached, severity, last_value) -> DeviceMetricAlertState:
        """原子 upsert 一行告警态，返回持久化后的 ORM 对象。

        用 ``INSERT ... ON DUPLICATE KEY UPDATE`` 替代裸 ``session.add``，避免
        ``(device_id, metric_key, index_key)`` 重复时 IntegrityError 污染会话。
        upsert 后从 DB 重新查回该行，确保拿到自增 id 与最新字段值。

        dialect 兼容：MySQL 走原生 ``ON DUPLICATE KEY UPDATE``（生产）；
        SQLite/其他 dialect（单测）走 ``query + add/update`` fallback——单测用
        SQLite 无法编译 MySQL 专属 DML。
        """
        dialect_name = self._session.get_bind().dialect.name
        if dialect_name == "mysql":
            stmt = mysql_insert(DeviceMetricAlertState).values(
                device_id=device_id,
                metric_key=metric_key,
                index_key=index,
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
            self._session.execute(stmt)
            self._session.flush()
            return (
                self._session.query(DeviceMetricAlertState)
                .filter(
                    DeviceMetricAlertState.device_id == device_id,
                    DeviceMetricAlertState.metric_key == metric_key,
                    DeviceMetricAlertState.index_key == index,
                )
                .one()
            )

        state = (
            self._session.query(DeviceMetricAlertState)
            .filter(
                DeviceMetricAlertState.device_id == device_id,
                DeviceMetricAlertState.metric_key == metric_key,
                DeviceMetricAlertState.index_key == index,
            )
            .one_or_none()
        )
        if state is None:
            state = DeviceMetricAlertState(
                device_id=device_id,
                metric_key=metric_key,
                index_key=index,
                alert_type=alert_type,
            )
            self._session.add(state)
        state.breached = breached
        state.severity = severity
        state.last_value = last_value
        self._session.flush()
        return state

    def _enqueue(self, device_id, alert_type, severity, metric_key, index, value, breached):
        """写一条待发告警/恢复行到 outbox（与告警态更新同一事务）。

        P1-2：接入统一治理门面（AlertIngress），使指标告警与连通性告警获得一致的
        静默（G4.1）/风暴抑制（G13）/SSE 权限发布（G1），不再裸入箱。
        """
        from app.models.monitor_alert_outbox import MonitorAlertOutbox
        from app.services.monitoring.alert_ingress import build_dedup_key

        action = "raise" if breached else "recover"
        idem_key = build_dedup_key(alert_type, device_id, metric_key, index, action)
        payload = {
            "type": alert_type,
            "severity": severity,
            "title": self._title(alert_type, index, value, breached),
            "content": self._content(alert_type, index, value, breached),
            "payload": {"device_id": device_id, "metric_key": metric_key, "index": index,
                        "value": value, "breached": breached},
            "source_module": "monitor_metrics",
            "target_type": "device",
            "target_id": device_id,
            "idempotency_key": idem_key,
            "allow_broadcast": True,
        }

        from app.services.monitoring.alert_ingress import governance_should_emit
        should_emit, aggregated, suppressed_count = governance_should_emit(
            device_id, alert_type, idem_key, severity=severity,
        )
        if not should_emit:
            return
        if aggregated:
            payload = dict(payload)
            payload["suppressed_count"] = suppressed_count

        new_row = MonitorAlertOutbox(
            device_id=device_id,
            alert_type=alert_type,
            severity=severity,
            dedup_key=idem_key,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
        self._session.add(new_row)

        from app.services.monitoring.alert_ingress import publish_monitor_alert_event
        try:
            self._session.flush()
            publish_monitor_alert_event(
                device_id, alert_type, severity, idem_key,
                new_row.id, payload,
            )
        except Exception:
            logger.warning("metric_alert SSE 发布失败 device_id=%s alert_type=%s", device_id, alert_type, exc_info=True)

        try:
            from app.services.monitoring.incident_aggregator import aggregate_alert
            aggregate_alert(device_id, alert_type, severity, outbox_id=new_row.id)
        except Exception:
            logger.warning("metric_alert 事件聚合失败 device_id=%s", device_id, exc_info=True)


    @staticmethod
    def _title(alert_type, index, value, breached) -> str:
        action = "已告警" if breached else "已恢复"
        if alert_type == "temperature_alert":
            return f"温度{action}：{index} = {value}°C"
        if alert_type in ("disk_failure_alert", "raid_failure_alert"):
            return f"{'RAID故障' if alert_type == 'raid_failure_alert' else '硬盘故障'}{action}：{index}"
        if alert_type == "port_status_changed":
            return f"端口状态{action}：{index}"
        if alert_type == "monitor_interrupted":
            return f"监控中断{action}：{index}"
        return f"指标{action}：{index} = {value}"

    @staticmethod
    def _content(alert_type, index, value, breached) -> str:
        state = "异常" if breached else "恢复"
        return f"[{alert_type}] 指标实例 {index} 当前{state}，值={value}"
