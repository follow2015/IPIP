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

    def list_enabled(self) -> List[MonitorAlertDependencyRule]:
        """查询**全部启用**规则（B-44 收敛：告警抑制的规则加载热路径）。

        与 `list_all()`（后台管理列表，含停用规则）**刻意分开**：抑制算链
        只认启用规则，误用 `list_all()` 会让停用的规则继续生效。
        不排序：调用方按 (上游,下游) 建索引，顺序无意义（原实现亦无 order_by）。
        """
        return (
            self.session.query(MonitorAlertDependencyRule)
            .filter_by(enabled=True)
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
