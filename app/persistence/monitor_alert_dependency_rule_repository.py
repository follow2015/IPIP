# -*- coding: utf-8 -*-
"""P2-17: 监控告警依赖抑制规则仓库"""
from typing import List, Optional

from extensions import db
from app.models.monitor_alert_dependency_rule import MonitorAlertDependencyRule


class MonitorAlertDependencyRuleRepository:
    """监控告警依赖抑制规则仓库"""

    def __init__(self, session=None):
        self.session = session or db.session

    def list_all(self) -> List[MonitorAlertDependencyRule]:
        return (
            self.session.query(MonitorAlertDependencyRule)
            .order_by(MonitorAlertDependencyRule.created_at.desc())
            .all()
        )

    def find_enabled_by_downstream(self, downstream_device_id: int) -> List[MonitorAlertDependencyRule]:
        """查询指向某下游设备的启用规则"""
        return (
            self.session.query(MonitorAlertDependencyRule)
            .filter(
                MonitorAlertDependencyRule.downstream_device_id == downstream_device_id,
                MonitorAlertDependencyRule.enabled == True,
            )
            .all()
        )

    def find_by_id(self, rule_id: int) -> Optional[MonitorAlertDependencyRule]:
        return self.session.get(MonitorAlertDependencyRule, rule_id)

    def add(self, rule: MonitorAlertDependencyRule) -> MonitorAlertDependencyRule:
        self.session.add(rule)
        self.session.flush()
        return rule

    def delete(self, rule: MonitorAlertDependencyRule) -> None:
        self.session.delete(rule)
        self.session.flush()

    def flush(self) -> None:
        self.session.flush()
