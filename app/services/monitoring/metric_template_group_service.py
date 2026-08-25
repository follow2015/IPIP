# -*- coding: utf-8 -*-
"""指标模板组服务（MetricTemplateGroupService）

封装模板组的业务逻辑 + 校验规则：
- 同组模板 device_type + source 必须一致
- 组级 vendor 声明时模板 vendor 需匹配
- 组名 (name, device_type, source) 唯一

供 API 层调用，保持路由层薄。
"""
from typing import List

from app.exceptions.business import BusinessLogicError
from app.exceptions.validation import ValidationError
from app.models.monitor_metric_template import MonitorMetricTemplate
from app.models.monitor_metric_template_group import MonitorMetricTemplateGroup
from app.persistence.monitor_metric_template_group_repository import (
    MonitorMetricTemplateGroupRepository,
)
from app.persistence.monitor_metric_template_repository import (
    MonitorMetricTemplateRepository,
)

_ALLOWED_DEVICE_TYPE = {"network", "server", "other"}
_ALLOWED_SOURCE = {"snmp", "ipmi", "zabbix"}


class MetricTemplateGroupService:
    """指标模板组服务"""

    def __init__(self, group_repo=None, template_repo=None):
        self._group_repo = group_repo or MonitorMetricTemplateGroupRepository()
        self._template_repo = template_repo or MonitorMetricTemplateRepository()


    def list_groups(self) -> List[dict]:
        groups = self._group_repo.list_all()
        result = []
        for g in groups:
            d = g.to_dict()
            d["template_count"] = len(self._group_repo.list_items(g.id))
            result.append(d)
        return result

    def get_group_detail(self, group_id: int) -> dict:
        group = self._group_repo.find_by_id(group_id)
        if not group:
            raise BusinessLogicError("模板组不存在", status_code=404)
        d = group.to_dict()
        templates = self._group_repo.list_templates_in_group(group_id)
        d["templates"] = [t.to_dict() for t in templates]
        return d


    def create_group(self, body: dict) -> dict:
        name = body.get("name", "").strip()
        device_type = body.get("device_type")
        source = body.get("source")
        if not name:
            raise ValidationError("name 不能为空")
        if device_type not in _ALLOWED_DEVICE_TYPE:
            raise ValidationError("device_type 不合法")
        if source not in _ALLOWED_SOURCE:
            raise ValidationError("source 不合法")
        existing = self._group_repo.find_by_name(name, device_type, source)
        if existing:
            raise ValidationError("组名已存在（同 device_type+source 内唯一）")
        group = self._group_repo.create(
            name=name,
            device_type=device_type,
            source=source,
            vendor=body.get("vendor"),
            display_order=int(body.get("display_order", 0)),
            enabled=bool(body.get("enabled", True)),
            description=body.get("description"),
        )
        return group.to_dict()

    def update_group(self, group_id: int, body: dict) -> dict:
        group = self._group_repo.find_by_id(group_id)
        if not group:
            raise BusinessLogicError("模板组不存在", status_code=404)
        new_name = body.get("name", group.name).strip() if body.get("name") else group.name
        new_dt = body.get("device_type", group.device_type)
        new_src = body.get("source", group.source)
        if new_dt not in _ALLOWED_DEVICE_TYPE:
            raise ValidationError("device_type 不合法")
        if new_src not in _ALLOWED_SOURCE:
            raise ValidationError("source 不合法")
        if (new_name, new_dt, new_src) != (group.name, group.device_type, group.source):
            existing = self._group_repo.find_by_name(new_name, new_dt, new_src)
            if existing and existing.id != group_id:
                raise ValidationError("组名已存在（同 device_type+source 内唯一）")
        new_vendor = body.get("vendor", group.vendor)
        if new_dt != group.device_type or new_src != group.source or new_vendor != group.vendor:
            templates = self._group_repo.list_templates_in_group(group_id)
            for t in templates:
                if t.device_type != new_dt or t.source != new_src:
                    raise ValidationError(
                        f"组内模板 {t.metric_key} 的 device_type/source 与新值不兼容，不能修改"
                    )
                if new_vendor and t.vendor != new_vendor:
                    raise ValidationError(
                        f"组内模板 {t.metric_key} 的厂商（{t.vendor or '未声明'}）与新厂商（{new_vendor}）不兼容，不能修改"
                    )
        updates = {}
        for k in ("name", "device_type", "source", "vendor", "display_order", "enabled", "description"):
            if k in body:
                updates[k] = body[k]
        updates["name"] = new_name
        self._group_repo.update(group, **updates)
        return group.to_dict()

    def delete_group(self, group_id: int) -> dict:
        group = self._group_repo.find_by_id(group_id)
        if not group:
            raise BusinessLogicError("模板组不存在", status_code=404)
        self._group_repo.delete(group)
        return {"deleted": True, "id": group_id}


    def add_template_to_group(self, group_id: int, template_id: int) -> dict:
        group = self._group_repo.find_by_id(group_id)
        if not group:
            raise BusinessLogicError("模板组不存在", status_code=404)
        tpl = self._template_repo.find_by_id(template_id)
        if not tpl:
            raise BusinessLogicError("指标模板不存在", status_code=404)
        if tpl.device_type != group.device_type or tpl.source != group.source:
            raise ValidationError(
                "模板的 device_type/source 与组不兼容，不能加入同组"
            )
        if group.vendor and tpl.vendor != group.vendor:
            raise ValidationError(
                f"模板 {tpl.metric_key} 的厂商（{tpl.vendor or '未声明'}）与组厂商（{group.vendor}）不一致，不能加入同组"
            )
        if self._group_repo.is_template_in_group(group_id, template_id):
            return {"added": False, "reason": "already_in_group"}
        self._group_repo.add_template(group_id, template_id)
        return {"added": True}

    def remove_template_from_group(self, group_id: int, template_id: int) -> dict:
        group = self._group_repo.find_by_id(group_id)
        if not group:
            raise BusinessLogicError("模板组不存在", status_code=404)
        removed = self._group_repo.remove_template(group_id, template_id)
        return {"removed": removed}

    def batch_add_templates(self, group_id: int, template_ids: List[int]) -> dict:
        """批量勾选模板入组（幂等，跳过已存在的）。"""
        group = self._group_repo.find_by_id(group_id)
        if not group:
            raise BusinessLogicError("模板组不存在", status_code=404)
        added = 0
        skipped = 0
        for tid in template_ids:
            tpl = self._template_repo.find_by_id(tid)
            if not tpl:
                raise BusinessLogicError(f"指标模板 {tid} 不存在", status_code=404)
            if tpl.device_type != group.device_type or tpl.source != group.source:
                raise ValidationError(
                    f"模板 {tpl.metric_key} 的 device_type/source 与组不兼容"
                )
            if group.vendor and tpl.vendor != group.vendor:
                raise ValidationError(
                    f"模板 {tpl.metric_key} 的厂商（{tpl.vendor or '未声明'}）与组厂商（{group.vendor}）不一致，不能加入同组"
                )
            if self._group_repo.is_template_in_group(group_id, tid):
                skipped += 1
                continue
            self._group_repo.add_template(group_id, tid)
            added += 1
        return {"added": added, "skipped": skipped}
