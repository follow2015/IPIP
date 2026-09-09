# -*- coding: utf-8 -*-
"""Incident 级 AI 诊断触发器（AI 诊断 × 告警集成 ③）。


一次根因故障会产生多条告警（上游设备 + N 条被抑制的下游留痕）。若按 alert
触发，同一个故障会被诊断 N 次，结论互相打架还烧 token。故：

- 触发器取 `alert.incident_id`（outbox 行已由 `incident_aggregator._link_outbox`
  回填），一个事件只诊断一次；
- 去重键就是 `incident_id`，复用既有的 `ai:idem` SETNX 占位（与 remedial 下发
  同一套防护），不用另造调度状态。


调用方是 `_apply_escalation_step`，它负责写 `alert.payload` 的
`executed_step_nos` 并发布升级通知。诊断触发若抛异常回滚了升级扫描，
后果是「升级静默丢失」——比「这次没诊断」严重得多。故所有异常在此收敛，
只记日志，返回 False 让调用方继续走后续升级动作。

同理，触发只做「解析上下文 + 投递 Celery 任务」，不做任何 LLM 调用或写库
（除旁路查询），保证在升级扫描的 1 分钟周期内不阻塞。


诊断会话 `user_id` 是 NOT NULL FK，而升级是系统自动触发、没有人类用户。
解析顺序：配置项 `AI_DIAGNOSIS_SYSTEM_USER_ID` → 首个激活超管 → 放弃（跳过）。
"""
from __future__ import annotations

import uuid
from typing import Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_SKILL = "network_troubleshoot"
_SYSTEM_USER_NAMESPACE = 0


def _resolve_system_user_id() -> Optional[int]:
    """解析自动诊断的归属用户 ID。

    Returns:
        用户 ID；无可用用户返回 None（调用方应跳过并记录）。
    """
    from extensions import db

    try:
        from flask import current_app

        configured = current_app.config.get("AI_DIAGNOSIS_SYSTEM_USER_ID")
        if configured:
            return int(configured)
    except Exception:  # noqa: BLE001 - 无 app context 或配置非数字，走回退
        pass

    try:
        from app.models.user import User

        with db.session.no_autoflush:
            user = (
                db.session.query(User)
                .filter(User.is_active.is_(True))
                .order_by(User.id.asc())
                .first()
            )
        return user.id if user else None
    except Exception:  # noqa: BLE001
        logger.warning("ai.incident_diag.system_user_failed", exc_info=True)
        return None


def _build_question(incident_id: int, device_id: Optional[int]) -> str:
    """基于事件上下文构造诊断问题。

    把「归并原因 / 影响面 / 故障前变更 / 连坐设备」这些库里现成的事实直接写进
    问题，避免 LLM 用首轮工具调用去重新发现一遍。
    """
    from app.models.monitor_incident import MonitorIncident
    from extensions import db

    base = f"请定位监控事件 #{incident_id} 的根因并给出处置建议。"
    try:
        with db.session.no_autoflush:
            inc = db.session.get(MonitorIncident, incident_id)
        if inc is None:
            return base
    except Exception:  # noqa: BLE001
        return base

    parts = [
        base,
        f"事件标题：{inc.title}（{inc.incident_key}）",
        f"严重级别：{inc.severity}，当前状态：{inc.status}",
        f"影响面：{inc.alert_count} 条告警 / {inc.device_count} 台设备",
    ]
    if inc.reason_code:
        parts.append(f"归并原因：{inc.reason_code}")

    try:
        from datetime import timedelta

        from app.utils.time_utils import now_utc_naive

        from app.services.ai.incident_context import collect_incident_contexts

        since = now_utc_naive() - timedelta(hours=24)
        ctxs = collect_incident_contexts(
            device_id or inc.root_device_id or -1, since, visible=None, limit=3,
        )
        ctx = next((c for c in ctxs if c["incident_id"] == incident_id), None)
        if ctx:
            if ctx.get("suppressed"):
                sample = ctx["suppressed"][:3]
                ids = "、".join(str(s.get("device_id")) for s in sample)
                parts.append(
                    f"因依赖被抑制的下游告警 {len(ctx['suppressed'])} 条"
                    f"（设备 {ids} 等），疑似上游故障连坐"
                )
            if ctx.get("change"):
                ch = ctx["change"]
                parts.append(
                    f"故障前存在配置变更：{ch.get('action')}（操作人 {ch.get('actor')}，"
                    f"时间 {ch.get('at')}），请优先评估是否为变更引发"
                )
            if ctx.get("diagnosis", {}).get("latest_summary"):
                parts.append(
                    f"该事件已有历史诊断结论：{ctx['diagnosis']['latest_summary']}"
                    "——请判断是同一根因还是新故障"
                )
    except Exception:  # noqa: BLE001 - 上下文是增强项，缺失不影响触发
        logger.warning("ai.incident_diag.context_failed incident=%s",
                       incident_id, exc_info=True)

    return "\n".join(parts)


def trigger_incident_diagnosis(alert, skill_name: Optional[str] = None) -> bool:
    """为告警所属事件触发一次 AI 深度诊断（best-effort，绝不抛出）。

    Args:
        alert: MonitorAlertOutbox 行（需带 incident_id / device_id）。
        skill_name: agentic 技能名；空则取 DEFAULT_SKILL。

    Returns:
        True 表示已入队；False 表示跳过（无事件 / 重复 / 无可用用户 / 投递失败）。
    """
    incident_id = getattr(alert, "incident_id", None)
    if not incident_id:
        logger.info("ai.incident_diag.skip alert=%s reason=no_incident",
                    getattr(alert, "id", None))
        return False

    try:
        from app.services.ai.task_idempotency import try_claim

        task_key = f"incident_diag:{incident_id}"
        claimed, existing = try_claim(
            key=task_key, task_id=str(uuid.uuid4()),
            user_id=_SYSTEM_USER_NAMESPACE, fail_closed=False,
        )
        if not claimed:
            logger.info(
                "ai.incident_diag.duplicate incident=%s existing_task=%s",
                incident_id, existing,
            )
            return False

        user_id = _resolve_system_user_id()
        if user_id is None:
            logger.warning("ai.incident_diag.no_system_user incident=%s", incident_id)
            return False

        from app.utils.auth import get_user_permissions

        perms = sorted(get_user_permissions(user_id))

        device_id = getattr(alert, "device_id", None)
        question = _build_question(incident_id, device_id)

        from app.tasks.ai_tasks import run_agentic_diagnosis

        run_agentic_diagnosis.delay(
            skill_name or DEFAULT_SKILL, question, user_id, perms,
            incident_id=incident_id, device_id=device_id,
        )
        logger.info("ai.incident_diag.queued incident=%s alert=%s skill=%s",
                    incident_id, getattr(alert, "id", None),
                    skill_name or DEFAULT_SKILL)
        return True

    except Exception as e:  # noqa: BLE001 - best-effort：绝不阻断升级扫描
        logger.error("ai.incident_diag.failed incident=%s: %s", incident_id, e,
                     exc_info=True)
        return False
