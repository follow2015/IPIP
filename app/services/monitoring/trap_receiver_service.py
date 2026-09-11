# -*- coding: utf-8 -*-
"""
SNMP Trap 接收 → 统一告警链路（P1-1）

把 trapd 服务收到的原始 trap 加工成与指标告警**同构**的告警行：
设备关联（源 IP → Device）→ 规则匹配 → 限流 → 统一治理门面（静默 G4.1 +
风暴抑制 G13，其 300s 节流窗口即 DoD 的「同一事件 5 分钟只认一次」）→
outbox 入箱 → SSE 发布 → 事件聚合。

**告警链路零旁路**：不新建通知通道、不另起日志表，全部复用既有
MonitorAlertOutbox / alert_ingress / incident_aggregator（与 MetricAlertService
._enqueue 同一模式），trapd 只是第 N 个告警生产者。

**fail-open 语义**：Redis 故障时治理门面自身放行（既有设计）；未知 trap 与
未知源 IP 不产生告警，只落结构化 WARNING 日志（供补规则/补设备档案）。
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Optional

from app.utils.logging import get_logger
from app.services.monitoring.trap_rule_service import TrapRuleMatcher

logger = get_logger(__name__)

TRAP_ALERT_TYPE = "trap"  # outbox.alert_type（String(40)）


class TrapRateLimiter:
    """进程内滑动窗口限流（trap 风暴第一道闸，保护 DB 与告警链路）。

    窗口内超过上限直接拒收（拒收的 trap 有日志，不影响后续窗口）。
    与治理门面的按 dedup_key 抑制互补：这里按**全局速率**，那里按**事件**。
    """

    def __init__(self, max_per_minute: int, window_seconds: float = 60.0):
        self._max = max(1, int(max_per_minute))
        self._window = window_seconds
        self._events: deque[float] = deque()
        self._lock = threading.Lock()

    def allow(self, now: Optional[float] = None) -> bool:
        ts = now if now is not None else time.monotonic()
        with self._lock:
            events = self._events
            while events and ts - events[0] >= self._window:
                events.popleft()
            if len(events) >= self._max:
                return False
            events.append(ts)
            return True


class TrapIngressService:
    """Trap 处理入口（纯加工，不含 UDP 传输层，便于单测与复用）。"""

    def __init__(self, matcher: Optional[TrapRuleMatcher] = None,
                 rate_limiter: Optional[TrapRateLimiter] = None):
        self._matcher = matcher or TrapRuleMatcher()
        self._limiter = rate_limiter


    @staticmethod
    def resolve_device(source_ip: str):
        """源 IP → Device（软删除除外）。复用 management_ip 同步口径。"""
        from app.models.device import Device

        return (
            Device.query.filter(
                Device.management_ip == source_ip,
                Device.deleted_at.is_(None),
            ).first()
        )


    def handle_trap(
        self,
        source_ip: str,
        snmp_version: str,
        community: str,
        trap_oid: str,
        varbinds: Optional[list[tuple[str, Any]]] = None,
        received_at: Optional[float] = None,
    ) -> dict[str, Any]:
        """处理一条已解码的 trap，返回处理结论（供日志与服务统计）。

        Returns:
            dict: {"action": "alerted"|"suppressed"|"unknown_trap"|"unknown_source"
                        |"rate_limited"|"error",
                   "alert_id"?: int, "dedup_key"?: str, "reason": str}
        """
        varbinds = varbinds or []

        rule = self._matcher.match(trap_oid)
        if rule is None:
            logger.warning(
                "[trapd] 未知 trap（不产生告警，请据此补规则）: source=%s version=%s "
                "oid=%s varbinds=%s",
                source_ip, snmp_version, trap_oid,
                [(str(o), str(v)) for o, v in varbinds],
            )
            return {"action": "unknown_trap", "reason": f"未匹配规则的 OID {trap_oid}"}

        device = self.resolve_device(source_ip)
        if device is None:
            logger.warning(
                "[trapd] 来源 IP 未关联到设备（不产生告警）: source=%s oid=%s rule=%s",
                source_ip, trap_oid, rule["name"],
            )
            return {"action": "unknown_source", "reason": f"IP {source_ip} 无对应设备"}

        if self._limiter is not None and not self._limiter.allow():
            logger.warning(
                "[trapd] 触发全局限流，trap 被拒收: source=%s rule=%s oid=%s",
                source_ip, rule["name"], trap_oid,
            )
            return {"action": "rate_limited", "reason": "超过全局 trap 速率上限"}

        return self._raise_alert(device, rule, source_ip, snmp_version, varbinds)


    def _raise_alert(self, device, rule: dict[str, Any], source_ip: str,
                     snmp_version: str, varbinds: list[tuple[str, Any]]) -> dict[str, Any]:
        import json as _json

        from app.models.monitor_alert_outbox import MonitorAlertOutbox
        from app.services.monitoring.alert_ingress import (
            build_dedup_key,
            governance_should_emit,
            publish_monitor_alert_event,
        )

        device_id = device.id
        index = self._matcher.extract_index(rule, varbinds)
        idem_key = build_dedup_key(TRAP_ALERT_TYPE, device_id, rule["name"], index, "raise")

        title = rule.get("title") or rule["name"]
        content = rule.get("content") or ""
        if index:
            content = f"{content}\n实例: {index}" if content else f"实例: {index}"
        payload = {
            "type": TRAP_ALERT_TYPE,
            "severity": rule["severity"],
            "title": title,
            "content": content,
            "payload": {
                "device_id": device_id,
                "device_name": getattr(device, "name", None),
                "trap_rule": rule["name"],
                "trap_oid": rule["match_oid"],
                "index": index,
                "source_ip": source_ip,
                "snmp_version": snmp_version,
                "varbinds": [(str(o), str(v)) for o, v in varbinds][:20],  # 防超长
            },
            "source_module": "trapd",
            "target_type": "device",
            "target_id": device_id,
            "idempotency_key": idem_key,
            "allow_broadcast": True,
        }

        should_emit, aggregated, suppressed_count = governance_should_emit(
            device_id, TRAP_ALERT_TYPE, idem_key, severity=rule["severity"],
        )
        if not should_emit:
            logger.info(
                "[trapd] 告警被治理门面抑制: device=%s rule=%s key=%s",
                device_id, rule["name"], idem_key,
            )
            return {"action": "suppressed", "dedup_key": idem_key,
                    "reason": "被静默/抑制窗口拦截"}
        if aggregated:
            payload = dict(payload)
            payload["suppressed_count"] = suppressed_count

        new_row = MonitorAlertOutbox(
            device_id=device_id,
            alert_type=TRAP_ALERT_TYPE,
            severity=rule["severity"],
            dedup_key=idem_key,
            payload_json=_json.dumps(payload, ensure_ascii=False),
        )
        from extensions import db
        db.session.add(new_row)
        db.session.flush()

        try:
            publish_monitor_alert_event(
                device_id, TRAP_ALERT_TYPE, rule["severity"], idem_key,
                new_row.id, payload,
            )
        except Exception:
            logger.warning("[trapd] SSE 发布失败 device_id=%s rule=%s",
                           device_id, rule["name"], exc_info=True)

        try:
            from app.services.monitoring.incident_aggregator import aggregate_alert
            aggregate_alert(device_id, TRAP_ALERT_TYPE, rule["severity"],
                            outbox_id=new_row.id)
        except Exception:
            logger.warning("[trapd] 事件聚合失败 device_id=%s", device_id, exc_info=True)

        alert_id = new_row.id
        db.session.commit()
        logger.info(
            "[trapd] 告警入箱: alert_id=%s device=%s(%s) rule=%s index=%s key=%s",
            alert_id, getattr(device, "name", None), source_ip, rule["name"],
            index, idem_key,
        )
        return {"action": "alerted", "alert_id": alert_id, "dedup_key": idem_key}
