# -*- coding: utf-8 -*-
"""G4.3: 设备级阈值覆盖服务

按 (device_id, metric_key) 解析生效阈值：
1. 查 device_metric_override（enabled=True）→ 用覆盖阈值
2. 否则用 monitor_metric_templates 的全局默认阈值

缓存：Redis key `monitor:threshold_override:{device_id}:{metric_key}` → JSON 阈值，TTL 300s。
"""
import json
from app.utils.logging import get_logger
from typing import Optional

logger = get_logger(__name__)

_CACHE_TTL = 300  # 5 分钟


def _get_redis():
    try:
        from app.services.switch_events import _get_redis
        return _get_redis()
    except Exception:
        logger.warning("threshold_override Redis 客户端获取失败，降级为无缓存", exc_info=True)
        return None


def _cache_key(device_id: int, metric_key: str) -> str:
    return f"monitor:threshold_override:{device_id}:{metric_key}"


def get_effective_threshold(
    device_id: int,
    metric_key: str,
    device_type: Optional[str] = None,
) -> Optional[dict]:
    """获取生效阈值（设备级覆盖优先，回退全局模板）。

    Args:
        device_id: 设备 ID
        metric_key: 指标标识
        device_type: 设备类型（用于查全局模板，可选）

    Returns:
        阈值 dict 或 None
    """
    r = _get_redis()
    ck = _cache_key(device_id, metric_key)
    if r is not None:
        try:
            cached = r.get(ck)
            if cached is not None:
                if cached == "__none__":
                    return None
                return json.loads(cached)
        except Exception:
            logger.warning("threshold_override 缓存读取失败 key=%s", ck, exc_info=True)

    threshold = None
    try:
        from app.persistence.device_metric_override_repository import DeviceMetricOverrideRepository
        from app.persistence.monitor_metric_template_repository import MonitorMetricTemplateRepository
        override_repo = DeviceMetricOverrideRepository()
        tpl_repo = MonitorMetricTemplateRepository()
        override = override_repo.find_enabled_by_device_metric(device_id, metric_key)
        if override:
            threshold = override.threshold
        else:
            tpl = tpl_repo.find_by_metric_key(metric_key, device_type=device_type)
            if tpl:
                threshold = tpl.threshold
    except Exception as exc:
        logger.warning("get_effective_threshold 失败: %s", exc)
        return None

    if r is not None:
        try:
            r.set(ck, "__none__" if threshold is None else json.dumps(threshold), ex=_CACHE_TTL)
        except Exception:
            logger.warning("threshold_override 缓存写入失败 key=%s", ck, exc_info=True)

    return threshold


def invalidate_cache(device_id: int, metric_key: Optional[str] = None):
    """失效缓存（覆盖变更时调用）"""
    r = _get_redis()
    if r is None:
        return
    try:
        if metric_key:
            r.delete(_cache_key(device_id, metric_key))
        else:
            prefix = f"monitor:threshold_override:{device_id}:"
            for key in r.scan_iter(match=f"{prefix}*", count=100):
                r.delete(key)
    except Exception:
        logger.warning("threshold_override 缓存失效失败 device_id=%s", device_id, exc_info=True)


def list_threshold_overrides(device_id: int = None, metric_key: str = None) -> list:
    """列出阈值覆盖（按 device_id/metric_key 过滤，序列化为 dict 列表）。

    P1-1：读路径下沉 service，路由层不再直访 repository。
    """
    from app.persistence.device_metric_override_repository import DeviceMetricOverrideRepository
    repo = DeviceMetricOverrideRepository()
    rows = repo.list_by_filters(device_id=device_id, metric_key=metric_key)
    return [r.to_dict() for r in rows]


def upsert(data: dict) -> dict:
    """upsert 阈值覆盖（I5：route handler 不再做完整 upsert）。"""
    from app.models.device_metric_override import DeviceMetricOverride
    from app.persistence.device_metric_override_repository import DeviceMetricOverrideRepository
    from app.exceptions.validation import ValidationError

    device_id = data.get("device_id")
    metric_key = data.get("metric_key")
    if not device_id or not metric_key:
        raise ValidationError("device_id / metric_key 必填")
    threshold = data.get("threshold")
    if threshold is None:
        raise ValidationError("threshold 必填")

    repo = DeviceMetricOverrideRepository()
    existing = repo.find_by_device_metric(device_id, metric_key)
    if existing:
        existing.threshold = threshold
        if "enabled" in data:
            existing.enabled = data["enabled"]
        if "note" in data:
            existing.note = data["note"]
    else:
        existing = DeviceMetricOverride(
            device_id=device_id,
            metric_key=metric_key,
            threshold=threshold,
            enabled=data.get("enabled", True),
            note=data.get("note"),
        )
        repo.add(existing)
    repo.flush()
    invalidate_cache(device_id, metric_key)
    return existing.to_dict()


def delete(override_id: int) -> dict:
    """删除阈值覆盖。"""
    from app.persistence.device_metric_override_repository import DeviceMetricOverrideRepository
    from app.exceptions.business import BusinessLogicError
    repo = DeviceMetricOverrideRepository()
    row = repo.find_by_id(override_id)
    if not row:
        raise BusinessLogicError("阈值覆盖不存在", status_code=404)
    device_id, metric_key = row.device_id, row.metric_key
    repo.delete(row)
    invalidate_cache(device_id, metric_key)
    return {"deleted": override_id}
