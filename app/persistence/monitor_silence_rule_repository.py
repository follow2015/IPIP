# -*- coding: utf-8 -*-
"""监控告警静默规则仓库（MonitorSilenceRuleRepository）

G4.1：静默规则（/silence-rules）的所有数据库访问统一经此仓库，
禁止在 API 路由层直接操作 db.session（项目约束：数据库必须走 Repository 层）。
"""
from typing import List, Optional

from extensions import db
from app.models.monitor_silence_rule import MonitorSilenceRule


class MonitorSilenceRuleRepository:
    """监控告警静默规则仓库"""

    def __init__(self, session=None):
        self.session = session or db.session

    def list_all(self) -> List[MonitorSilenceRule]:
        """查询全部静默规则（按创建时间倒序）。"""
        return (
            self.session.query(MonitorSilenceRule)
            .order_by(MonitorSilenceRule.created_at.desc())
            .all()
        )

    def find_active(self, now) -> List[MonitorSilenceRule]:
        """查询当前活跃的静默规则（enabled + 时间窗口内）。"""
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
        """按 ID 查询静默规则；不存在返回 None。"""
        return self.session.get(MonitorSilenceRule, rule_id)

    def add(self, rule: MonitorSilenceRule) -> MonitorSilenceRule:
        """新增静默规则并 flush。"""
        self.session.add(rule)
        self.session.flush()
        return rule

    def delete(self, rule: MonitorSilenceRule) -> None:
        """删除静默规则并 flush。"""
        self.session.delete(rule)
        self.session.flush()

    def flush(self) -> None:
        """将 session 中未提交的改动 flush 到数据库（事务提交由 @transactional 负责）。"""
        self.session.flush()
