# -*- coding: utf-8 -*-
"""安全巡检 findings 仓储（`security_findings` 表）。

**为什么单独建仓储**：`tests/test_service_layer_session_budget.py` 的 C 类台账
（`Model.query` / `cls.query`）预算为 **0** 且**只减不增**；`scanner` 若直查
`SecurityFinding.query` 就是新增欠账。查询收进仓储是本仓既定的收敛路径。

**只读**：这里只有查询；插入与刷新（`upsert_finding` 里的 `db.session.add` /
`flush`）留在 `scanner` —— 那是巡检语义（幂等刷新 `first_seen`/`last_seen`、
本轮不再违规则转 `resolved`），搬进数据层会把它藏起来。
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.core.pagination_limits import ensure_offset_within_limit
from app.exceptions.data_access import QueryExecutionError
from app.models.security_finding import SecurityFinding
from app.persistence.base import SQLAlchemyRepository

_EMPTY_KEEP_SENTINEL = -1


class SecurityFindingRepository(SQLAlchemyRepository):
    """`security_findings` 表的只读访问。"""

    def __init__(self, session=None):
        super().__init__(SecurityFinding, session)

    def find_by_subject(
        self, rule_id: str, subject_type: str, subject_id: int
    ) -> Optional[SecurityFinding]:
        """按唯一键 `(rule_id, subject_type, subject_id)` 取一行（upsert 前查重用）。

        Raises:
            QueryExecutionError: 查询失败。调用方 `scanner.run_scan` 会整体回滚并上抛。
        """
        try:
            return (
                self.session.query(SecurityFinding)
                .filter(
                    SecurityFinding.rule_id == rule_id,
                    SecurityFinding.subject_type == subject_type,
                    SecurityFinding.subject_id == subject_id,
                )
                .first()
            )
        except SQLAlchemyError as e:
            self.logger.error("按唯一键查询安全发现项失败: %s", e)
            raise QueryExecutionError("查询安全发现项失败", original_error=e) from e

    def find_open_excluding(self, rule_id: str, keep_subject_ids) -> List[SecurityFinding]:
        """取该 rule 下仍为 `open`、且 `subject_id` **不在**保留集合里的行（待置 resolved）。

        Args:
            rule_id: 规则 ID。
            keep_subject_ids: 本轮仍违规的主体集合；空集合表示"全部转 resolved"。
        """
        keep = set(keep_subject_ids) or {_EMPTY_KEEP_SENTINEL}
        try:
            return (
                self.session.query(SecurityFinding)
                .filter(
                    SecurityFinding.rule_id == rule_id,
                    SecurityFinding.status == "open",
                    ~SecurityFinding.subject_id.in_(keep),
                )
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error("查询待消除的安全发现项失败: %s", e)
            raise QueryExecutionError("查询待消除的安全发现项失败", original_error=e) from e

    def open_counts_by_rule(self) -> List[tuple]:
        """按 `rule_id` 聚合仍为 `open` 的发现项数量（概览页用）。

        Returns:
            list[tuple[str, str, int]]：`(rule_id, severity, count)`。

        Raises:
            QueryExecutionError: 查询失败。
        """
        try:
            return (
                self.session.query(
                    SecurityFinding.rule_id,
                    SecurityFinding.severity,
                    func.count(SecurityFinding.id),
                )
                .filter(SecurityFinding.status == "open")
                .group_by(SecurityFinding.rule_id, SecurityFinding.severity)
                .all()
            )
        except SQLAlchemyError as e:
            self.logger.error("聚合安全发现项失败: %s", e)
            raise QueryExecutionError("聚合安全发现项失败", original_error=e) from e

    def list_paged(self, filters: dict, page: int, size: int) -> tuple:
        """按过滤条件分页列出发现项（最近发现优先）。

        Args:
            filters: 字段名 → 期望值；仅认 `rule_id` / `severity` / `status` /
                `subject_type`，空值忽略（等价于不过滤）。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            tuple[list[SecurityFinding], int]：`(当前页行, 过滤后总数)`。

        Raises:
            QueryExecutionError: 查询失败。
        """
        allowed = ("rule_id", "severity", "status", "subject_type")
        try:
            query = self.session.query(SecurityFinding)
            for field, value in (filters or {}).items():
                if field in allowed and value:
                    query = query.filter(getattr(SecurityFinding, field) == value)
            total = query.count()
            offset = (page - 1) * size
            ensure_offset_within_limit(offset)
            rows = (query.order_by(SecurityFinding.last_seen.desc())
                    .offset(offset).limit(size).all())
            return rows, total
        except SQLAlchemyError as e:
            self.logger.error("分页查询安全发现项失败: %s", e)
            raise QueryExecutionError("分页查询安全发现项失败", original_error=e) from e
