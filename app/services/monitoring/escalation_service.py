# -*- coding: utf-8 -*-
"""G4.2: 告警升级服务

扫描未确认告警（acknowledged_at IS NULL）+ 到期升级：
1. 查询 enabled 升级策略
2. 对每条未确认告警匹配策略（alert_type + severity）
3. 检查 created_at + wait_minutes <= now
4. 执行升级动作：
   - 提升严重级别（更新 outbox.severity）
   - 通知 escalate_to_role_id 角色（publish SSE）
   - 触发 webhook（POST，best-effort）
5. 标记已升级（payload.escalation_count += 1，避免重复升级）

由 outbox_sender 周期调用 run_escalation_scan()。
"""
import json
from app.utils.logging import get_logger
from datetime import datetime, timedelta, timezone
from typing import List

from app.utils.http_client import post_json
from app.models.monitor_alert_outbox import MonitorAlertOutbox
from app.models.monitor_escalation_policy import MonitorEscalationPolicy
from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
from app.persistence.monitor_escalation_policy_repository import MonitorEscalationPolicyRepository
from app.persistence.rbac_repository import RoleRepository

logger = get_logger(__name__)

_WEBHOOK_TIMEOUT = 5  # 秒

_policy_repo = MonitorEscalationPolicyRepository()
_outbox_repo = MonitorAlertOutboxRepository()
_role_repo = RoleRepository()


def _match_policy(alert: MonitorAlertOutbox,
                  policy: MonitorEscalationPolicy) -> bool:
    """判定告警是否匹配升级策略"""
    if policy.alert_type and alert.alert_type != policy.alert_type:
        return False
    if policy.severity and alert.severity != policy.severity:
        return False
    return True


def _get_role_user_ids(role_id: int) -> List[int]:
    """获取角色下的用户 ID 列表"""
    return _role_repo.find_user_ids_by_role_id(role_id)


def _publish_escalation(alert: MonitorAlertOutbox,
                        policy: MonitorEscalationPolicy,
                        escalation_count: int,
                        step=None) -> None:
    """发布升级事件（SSE + 可选 webhook）。

    P2-11: step 不为 None 时使用 step 上的 escalate_* 字段，否则回退 policy 单级字段。
    """
    escalate_severity = (step.escalate_severity if step else policy.escalate_severity)
    escalate_to_role_id = (step.escalate_to_role_id if step else policy.escalate_to_role_id)
    escalate_webhook_url = (step.escalate_webhook_url if step else policy.escalate_webhook_url)

    payload: dict = {}
    try:
        from app.services.switch_events import emit_global_event_with_targets
        target_user_ids = None
        if escalate_to_role_id:
            target_user_ids = _get_role_user_ids(escalate_to_role_id)

        payload = {
            "alert_id": alert.id,
            "device_id": alert.device_id,
            "alert_type": alert.alert_type,
            "original_severity": alert.severity,
            "escalated_severity": escalate_severity or alert.severity,
            "policy_id": policy.id,
            "policy_name": policy.name,
            "escalation_count": escalation_count,
            "step_no": (step.step_no if step else None),
            "escalated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }
        emit_global_event_with_targets(
            event_type="monitor_escalation",
            payload=payload,
            target_user_ids=target_user_ids,
        )
    except Exception as exc:
        logger.warning("升级 SSE 发布失败 alert_id=%s: %s", alert.id, exc)

    if escalate_webhook_url:
        try:
            post_json(escalate_webhook_url, payload, timeout=_WEBHOOK_TIMEOUT,
                      allow_redirects=True)
        except Exception as exc:
            logger.warning("升级 webhook 失败 alert_id=%s url=%s: %s",
                           alert.id, escalate_webhook_url, exc)

    try:
        from extensions import db

        db.session.commit()
    except Exception as exc:
        logger.warning("升级状态提交失败 alert_id=%s: %s", alert.id, exc)

    from app.services.notification_service import NotificationService
    from app.core.enums import ChannelType

    NotificationService().notify_strict(
        type="monitor_escalation",
        severity=escalate_severity or alert.severity,
        title=f"告警升级: {alert.alert_type}",
        content=(
            f"设备 {alert.device_id} 告警 {alert.alert_type} 已升级至 "
            f"{escalate_severity or alert.severity}"
        ),
        payload=payload,
        source_module="monitoring.escalation",
        target_type="role",
        target_id=escalate_to_role_id,
        channels=(ChannelType.INBOX, ChannelType.EMAIL, ChannelType.VOICE),
        idempotency_key=f"escalation:{alert.id}:{escalation_count}",
        ack_required=True,
    )


def _apply_escalation_step(alert: MonitorAlertOutbox,
                           policy: MonitorEscalationPolicy,
                           step,
                           ts: datetime) -> bool:
    """对单条告警执行单级升级动作（更新 severity + payload + 发布）。返回是否升级。"""
    if step.escalate_severity:
        alert.severity = step.escalate_severity

    payload = alert.payload or {}
    new_count = int(payload.get("escalation_count", 0)) + 1
    new_payload = dict(payload)
    new_payload["escalation_count"] = new_count
    new_payload["last_escalated_at"] = ts.isoformat()
    new_payload["escalation_policy_id"] = policy.id
    new_payload["escalation_step_no"] = step.step_no
    alert.payload = new_payload

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(alert, "payload")

    _publish_escalation(alert, policy, new_count, step=step)
    return True


def run_escalation_scan(now: datetime = None) -> int:
    """扫描未确认告警并执行升级。返回升级的告警数。

    P2-11: 优先走多级 step 链；policy 无 step 时回退单级模式（向后兼容）。
    由 outbox_sender 周期调用（建议每 1 分钟）。
    """
    ts = now or datetime.now(timezone.utc).replace(tzinfo=None)
    upgraded = 0

    try:
        policies = _policy_repo.list_enabled()
        if not policies:
            return 0

        policy_steps = {p.id: _policy_repo.list_steps(p.id) for p in policies}

        alerts = _outbox_repo.find_unacknowledged_sent(limit=200)

        for alert in alerts:
            for policy in policies:
                if not _match_policy(alert, policy):
                    continue

                steps = policy_steps.get(policy.id, [])
                if steps:
                    payload = alert.payload or {}
                    executed_steps = set(payload.get("executed_step_nos", []))
                    did_upgrade = False
                    for step in steps:
                        if not step.enabled:
                            continue
                        if step.step_no in executed_steps:
                            continue
                        due_at = alert.created_at + timedelta(minutes=step.wait_minutes)
                        if ts < due_at:
                            continue
                        if _apply_escalation_step(alert, policy, step, ts):
                            executed_steps.add(step.step_no)
                            new_payload = dict(alert.payload or {})
                            new_payload["executed_step_nos"] = sorted(executed_steps)
                            alert.payload = new_payload
                            from sqlalchemy.orm.attributes import flag_modified
                            flag_modified(alert, "payload")
                            upgraded += 1
                            did_upgrade = True
                            break  # 单次扫描每条告警每 policy 只升一级
                    if did_upgrade:
                        break  # 一条告警只匹配一个策略
                else:
                    due_at = alert.created_at + timedelta(minutes=policy.wait_minutes)
                    if ts < due_at:
                        continue

                    payload = alert.payload or {}
                    esc_count = int(payload.get("escalation_count", 0))
                    last_esc_at = payload.get("last_escalated_at")

                    if esc_count > 0 and policy.repeat_minutes == 0:
                        continue

                    if esc_count > 0 and last_esc_at:
                        try:
                            last_ts = datetime.fromisoformat(last_esc_at)
                            if ts < last_ts + timedelta(minutes=policy.repeat_minutes):
                                continue
                        except ValueError:
                            pass

                    if policy.escalate_severity:
                        alert.severity = policy.escalate_severity

                    new_count = esc_count + 1
                    new_payload = dict(payload)
                    new_payload["escalation_count"] = new_count
                    new_payload["last_escalated_at"] = ts.isoformat()
                    new_payload["escalation_policy_id"] = policy.id
                    alert.payload = new_payload

                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(alert, "payload")

                    _publish_escalation(alert, policy, new_count)
                    upgraded += 1
                    break  # 一条告警只匹配一个策略

        if upgraded > 0:
            _outbox_repo.flush()
        return upgraded

    except Exception as exc:
        logger.error("升级扫描失败: %s", exc, exc_info=True)
        return 0


def _policy_to_dict_with_steps(policy) -> dict:
    """序列化 policy 并附带 steps 列表（P2-11）。"""
    data = policy.to_dict()
    data["steps"] = [s.to_dict() for s in _policy_repo.list_steps(policy.id)]
    return data


def list_escalation_policies() -> list:
    """列出全部升级策略（序列化为 dict 列表，含 steps，供路由层直接返回）。

    P1-1：读路径下沉 service，路由层不再直访 repository。
    P2-11：附带 steps 列表。
    """
    from app.persistence.monitor_escalation_policy_repository import MonitorEscalationPolicyRepository
    repo = MonitorEscalationPolicyRepository()
    return [_policy_to_dict_with_steps(r) for r in repo.list_all()]


def create_policy(data: dict) -> dict:
    """创建升级策略（I6：route handler 不再构造 Model + 调 repo）。

    P2-11: 若 data 含 steps 数组，同步创建 step 链。
    """
    from app.models.monitor_escalation_policy import MonitorEscalationPolicy
    from app.persistence.monitor_escalation_policy_repository import MonitorEscalationPolicyRepository
    from app.exceptions.validation import ValidationError

    name = data.get("name")
    if not name:
        raise ValidationError("name 必填")
    repo = MonitorEscalationPolicyRepository()
    policy = MonitorEscalationPolicy(
        name=name,
        alert_type=data.get("alert_type"),
        severity=data.get("severity"),
        wait_minutes=data.get("wait_minutes", 30),
        escalate_severity=data.get("escalate_severity"),
        escalate_to_role_id=data.get("escalate_to_role_id"),
        escalate_webhook_url=data.get("escalate_webhook_url"),
        repeat_minutes=data.get("repeat_minutes", 60),
        enabled=data.get("enabled", True),
    )
    repo.add(policy)
    repo.flush()

    steps_data = data.get("steps")
    if steps_data:
        _validate_steps(steps_data)
        repo.replace_steps(policy.id, steps_data)

    return _policy_to_dict_with_steps(policy)


def update_policy(policy_id: int, data: dict) -> dict:
    """更新升级策略。

    P2-11: 若 data 含 steps 数组，全量替换 step 链。
    """
    from app.persistence.monitor_escalation_policy_repository import MonitorEscalationPolicyRepository
    from app.exceptions.business import BusinessLogicError
    repo = MonitorEscalationPolicyRepository()
    policy = repo.find_by_id(policy_id)
    if not policy:
        raise BusinessLogicError("升级策略不存在", status_code=404)
    for k in (
        "name", "alert_type", "severity", "wait_minutes",
        "escalate_severity", "escalate_to_role_id", "escalate_webhook_url",
        "repeat_minutes", "enabled",
    ):
        if k in data:
            setattr(policy, k, data[k])
    repo.flush()

    if "steps" in data:
        steps_data = data["steps"] or []
        _validate_steps(steps_data)
        repo.replace_steps(policy.id, steps_data)

    return _policy_to_dict_with_steps(policy)


def delete_policy(policy_id: int) -> dict:
    """删除升级策略（step 由外键 ON DELETE CASCADE 自动清理）。"""
    from app.persistence.monitor_escalation_policy_repository import MonitorEscalationPolicyRepository
    from app.exceptions.business import BusinessLogicError
    repo = MonitorEscalationPolicyRepository()
    policy = repo.find_by_id(policy_id)
    if not policy:
        raise BusinessLogicError("升级策略不存在", status_code=404)
    repo.delete(policy)
    return {"deleted": policy_id}


def _validate_steps(steps_data: list) -> None:
    """校验 step 链数据。"""
    from app.exceptions.validation import ValidationError
    if not isinstance(steps_data, list):
        raise ValidationError("steps 必须是数组")
    if len(steps_data) > 20:
        raise ValidationError("单策略最多 20 个 step")
    seen_nos = set()
    for idx, sd in enumerate(steps_data, start=1):
        if not isinstance(sd, dict):
            raise ValidationError(f"step[{idx}] 必须是对象")
        if "wait_minutes" not in sd:
            raise ValidationError(f"step[{idx}] 缺少 wait_minutes")
        if not isinstance(sd["wait_minutes"], int) or sd["wait_minutes"] < 1:
            raise ValidationError(f"step[{idx}].wait_minutes 必须是 >=1 的整数")
        step_no = sd.get("step_no", idx)
        if step_no in seen_nos:
            raise ValidationError(f"step_no={step_no} 重复")
        seen_nos.add(step_no)
