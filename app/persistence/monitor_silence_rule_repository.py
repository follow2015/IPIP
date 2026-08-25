# -*- coding: utf-8 -*-
"""监控告警静默规则仓库（MonitorSilenceRuleRepository）

G4.1：静默规则（/silence-rules）的所有数据库访问统一经此仓库，
禁止在 API 路由层直接操作 db.session（项目约束：数据库必须走 Repository 层）。
"""
from typing import List, Optional

from extensions import db
from app.models.monitor_silence_rule import MonitorSilenceRule


class MonitorSilenceRuleRepository:

    def __init__(self, session=None):
        self.session = session or db.session

    def list_all(self) -> List[MonitorSilenceRule]:
        return (
            self.session.query(MonitorSilenceRule)
            .order_by(MonitorSilenceRule.created_at.desc())
            .all()
        )

    def find_active(self, now) -> List[MonitorSilenceRule]:
        return (
            self.session.query(MonitorSilenceRule)
            .filter(
                MonitorSilenceRule.enabled == True,
                MonitorSilenceRule.silence_from <= now,
                MonitorSilenceRule.silence_until >= now,
            )
            .all()
        )

    def find_by_id(self, rule_id: int) -> Optional[MonitorSilenceRule]:
        return self.session.get(MonitorSilenceRule, rule_id)

    def add(self, rule: MonitorSilenceRule) -> MonitorSilenceRule:
        self.session.add(rule)
        self.session.flush()
        return rule

    def delete(self, rule: MonitorSilenceRule) -> None:
        self.session.delete(rule)
        self.session.flush()

    def flush(self) -> None:
        self.session.flush()
