# -*- coding: utf-8 -*-
"""P2-17: 告警依赖抑制判定服务

当上游设备已有 active 告警（未关闭）时，抑制下游设备的同类型告警，
避免网络抖动时下游设备大量告警淹没根因。

抑制来源（按优先级）：
1. 手动规则（monitor_alert_dependency_rule）：运维显式配置的依赖关系
2. 自动拓扑推断（DeviceServerExt.parent_device_id）：子设备的父设备 active 告警时抑制子设备

判定逻辑：
- 查下游设备的所有上游（手动规则 + 拓扑父设备）
- 任一上游有同 alert_type 的 active 告警（closed_at IS NULL）→ 抑制
- alert_types 为 null 的规则匹配全部告警类型
- fail-open：判定失败不阻断告警

缓存：Redis key `monitor:dep_rules:active` 缓存启用的手动规则列表，TTL 60s。
"""
import json
from app.utils.logging import get_logger
from typing import List, Optional, Tuple

logger = get_logger(__name__)

_CACHE_KEY = "monitor:dep_rules:active"
_CACHE_TTL = 60


def _get_redis():
    from app.services.switch_events import _get_redis
    return _get_redis()


def _load_active_rules() -> List[dict]:
    from app.models.monitor_alert_dependency_rule import MonitorAlertDependencyRule
    from extensions import db
    all_rules = (
        db.session.query(MonitorAlertDependencyRule)
        .filter_by(enabled=True)
        .all()
    )
    return [
        {
            "id": r.id,
            "upstream_device_id": r.upstream_device_id,
            "downstream_device_id": r.downstream_device_id,
            "alert_types": r.alert_types,
        }
        for r in all_rules
    ]


def _get_active_rules() -> List[dict]:
    r = _get_redis()
    if r is not None:
        try:
            cached = r.get(_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            logger.warning("dep_service 缓存读取失败 key=%s", _CACHE_KEY, exc_info=True)

    rules = _load_active_rules()
    if r is not None:
        try:
            r.set(_CACHE_KEY, json.dumps(rules), ex=_CACHE_TTL)
        except Exception:
            logger.warning("dep_service 缓存写入失败 key=%s", _CACHE_KEY, exc_info=True)
    return rules


def invalidate_cache():
    r = _get_redis()
    if r is not None:
        try:
            r.delete(_CACHE_KEY)
        except Exception:
            logger.warning("dep_service 缓存失效失败 key=%s", _CACHE_KEY, exc_info=True)


def _upstream_has_active_alert(upstream_device_id: int, alert_type: str) -> bool:
    from app.models.monitor_alert_outbox import MonitorAlertOutbox
    from extensions import db
    q = (
        db.session.query(MonitorAlertOutbox.id)
        .filter(
            MonitorAlertOutbox.device_id == upstream_device_id,
            MonitorAlertOutbox.alert_type == alert_type,
            MonitorAlertOutbox.closed_at.is_(None),
        )
        .limit(1)
    )
    return q.first() is not None


def is_suppressed_by_dependency(
    device_id: int,
    alert_type: str,
) -> Tuple[bool, str]:
    try:
        rules = _get_active_rules()
        for rule in rules:
            if rule["downstream_device_id"] != device_id:
                continue
            types = rule.get("alert_types")
            if types and alert_type not in types:
                continue
            if _upstream_has_active_alert(rule["upstream_device_id"], alert_type):
                return True, f"manual rule #{rule['id']}: upstream device {rule['upstream_device_id']} has active alert"

        from app.models.device_server_ext import DeviceServerExt
        from extensions import db
        ext = db.session.get(DeviceServerExt, device_id)
        if ext is not None and ext.parent_device_id is not None:
            if _upstream_has_active_alert(ext.parent_device_id, alert_type):
                return True, f"topology: parent device {ext.parent_device_id} has active alert"

        return False, ""
    except Exception as exc:
        logger.warning("is_suppressed_by_dependency 失败（fail-open 放行）: %s", exc, exc_info=True)
        return False, ""


def list_rules() -> list:
    from app.persistence.monitor_alert_dependency_rule_repository import (
        MonitorAlertDependencyRuleRepository,
    )
    repo = MonitorAlertDependencyRuleRepository()
    return [r.to_dict() for r in repo.list_all()]


def create_rule(data: dict) -> dict:
    from app.models.monitor_alert_dependency_rule import MonitorAlertDependencyRule
    from app.persistence.monitor_alert_dependency_rule_repository import (
        MonitorAlertDependencyRuleRepository,
    )
    from app.exceptions.validation import ValidationError

    name = data.get("name")
    if not name:
        raise ValidationError("name 必填")
    upstream = data.get("upstream_device_id")
    downstream = data.get("downstream_device_id")
    if not upstream or not downstream:
        raise ValidationError("upstream_device_id / downstream_device_id 必填")
    if upstream == downstream:
        raise ValidationError("上游与下游设备不能相同")

    repo = MonitorAlertDependencyRuleRepository()
    rule = MonitorAlertDependencyRule(
        name=name,
        upstream_device_id=upstream,
        downstream_device_id=downstream,
        alert_types=data.get("alert_types"),
        reason=data.get("reason"),
        enabled=data.get("enabled", True),
    )
    repo.add(rule)
    repo.flush()
    invalidate_cache()
    return rule.to_dict()


def update_rule(rule_id: int, data: dict) -> dict:
    from app.persistence.monitor_alert_dependency_rule_repository import (
        MonitorAlertDependencyRuleRepository,
    )
    from app.exceptions.business import BusinessLogicError
    repo = MonitorAlertDependencyRuleRepository()
    rule = repo.find_by_id(rule_id)
    if not rule:
        raise BusinessLogicError("依赖规则不存在", status_code=404)
    for k in ("name", "alert_types", "reason", "enabled"):
        if k in data:
            setattr(rule, k, data[k])
    if "upstream_device_id" in data:
        rule.upstream_device_id = data["upstream_device_id"]
    if "downstream_device_id" in data:
        rule.downstream_device_id = data["downstream_device_id"]
    if rule.upstream_device_id == rule.downstream_device_id:
        raise BusinessLogicError("上游与下游设备不能相同")
    repo.flush()
    invalidate_cache()
    return rule.to_dict()


def delete_rule(rule_id: int) -> dict:
    from app.persistence.monitor_alert_dependency_rule_repository import (
        MonitorAlertDependencyRuleRepository,
    )
    from app.exceptions.business import BusinessLogicError
    repo = MonitorAlertDependencyRuleRepository()
    rule = repo.find_by_id(rule_id)
    if not rule:
        raise BusinessLogicError("依赖规则不存在", status_code=404)
    repo.delete(rule)
    invalidate_cache()
    return {"deleted": rule_id}
