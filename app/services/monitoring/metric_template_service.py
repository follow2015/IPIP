# -*- coding: utf-8 -*-
"""指标模板服务（MetricTemplateService）

P1-1：读路径下沉 service，路由层不再直访 repository。
"""
from typing import List

from app.persistence.monitor_metric_template_repository import MonitorMetricTemplateRepository


_repo = MonitorMetricTemplateRepository()


def list_metric_templates() -> List[dict]:
    rows = _repo.list_all()
    return [t.to_dict(exclude=['created_at', 'updated_at']) for t in rows]


def upsert(data: dict) -> dict:
    tpl = _repo.upsert(
        device_type=data["device_type"],
        metric_key=data["metric_key"],
        source=data.get("source", "snmp"),
        vendor=data.get("vendor"),
        category=data.get("category"),
        display_name=data.get("display_name"),
        mib=data.get("mib"),
        oid_symbol=data.get("oid_symbol"),
        oid=data.get("oid"),
        zabbix_item_key=data.get("zabbix_item_key"),
        index_kind=data.get("index_kind"),
        metric_type=data.get("metric_type", "gauge"),
        unit=data.get("unit"),
        poll_interval=data.get("poll_interval", 60),
        threshold=data.get("threshold"),
        severity_default=data.get("severity_default"),
        enabled=data.get("enabled", True),
        description=data.get("description"),
        runbook_url=data.get("runbook_url"),
        runbook_title=data.get("runbook_title"),
    )
    return {"id": tpl.id, "metric_key": data["metric_key"], "device_type": data["device_type"]}


def seed_defaults() -> int:
    return _repo.seed_defaults()


def delete(template_id: int) -> dict:
    from app.exceptions.business import BusinessLogicError
    ok = _repo.delete(template_id)
    if not ok:
        raise BusinessLogicError("指标模板不存在", status_code=404)
    return {"deleted": template_id}


def batch_delete(ids: list) -> dict:
    deleted = _repo.batch_delete(ids)
    return {"deleted": deleted, "total": len(ids)}


def batch_set_enabled(ids: list, enabled: bool) -> dict:
    updated = _repo.batch_set_enabled(ids, enabled)
    return {"updated": updated, "total": len(ids), "enabled": enabled}
