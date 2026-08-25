# -*- coding: utf-8 -*-
"""MonitorDynamicConfig 仓储（DB 持久化层）。

提交决策权交给调用方（PUT 路由的 @transactional / 启动加载的独立会话）。
"""
from typing import Dict, List, Optional

from app.models.monitor_dynamic_config import MonitorDynamicConfig
from app.persistence.base import SQLAlchemyRepository


class MonitorDynamicConfigRepository(SQLAlchemyRepository):

    def __init__(self, session=None):
        super().__init__(MonitorDynamicConfig, session)

    def upsert(
        self,
        key: str,
        value: str,
        value_type: str = "string",
        description: str = "",
        updated_by: str = "",
    ) -> MonitorDynamicConfig:
        row = (
            self.session.query(MonitorDynamicConfig)
            .filter_by(config_key=key)
            .first()
        )
        if row is None:
            row = MonitorDynamicConfig(config_key=key)
            self.session.add(row)
        row.config_value = value
        row.value_type = value_type
        row.description = description
        row.updated_by = updated_by
        self.session.flush()
        return row

    def get_value(self, key: str) -> Optional[str]:
        row = (
            self.session.query(MonitorDynamicConfig)
            .filter_by(config_key=key)
            .first()
        )
        return row.config_value if row is not None else None

    def find_all(self) -> List[MonitorDynamicConfig]:
        return self.session.query(MonitorDynamicConfig).all()

    def as_dict(self) -> Dict[str, MonitorDynamicConfig]:
        return {r.config_key: r for r in self.find_all()}
