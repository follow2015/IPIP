# -*- coding: utf-8 -*-
"""监控告警升级策略仓库（MonitorEscalationPolicyRepository）

G4.2：升级策略（/escalation-policies）的所有数据库访问统一经此仓库，
禁止在 API 路由层直接操作 db.session（项目约束：数据库必须走 Repository 层）。

P2-11：策略可挂多个 step（MonitorEscalationStep），按 step_no 顺序执行多级升级。
"""
from typing import List, Optional

from extensions import db
from app.models.monitor_escalation_policy import MonitorEscalationPolicy
from app.models.monitor_escalation_step import MonitorEscalationStep


class MonitorEscalationPolicyRepository:

    def __init__(self, session=None):
        self.session = session or db.session

    def list_all(self) -> List[MonitorEscalationPolicy]:
        return (
            self.session.query(MonitorEscalationPolicy)
            .order_by(MonitorEscalationPolicy.created_at.desc())
            .all()
        )

    def list_enabled(self) -> List[MonitorEscalationPolicy]:
        return (
            self.session.query(MonitorEscalationPolicy)
            .filter(MonitorEscalationPolicy.enabled == True)
            .all()
        )

    def find_by_id(self, policy_id: int) -> Optional[MonitorEscalationPolicy]:
        return self.session.get(MonitorEscalationPolicy, policy_id)

    def add(self, policy: MonitorEscalationPolicy) -> MonitorEscalationPolicy:
        self.session.add(policy)
        self.session.flush()
        return policy

    def delete(self, policy: MonitorEscalationPolicy) -> None:
        self.session.delete(policy)
        self.session.flush()

    def flush(self) -> None:
        self.session.flush()


    def list_steps(self, policy_id: int) -> List[MonitorEscalationStep]:
        return (
            self.session.query(MonitorEscalationStep)
            .filter(MonitorEscalationStep.policy_id == policy_id)
            .order_by(MonitorEscalationStep.step_no.asc())
            .all()
        )

    def add_step(self, step: MonitorEscalationStep) -> MonitorEscalationStep:
        self.session.add(step)
        self.session.flush()
        return step

    def find_step(self, step_id: int) -> Optional[MonitorEscalationStep]:
        return self.session.get(MonitorEscalationStep, step_id)

    def delete_step(self, step: MonitorEscalationStep) -> None:
        self.session.delete(step)
        self.session.flush()

    def replace_steps(self, policy_id: int, steps_data: List[dict]) -> List[MonitorEscalationStep]:
        old = self.list_steps(policy_id)
        for s in old:
            self.session.delete(s)
        self.session.flush()

        new_steps: List[MonitorEscalationStep] = []
        for idx, sd in enumerate(steps_data, start=1):
            step = MonitorEscalationStep(
                policy_id=policy_id,
                step_no=sd.get("step_no", idx),
                wait_minutes=sd["wait_minutes"],
                escalate_severity=sd.get("escalate_severity"),
                escalate_to_role_id=sd.get("escalate_to_role_id"),
                escalate_webhook_url=sd.get("escalate_webhook_url"),
                enabled=sd.get("enabled", True),
            )
            self.session.add(step)
            new_steps.append(step)
        self.session.flush()
        return new_steps
