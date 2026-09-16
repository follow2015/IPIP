# -*- coding: utf-8 -*-
"""G4.1: 告警静默判定服务

判定一条告警是否被静默规则命中（不入箱、不推送）。

判定逻辑：
1. 查询 enabled=True 且 silence_from <= now <= silence_until 的规则
2. 规则 device_ids 为 null 或包含 device_id → 设备命中
3. 规则 alert_types 为 null 或包含 alert_type → 类型命中
4. 任一规则同时设备命中 + 类型命中 → 静默

缓存：Redis key `monitor:silence:active` 缓存活跃规则列表，TTL 60s。
**缓存项必须带上 `silence_from`/`silence_until`**：缓存存的是「写入时刻」的活跃集合，
TTL 内规则窗口可能自然到期，命中缓存后要用当前 `now` 重新过滤（见 `_in_window`）。
"""
import json
from app.utils.logging import get_logger
from app.utils.redis_client import get_redis_client
from datetime import datetime
from typing import List, Optional
from app.utils.time_utils import now_utc_naive

logger = get_logger(__name__)

_CACHE_KEY = "monitor:silence:active"
_CACHE_TTL = 60  # 秒


def _load_active_rules(now: datetime) -> List[dict]:
    """从 DB 加载当前活跃的静默规则（enabled + 时间窗口内）。

    返回项**含窗口字段**：它们会被一并写入 Redis 缓存，供命中缓存时用当前
    `now` 重新过滤（见 `_in_window`）。
    """
    from app.persistence.monitor_silence_rule_repository import MonitorSilenceRuleRepository
    repo = MonitorSilenceRuleRepository()
    rules = repo.find_active(now)
    return [
        {
            "id": r.id,
            "device_ids": r.device_ids,
            "alert_types": r.alert_types,
            "silence_from": _iso(r.silence_from),
            "silence_until": _iso(r.silence_until),
        }
        for r in rules
    ]


def _iso(dt) -> Optional[str]:
    """datetime → ISO 字符串（供 JSON 缓存）；None 原样返回。"""
    return dt.isoformat() if dt is not None else None


def _as_naive_utc(dt):
    """统一为 naive UTC，避免 aware/naive 混比抛 TypeError。"""
    if dt is None or dt.tzinfo is None:
        return dt
    from datetime import timezone
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _in_window(rule: dict, now: datetime) -> bool:
    """缓存中的规则在 `now` 时刻是否仍在静默窗口内。

    缓存存的是**写入时刻**的活跃集合，60s TTL 内窗口可能已自然到期——若不重过滤，
    窗口结束后的告警仍会被静默最多 60s（漏报）。规则增删改已由 `invalidate_cache()`
    覆盖，这里只补「窗口自然到期」这一种。

    兼容：老格式缓存项没有窗口字段（部署后 60s 内可能仍在）→ 保守按活跃处理。
    """
    start = _as_naive_utc(_parse_iso(rule.get("silence_from")))
    until = _as_naive_utc(_parse_iso(rule.get("silence_until")))
    if start is None or until is None:
        return True
    ts = _as_naive_utc(now)
    return start <= ts <= until


def _get_active_rules(now: datetime) -> List[dict]:
    """获取活跃规则（Redis 缓存 → DB 回源）。

    命中缓存时**必须用当前 `now` 重新过滤窗口**：缓存项是写入时刻的活跃集合，
    直接返回会让窗口已到期的规则继续静默最多 60s。
    """
    r = get_redis_client()
    if r is not None:
        try:
            cached = r.get(_CACHE_KEY)
            if cached:
                return [x for x in json.loads(cached) if _in_window(x, now)]
        except Exception:
            logger.warning("silence_service 缓存读取失败 key=%s", _CACHE_KEY, exc_info=True)

    rules = _load_active_rules(now)
    if r is not None:
        try:
            r.set(_CACHE_KEY, json.dumps(rules), ex=_CACHE_TTL)
        except Exception:
            logger.warning("silence_service 缓存写入失败 key=%s", _CACHE_KEY, exc_info=True)
    return rules


def is_silenced(device_id: int, alert_type: str,
                now: Optional[datetime] = None) -> bool:
    """判定告警是否被静默。

    Args:
        device_id: 设备 ID
        alert_type: 告警类型
        now: 当前时间（测试注入），默认 utcnow

    Returns:
        True 表示静默（不入箱），False 表示放行
    """
    ts = now if now is not None else now_utc_naive()
    try:
        rules = _get_active_rules(ts)
        for rule in rules:
            device_ids = rule.get("device_ids")
            if device_ids and device_id not in device_ids:
                continue
            alert_types = rule.get("alert_types")
            if alert_types and alert_type not in alert_types:
                continue
            return True
        return False
    except Exception as exc:
        logger.warning("silence_service.is_silenced 失败: %s", exc)
        return False


def invalidate_cache():
    """失效静默规则缓存（规则变更时调用）"""
    r = get_redis_client()
    if r is not None:
        try:
            r.delete(_CACHE_KEY)
        except Exception:
            logger.warning("silence_service 缓存失效失败 key=%s", _CACHE_KEY, exc_info=True)


def list_silence_rules() -> list:
    """列出全部静默规则（序列化为 dict 列表，供路由层直接返回）。

    P1-1：读路径下沉 service，路由层不再直访 repository。
    """
    from app.persistence.monitor_silence_rule_repository import MonitorSilenceRuleRepository
    repo = MonitorSilenceRuleRepository()
    return [r.to_dict() for r in repo.list_all()]


def create_rule(data: dict, user_id: int = None) -> dict:
    """创建静默规则（I4：route handler 不再构造 Model + 调 repo）。

    data: {name, device_ids, alert_types, silence_from, silence_until, reason, enabled}
    返回新建规则的 to_dict()。
    """
    from datetime import datetime as _dt
    from app.models.monitor_silence_rule import MonitorSilenceRule
    from app.persistence.monitor_silence_rule_repository import MonitorSilenceRuleRepository
    from app.exceptions.validation import ValidationError

    name = data.get("name")
    if not name:
        raise ValidationError("name 必填")
    silence_from = _parse_iso(data.get("silence_from"))
    silence_until = _parse_iso(data.get("silence_until"))
    if not silence_from or not silence_until:
        raise ValidationError("silence_from / silence_until 必须为合法 ISO datetime")

    repo = MonitorSilenceRuleRepository()
    rule = MonitorSilenceRule(
        name=name,
        device_ids=data.get("device_ids"),
        alert_types=data.get("alert_types"),
        silence_from=silence_from,
        silence_until=silence_until,
        reason=data.get("reason"),
        created_by=str(user_id or ""),
        enabled=data.get("enabled", True),
    )
    repo.add(rule)
    repo.flush()
    invalidate_cache()
    return rule.to_dict()


def update_rule(rule_id: int, data: dict) -> dict:
    """更新静默规则。"""
    from app.persistence.monitor_silence_rule_repository import MonitorSilenceRuleRepository
    from app.exceptions.business import BusinessLogicError
    repo = MonitorSilenceRuleRepository()
    rule = repo.find_by_id(rule_id)
    if not rule:
        raise BusinessLogicError("静默规则不存在", status_code=404)
    for k in ("name", "device_ids", "alert_types", "reason", "enabled"):
        if k in data:
            setattr(rule, k, data[k])
    if "silence_from" in data:
        v = _parse_iso(data["silence_from"])
        if v:
            rule.silence_from = v
    if "silence_until" in data:
        v = _parse_iso(data["silence_until"])
        if v:
            rule.silence_until = v
    repo.flush()
    invalidate_cache()
    return rule.to_dict()


def delete_rule(rule_id: int) -> dict:
    """删除静默规则。"""
    from app.persistence.monitor_silence_rule_repository import MonitorSilenceRuleRepository
    from app.exceptions.business import BusinessLogicError
    repo = MonitorSilenceRuleRepository()
    rule = repo.find_by_id(rule_id)
    if not rule:
        raise BusinessLogicError("静默规则不存在", status_code=404)
    repo.delete(rule)
    invalidate_cache()
    return {"deleted": rule_id}


def _parse_iso(s: str):
    """解析 ISO datetime 字符串，失败返回 None。"""
    if not s:
        return None
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
