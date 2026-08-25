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
    """监控告警升级策略仓库"""

    def __init__(self, session=None):
        self.session = session or db.session

    def list_all(self) -> List[MonitorEscalationPolicy]:
        """查询全部升级策略（按创建时间倒序）。"""
        return (
            self.session.query(MonitorEscalationPolicy)
            .order_by(MonitorEscalationPolicy.created_at.desc())
            .all()
        )

    def list_enabled(self) -> List[MonitorEscalationPolicy]:
        """查询全部启用的升级策略（供 escalation_service 扫描使用）。"""
        return (
            self.session.query(MonitorEscalationPolicy)
            .filter(MonitorEscalationPolicy.enabled == True)  # noqa: E712
            .all()
        )

    def find_by_id(self, policy_id: int) -> Optional[MonitorEscalationPolicy]:
        """按 ID 查询升级策略；不存在返回 None。"""
        return self.session.get(MonitorEscalationPolicy, policy_id)

    def add(self, policy: MonitorEscalationPolicy) -> MonitorEscalationPolicy:
        """新增升级策略并 flush。"""
        self.session.add(policy)
        self.session.flush()
        return policy

    def delete(self, policy: MonitorEscalationPolicy) -> None:
        """删除升级策略并 flush。"""
        self.session.delete(policy)
        self.session.flush()

    def flush(self) -> None:
        """将 session 中未提交的改动 flush 到数据库（事务提交由 @transactional 负责）。"""
        self.session.flush()


    def list_steps(self, policy_id: int) -> List[MonitorEscalationStep]:
        """查询策略下全部 step（按 step_no 升序）。"""
        return (
            self.session.query(MonitorEscalationStep)
            .filter(MonitorEscalationStep.policy_id == policy_id)
            .order_by(MonitorEscalationStep.step_no.asc())
            .all()
        )

    def add_step(self, step: MonitorEscalationStep) -> MonitorEscalationStep:
        """新增 step 并 flush。"""
        self.session.add(step)
        self.session.flush()
        return step

    def find_step(self, step_id: int) -> Optional[MonitorEscalationStep]:
        """按 ID 查询 step；不存在返回 None。"""
        return self.session.get(MonitorEscalationStep, step_id)

    def delete_step(self, step: MonitorEscalationStep) -> None:
        """删除 step 并 flush。"""
        self.session.delete(step)
        self.session.flush()

    def replace_steps(self, policy_id: int, steps_data: List[dict]) -> List[MonitorEscalationStep]:
        """全量替换策略下的 step（先删后建，保持 step_no 连续从 1 开始）。

        供 create_policy / update_policy 调用，事务由上层 @transactional 控制。
        """
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
