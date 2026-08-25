# -*- coding: utf-8 -*-
"""监控 OID 分类规则仓库（MonitorOidCategoryRuleRepository）

OID 分类规则（/oid-category-rules）的所有数据库访问统一经此仓库，
禁止在 API 路由层直接操作 db.session（项目约束：数据库必须走 Repository 层）。
"""
from typing import List, Optional

from extensions import db
from app.models.monitor_oid_category_rule import MonitorOidCategoryRule


class MonitorOidCategoryRuleRepository:
    """监控 OID 分类规则仓库"""

    def __init__(self, session=None):
        self.session = session or db.session

    def list_all(self) -> List[MonitorOidCategoryRule]:
        """查询全部 OID 分类规则。"""
        return self.session.query(MonitorOidCategoryRule).all()

    def find_by_id(self, rule_id: int) -> Optional[MonitorOidCategoryRule]:
        """按 ID 查询；不存在返回 None。"""
        return self.session.get(MonitorOidCategoryRule, rule_id)

    def find_enabled_by_vendor(
        self,
        vendor_id: Optional[int],
        device_type: Optional[str] = None,
    ) -> List[MonitorOidCategoryRule]:
        """查询 enabled 且 vendor_id 匹配（或 vendor_id 为 null 的通配规则），按 priority 倒序。

        device_type 可选过滤：传值时仅返回 device_type 匹配或 device_type IS NULL 的通用规则，
        排除 device_type 不匹配的规则；不传时保持原行为（所有 device_type 都参与）。
        """
        from sqlalchemy import or_
        q = (
            self.session.query(MonitorOidCategoryRule)
            .filter(
                MonitorOidCategoryRule.enabled.is_(True),
                or_(
                    MonitorOidCategoryRule.vendor_id == vendor_id,
                    MonitorOidCategoryRule.vendor_id.is_(None),
                ),
            )
        )
        if device_type:
            q = q.filter(
                or_(
                    MonitorOidCategoryRule.device_type == device_type,
                    MonitorOidCategoryRule.device_type.is_(None),
                )
            )
        return q.order_by(MonitorOidCategoryRule.priority.desc()).all()

    def add(self, rule: MonitorOidCategoryRule) -> MonitorOidCategoryRule:
        """新增并 flush。"""
        self.session.add(rule)
        self.session.flush()
        return rule

    def delete(self, rule: MonitorOidCategoryRule) -> None:
        """删除并 flush。"""
        self.session.delete(rule)
        self.session.flush()

    def flush(self) -> None:
        """flush 到数据库（事务提交由 @transactional 负责）。"""
        self.session.flush()
