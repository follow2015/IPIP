# -*- coding: utf-8 -*-
"""P2-13: SLA 目标仓库"""
from typing import List, Optional

from extensions import db
from app.models.monitor_sla_target import MonitorSlaTarget


class MonitorSlaTargetRepository:

    def __init__(self, session=None):
        self.session = session or db.session

    def list_all(self) -> List[MonitorSlaTarget]:
        return (
            self.session.query(MonitorSlaTarget)
            .order_by(MonitorSlaTarget.created_at.desc())
            .all()
        )

    def find_by_id(self, target_id: int) -> Optional[MonitorSlaTarget]:
        return self.session.get(MonitorSlaTarget, target_id)

    def add(self, target: MonitorSlaTarget) -> MonitorSlaTarget:
        self.session.add(target)
        self.session.flush()
        return target

    def delete(self, target: MonitorSlaTarget) -> None:
        self.session.delete(target)
        self.session.flush()

    def flush(self) -> None:
        self.session.flush()
