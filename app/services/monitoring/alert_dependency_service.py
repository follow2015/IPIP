# -*- coding: utf-8 -*-
"""P2-17: 告警依赖抑制判定服务

当上游设备已有 active 告警（未关闭）时，抑制下游设备的同类型告警，
避免网络抖动时下游设备大量告警淹没根因。

抑制来源（按优先级）：
1. 手动规则（monitor_alert_dependency_rule）：运维显式配置的依赖关系
2. 自动拓扑推断（DeviceServerExt.parent_device_id）：子设备的父设备 active 告警时抑制子设备

判定逻辑：
- 查下游设备的所有上游（手动规则 + 拓扑父设备）
- 任一上游有同 alert_type 的 active 告警 → 抑制。active 判据 =
  `closed_at IS NULL`（未闭合）**且**未超过「最大存活时长」
  （`MONITOR_DEP_UPSTREAM_ALERT_MAX_AGE`，默认 7 天）——两项缺一不可：
  闭合由 `monitor_service` 在恢复时写入（○9 修复前从不写，导致抑制永久化），
  存活上限则是历史遗留行的兜底
- alert_types 为 null 的规则匹配全部告警类型
- fail-open：判定失败不阻断告警

事件聚合（Incident）适配：
被抑制的告警不入 outbox、零留痕，会导致事件无法统计「这起事故影响了
多少台设备」。故 check_dependency 返回结构化的 upstream_device_id，
调用方据此写入留痕表（见 monitor_suppressed_alert_log），使 L2 拓扑
聚合能还原影响面。

缓存：Redis key `monitor:dep_rules:active` 缓存启用的手动规则列表，TTL 60s。
"""
import json
from app.utils.logging import get_logger
from app.utils.redis_client import get_redis_client
from typing import List, Optional, Tuple, TypedDict

logger = get_logger(__name__)

_CACHE_KEY = "monitor:dep_rules:active"
_CACHE_TTL = 60  # 秒


class DependencyDecision(TypedDict):
    """依赖抑制判定结果"""
    suppressed: bool
    """抑制原因（人读），未抑制时为空字符串"""
    reason: str
    """命中的上游设备 ID（未抑制时为 None）。

    事件聚合的 L2 拓扑聚合与影响面统计依赖此字段 —— 没有它，被抑制的
    下游告警无法归属到根因事件。
    """
    upstream_device_id: Optional[int]
    """抑制来源：manual_rule / topology / 空字符串（未抑制）"""
    source: str




def _load_active_rules() -> List[dict]:
    """从 DB 加载启用的手动依赖规则"""
    from app.persistence.monitor_alert_dependency_rule_repository import (
        MonitorAlertDependencyRuleRepository,
    )

    all_rules = MonitorAlertDependencyRuleRepository().list_enabled()
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
    """获取启用的手动规则（Redis 缓存 → DB 回源）"""
    r = get_redis_client()
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
    """失效依赖规则缓存（规则变更时调用）"""
    r = get_redis_client()
    if r is not None:
        try:
            r.delete(_CACHE_KEY)
        except Exception:
            logger.warning("dep_service 缓存失效失败 key=%s", _CACHE_KEY, exc_info=True)




_UPSTREAM_ALERT_MAX_AGE_SECONDS = 7 * 24 * 3600


def _upstream_alert_max_age_seconds() -> int:
    """读取上游告警最大存活时长配置（非法/缺失回退默认 7 天）。"""
    raw = _UPSTREAM_ALERT_MAX_AGE_SECONDS
    try:
        from flask import current_app
        raw = current_app.config.get(
            "MONITOR_DEP_UPSTREAM_ALERT_MAX_AGE", _UPSTREAM_ALERT_MAX_AGE_SECONDS
        )
    except Exception:  # noqa: BLE001 - 无 app 上下文或配置缺失时沿用模块默认值
        pass
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _UPSTREAM_ALERT_MAX_AGE_SECONDS
    return value if value > 0 else _UPSTREAM_ALERT_MAX_AGE_SECONDS


def _upstream_has_active_alert(upstream_device_id: int, alert_type: str) -> bool:
    """查询上游设备是否有指定类型的 active 告警。

    active 判据 = `closed_at IS NULL`（未闭合）**且** `created_at` 未超过
    「最大存活时长」（见 `_UPSTREAM_ALERT_MAX_AGE_SECONDS`）。
    """
    from datetime import timedelta

    from app.persistence.monitor_alert_outbox_repository import (
        MonitorAlertOutboxRepository,
    )
    from app.utils.time_utils import now_utc_naive

    cutoff = now_utc_naive() - timedelta(seconds=_upstream_alert_max_age_seconds())
    return MonitorAlertOutboxRepository().exists_recent_open(
        upstream_device_id, alert_type, cutoff,
    )




def _get_parent_device_id(device_id: int) -> Optional[int]:
    """取设备的拓扑父设备 ID（DeviceServerExt.parent_device_id）。

    独立成函数便于测试替身注入，避免测试必须 mock db.session.get 的
    内部调用细节。
    """
    from app.models.device_server_ext import DeviceServerExt
    from extensions import db
    ext = db.session.get(DeviceServerExt, device_id)
    if ext is None:
        return None
    return ext.parent_device_id


def check_dependency(device_id: int, alert_type: str) -> DependencyDecision:
    """判定告警是否被依赖关系抑制，并返回结构化上游信息。

    相比 is_suppressed_by_dependency 增加了 upstream_device_id 与 source，
    供事件聚合把被抑制的下游告警归属到根因事件、统计影响面。

    Args:
        device_id: 下游设备 ID（待判定告警的设备）
        alert_type: 告警类型

    Returns:
        DependencyDecision：见类型定义。判定异常时 fail-open 放行
        （suppressed=False），不因依赖服务故障丢弃告警。
    """
    try:
        rules = _get_active_rules()
        for rule in rules:
            if rule["downstream_device_id"] != device_id:
                continue
            types = rule.get("alert_types")
            if types and alert_type not in types:
                continue
            upstream = rule["upstream_device_id"]
            if _upstream_has_active_alert(upstream, alert_type):
                return DependencyDecision(
                    suppressed=True,
                    reason=f"manual rule #{rule['id']}: upstream device {upstream} has active alert",
                    upstream_device_id=upstream,
                    source="manual_rule",
                )

        parent = _get_parent_device_id(device_id)
        if parent is not None and _upstream_has_active_alert(parent, alert_type):
            return DependencyDecision(
                suppressed=True,
                reason=f"topology: parent device {parent} has active alert",
                upstream_device_id=parent,
                source="topology",
            )

        return DependencyDecision(
            suppressed=False, reason="", upstream_device_id=None, source=""
        )
    except Exception as exc:
        logger.warning("check_dependency 失败（fail-open 放行）: %s", exc, exc_info=True)
        return DependencyDecision(
            suppressed=False, reason="", upstream_device_id=None, source=""
        )


def is_suppressed_by_dependency(
    device_id: int,
    alert_type: str,
) -> Tuple[bool, str]:
    """兼容旧调用方：仅返回 (suppressed, reason)。

    新代码请用 check_dependency 以获取 upstream_device_id。
    """
    d = check_dependency(device_id, alert_type)
    return d["suppressed"], d["reason"]




def list_rules() -> list:
    """列出全部依赖规则（序列化为 dict 列表）"""
    from app.persistence.monitor_alert_dependency_rule_repository import (
        MonitorAlertDependencyRuleRepository,
    )
    repo = MonitorAlertDependencyRuleRepository()
    return [r.to_dict() for r in repo.list_all()]


def create_rule(data: dict) -> dict:
    """创建依赖规则"""
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
    """更新依赖规则"""
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
    """删除依赖规则"""
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
