# -*- coding: utf-8 -*-
"""指标模板组仓库（MonitorMetricTemplateGroupRepository）

提供模板组的查询/管理 + 组-模板关联管理：
- 组 CRUD
- 勾选/移除模板入组
- 按设备类型 + 来源查询启用组（供前端展示）

校验规则（service 层强制）：
- 同组模板 device_type + source 必须一致
- 组级 vendor 声明时模板 vendor 需匹配
"""
from typing import List, Optional

from extensions import db
from app.models.monitor_metric_template import MonitorMetricTemplate
from app.models.monitor_metric_template_group import (
    MonitorMetricTemplateGroup,
    MonitorMetricTemplateGroupItem,
)


class MonitorMetricTemplateGroupRepository:
    """指标模板组仓库"""

    def __init__(self, session=None):
        self.session = session or db.session


    def find_by_id(self, group_id: int) -> Optional[MonitorMetricTemplateGroup]:
        return self.session.get(MonitorMetricTemplateGroup, group_id)

    def list_all(self) -> List[MonitorMetricTemplateGroup]:
        return (
            self.session.query(MonitorMetricTemplateGroup)
            .order_by(
                MonitorMetricTemplateGroup.device_type.asc(),
                MonitorMetricTemplateGroup.source.asc(),
                MonitorMetricTemplateGroup.display_order.asc(),
            )
            .all()
        )

    def find_enabled_by_device_type(
        self, device_type: str, source: str, vendor: Optional[str] = None
    ) -> List[MonitorMetricTemplateGroup]:
        """返回某设备类型 + 来源（可选厂商）下启用的组（按 display_order 排序）。

        设备自动匹配时：若设备有品牌，优先匹配 vendor 一致的组；vendor 为空的
        通用组始终可匹配（KISS：组 vendor 可空表示不约束厂商）。
        """
        q = self.session.query(MonitorMetricTemplateGroup).filter(
            MonitorMetricTemplateGroup.device_type == device_type,
            MonitorMetricTemplateGroup.source == source,
            MonitorMetricTemplateGroup.enabled.is_(True),
        )
        if vendor:
            q = q.filter(
                db.or_(
                    MonitorMetricTemplateGroup.vendor == vendor,
                    MonitorMetricTemplateGroup.vendor.is_(None),
                )
            )
        return (
            q.order_by(MonitorMetricTemplateGroup.display_order.asc())
            .all()
        )

    def find_by_name(self, name: str, device_type: str, source: str) -> Optional[MonitorMetricTemplateGroup]:
        return (
            self.session.query(MonitorMetricTemplateGroup)
            .filter_by(name=name, device_type=device_type, source=source)
            .first()
        )


    def create(self, **kwargs) -> MonitorMetricTemplateGroup:
        group = MonitorMetricTemplateGroup(**kwargs)
        self.session.add(group)
        self.session.flush()
        return group

    def update(self, group: MonitorMetricTemplateGroup, **kwargs) -> MonitorMetricTemplateGroup:
        for k, v in kwargs.items():
            if hasattr(group, k) and k not in ("id", "created_at", "updated_at"):
                setattr(group, k, v)
        self.session.flush()
        return group

    def delete(self, group: MonitorMetricTemplateGroup) -> None:
        self.session.delete(group)
        self.session.flush()


    def list_items(self, group_id: int) -> List[MonitorMetricTemplateGroupItem]:
        return (
            self.session.query(MonitorMetricTemplateGroupItem)
            .filter_by(group_id=group_id)
            .all()
        )

    def list_templates_in_group(self, group_id: int) -> List[MonitorMetricTemplate]:
        """返回组内全部模板（按 id 排序）。"""
        items = self.list_items(group_id)
        ids = [it.template_id for it in items]
        if not ids:
            return []
        return (
            self.session.query(MonitorMetricTemplate)
            .filter(MonitorMetricTemplate.id.in_(ids))
            .order_by(MonitorMetricTemplate.id.asc())
            .all()
        )

    def add_template(self, group_id: int, template_id: int) -> MonitorMetricTemplateGroupItem:
        item = MonitorMetricTemplateGroupItem(group_id=group_id, template_id=template_id)
        self.session.add(item)
        self.session.flush()
        return item

    def remove_template(self, group_id: int, template_id: int) -> bool:
        deleted = (
            self.session.query(MonitorMetricTemplateGroupItem)
            .filter_by(group_id=group_id, template_id=template_id)
            .delete(synchronize_session=False)
        )
        self.session.flush()
        return deleted > 0

    def is_template_in_group(self, group_id: int, template_id: int) -> bool:
        return (
            self.session.query(MonitorMetricTemplateGroupItem)
            .filter_by(group_id=group_id, template_id=template_id)
            .first()
        ) is not None
