# -*- coding: utf-8 -*-
"""Incident 上下文采集（AI 诊断 × 告警集成 ② 的公共实现）。


同样的上下文有两处消费方：

1. `diag.timeline` capability —— 让 agentic 诊断 Round 1 直接拿到结构化事实；
2. escalation 自动触发诊断（`incident_diagnosis_trigger.py`）—— 构造诊断问题时
   需要事件的严重级别 / 影响面 / 归因线索。

放在 capability 内部会让触发器反向依赖能力层（层次倒置），故下沉为服务层模块。


- **L1 / L2 已物化**：`monitor_incident` 的 `reason_code`、`alert_count`、
  `device_count` 由 incident_aggregator 落库，直接读即可。
- **L3 只落了标志**：`reason_code=L3_change` 只说明"关联到变更"，变更的
  who/what/when **不在 incident 行里**，必须回查审计表复算
  （`incident_aggregator.find_recent_change`）。
  复算基准时间用**事件首告警时间**而非当前时间——要找的是"故障发生前的变更"，
  用 now 会把故障之后人为排查造成的变更也算进来。
- **L2 被抑制的下游告警**：在 `monitor_suppressed_alert_log`，按 incident_id 反查。
  它揭示了"谁被上游故障连坐"，是判断影响面最直接的证据。


`visible` 为设备 id 集合时，被抑制告警按该集合裁剪——这些行含上下游设备 id
与健康状态，属于数据域外设备时不该出现在 AI 视野里。visible=None 表示无限制
（超管/全量），不做裁剪。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

MAX_INCIDENTS = 10
MAX_SUPPRESSED = 20
L3_WINDOW_SECONDS = 300


def _l3_change(root_device_id: Optional[int], at) -> Optional[Dict[str, Any]]:
    """复算 L3 变更明细。旁路：审计表异常只记日志，不阻断整体上下文。"""
    if not root_device_id or at is None:
        return None
    try:
        from app.services.monitoring.incident_aggregator import find_recent_change

        change = find_recent_change(
            int(root_device_id), within_seconds=L3_WINDOW_SECONDS, now=at,
        )
    except Exception:  # noqa: BLE001 - 旁路，上下文缺失不应让诊断失败
        logger.warning("ai.incident_ctx.l3_failed device=%s", root_device_id,
                       exc_info=True)
        return None
    if not change:
        return None
    return {
        "at": change["at"].isoformat() if change.get("at") else None,
        "actor": change.get("actor"),
        "action": change.get("action"),
    }


def _suppressed(incident_id: int, visible: Optional[set]) -> List[Dict[str, Any]]:
    """取该事件下被依赖抑制的告警（L2 连坐面）。"""
    from app.models.monitor_suppressed_alert_log import MonitorSuppressedAlertLog
    from extensions import db

    q = (
        db.session.query(MonitorSuppressedAlertLog)
        .filter(MonitorSuppressedAlertLog.incident_id == incident_id)
        .order_by(MonitorSuppressedAlertLog.created_at.desc())
        .limit(MAX_SUPPRESSED)
        .all()
    )
    out: List[Dict[str, Any]] = []
    for row in q:
        if visible is not None:
            if row.device_id not in visible and row.upstream_device_id not in visible:
                continue
        out.append({
            "device_id": row.device_id,
            "alert_type": row.alert_type,
            "severity": row.severity,
            "reason_code": row.reason_code,
            "upstream_device_id": row.upstream_device_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return out


def _diagnosis_state(incident_id: int) -> Dict[str, Any]:
    """该事件是否已有诊断会话（供 Round 1 直接复用，避免重复诊断）。"""
    from app.models.ai_diagnosis_session import AIDiagnosisSession
    from extensions import db

    try:
        running = (
            db.session.query(AIDiagnosisSession.id)
            .filter(AIDiagnosisSession.incident_id == incident_id,
                    AIDiagnosisSession.status == "running")
            .count()
        )
        latest = (
            db.session.query(AIDiagnosisSession)
            .filter(AIDiagnosisSession.incident_id == incident_id,
                    AIDiagnosisSession.status.in_(("completed", "incomplete")))
            .order_by(AIDiagnosisSession.id.desc())
            .first()
        )
    except Exception:  # noqa: BLE001 - 迁移未执行时该列不存在，降级为无诊断记录
        logger.warning("ai.incident_ctx.diagnosis_lookup_failed incident=%s",
                       incident_id, exc_info=True)
        return {"running": 0, "latest_session_id": None, "latest_summary": None}

    summary = None
    if latest is not None and latest.final_answer_json:
        try:
            import json

            parsed = json.loads(latest.final_answer_json)
            if isinstance(parsed, dict):
                summary = parsed.get("diagnosis") or parsed.get("summary")
        except Exception:  # noqa: BLE001
            summary = None
    return {
        "running": running,
        "latest_session_id": latest.id if latest else None,
        "latest_summary": summary,
    }


def collect_incident_contexts(
    device_id: int,
    since,
    visible: Optional[set] = None,
    limit: int = MAX_INCIDENTS,
) -> List[Dict[str, Any]]:
    """采集某设备近期事件的完整上下文。

    Args:
        device_id: 根因设备 ID（`monitor_incident.root_device_id`）。
        since: 起始时间（naive UTC），按 `first_alert_at` 过滤。
        visible: 可见设备 id 集合；None 表示无限制。
        limit: 最多返回事件数。

    Returns:
        每项含 incident 本体字段 + suppressed（L2 连坐）+ change（L3 复算）
        + diagnosis（已有诊断状态）。
    """
    from app.models.monitor_incident import MonitorIncident
    from extensions import db

    incidents = (
        db.session.query(MonitorIncident)
        .filter(MonitorIncident.root_device_id == device_id,
                MonitorIncident.first_alert_at >= since)
        .order_by(MonitorIncident.first_alert_at.desc())
        .limit(limit)
        .all()
    )

    out: List[Dict[str, Any]] = []
    for inc in incidents:
        out.append({
            "incident_id": inc.id,
            "incident_key": inc.incident_key,
            "title": inc.title,
            "severity": inc.severity,
            "status": inc.status,
            "reason_code": inc.reason_code,
            "alert_count": inc.alert_count,
            "device_count": inc.device_count,
            "root_device_id": inc.root_device_id,
            "first_alert_at": inc.first_alert_at.isoformat() if inc.first_alert_at else None,
            "last_alert_at": inc.last_alert_at.isoformat() if inc.last_alert_at else None,
            "suppressed": _suppressed(inc.id, visible),
            "change": _l3_change(inc.root_device_id, inc.first_alert_at),
            "diagnosis": _diagnosis_state(inc.id),
        })
    return out
