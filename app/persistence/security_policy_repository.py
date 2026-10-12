# -*- coding: utf-8 -*-
"""安全策略仓储（`security_policies` KV 表）。

**为什么单独建仓储**：`tests/test_service_layer_session_budget.py` 的 C 类台账
（`Model.query` / `cls.query`）预算为 **0** 且**只减不增**；`policy_service` 若直接
`SecurityPolicy.query.filter(...)` 就是新增欠账（门禁实测报 `policy_service.py: 2`）。
把查询收进仓储是本仓既定的收敛路径（ADR-002：Service 层不自行直查模型）。

**只读**：写入（乐观锁 + 审计 `before`/`after` + Redis 刷新顺序）留在
`policy_service.set_value` —— 那是业务语义，搬进数据层会把它藏起来。
"""
from __future__ import annotations

from typing import Dict, List

from sqlalchemy.exc import SQLAlchemyError

from app.exceptions.data_access import QueryExecutionError
from app.models.security_policy import SecurityPolicy
from app.persistence.base import SQLAlchemyRepository


class SecurityPolicyRepository(SQLAlchemyRepository):
    """`security_policies` 表的只读访问（覆盖行查询）。"""

    def __init__(self, session=None):
        super().__init__(SecurityPolicy, session)

    def find_by_keys(self, keys: List[str]) -> List[SecurityPolicy]:
        """按 `policy_key` 批量取覆盖行。

        Args:
            keys: 策略键列表；为空时**不发 SQL** 直接返回空列表。

        Returns:
            覆盖行列表（未覆盖的键不会出现在结果里）。

        Raises:
            QueryExecutionError: 查询失败。调用方（`policy_service`）按失败语义
                自行降级为"全用注册表默认值"。
        """
        if not keys:
            return []
        try:
            return (
                self.session.query(SecurityPolicy)
                .filter(SecurityPolicy.policy_key.in_(keys))
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error("按 key 批量查询安全策略失败: %s", e)
            raise QueryExecutionError("查询安全策略失败", original_error=e) from e

    def map_by_keys(self, keys: List[str]) -> Dict[str, SecurityPolicy]:
        """`find_by_keys` 的字典形态：`{policy_key: 覆盖行}`（供策略页取版本号用）。"""
        return {row.policy_key: row for row in self.find_by_keys(keys)}
