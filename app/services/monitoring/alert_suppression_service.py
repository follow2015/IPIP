# -*- coding: utf-8 -*-
"""
G13: 告警风暴抑制服务

针对同一 dedup_key 在滑动窗口内的高频重复告警进行限频，避免指标抖动放大为
告警风暴，冲击 Redis Pub/Sub、outbox 表与前端 SSE 通道。

判定逻辑（Redis 滑动窗口计数）：
1. 以 `monitor:suppress:{dedup_key}` 为 Redis key，value 为 JSON：
   {"count": N, "window_start": ts, "last_alert_at": ts}
2. 收到告警时：
   - 若 now - window_start > WINDOW → 重置窗口，count=1，允许通过
   - 若 count < MAX → count+=1，允许通过
   - 若 count >= MAX → 抑制（不通过），更新 last_alert_at
3. 抑制后的降频通知：距 last_alert_at >= THROTTLE 时，放行一条聚合告警
   （含累计 count），重置窗口

Feature Flag：MONITOR_SUPPRESSION_ENABLED=false 时全部放行（瞬时回退）。

性能：单次判定 1 次 Redis GET + 1 次 SET，命中时 < 5ms（见 §5.2.1）。
"""
import json
from app.utils.logging import get_logger
import time
from typing import Optional, TypedDict

logger = get_logger(__name__)


class SuppressionDecision(TypedDict):
    """抑制判定结果"""
    suppressed: bool
    """是否为聚合告警（抑制窗口内累计后放行的一条）"""
    aggregated: bool
    """累计被抑制的告警数（聚合时返回，非聚合为 0）"""
    suppressed_count: int
    """下次允许放行的时间戳（被抑制时返回）"""
    next_allowed_at: Optional[float]


def _get_redis():
    """复用 switch_events 的 Redis 客户端（懒加载单例）"""
    from app.services.switch_events import _get_redis as _get
    return _get()


def _load_config():
    """从 Flask config 读取抑制参数（支持 current_app 与 get_config 双路径）"""
    try:
        from flask import current_app
        cfg = current_app.config
        return (
            cfg.get("MONITOR_SUPPRESSION_ENABLED", True),
            int(cfg.get("MONITOR_SUPPRESSION_WINDOW", 60)),
            int(cfg.get("MONITOR_SUPPRESSION_MAX", 5)),
            int(cfg.get("MONITOR_SUPPRESSION_THROTTLE", 300)),
        )
    except Exception:
        from config import get_config
        _c = get_config()
        ci = _c() if isinstance(_c, type) else _c
        return (
            getattr(ci, "MONITOR_SUPPRESSION_ENABLED", True),
            int(getattr(ci, "MONITOR_SUPPRESSION_WINDOW", 60)),
            int(getattr(ci, "MONITOR_SUPPRESSION_MAX", 5)),
            int(getattr(ci, "MONITOR_SUPPRESSION_THROTTLE", 300)),
        )


def should_emit(dedup_key: str, now: Optional[float] = None) -> SuppressionDecision:
    """判定一条告警是否应放行。

    Args:
        dedup_key: 告警去重键（同 key 在窗口内限频）
        now: 当前时间戳（测试注入），默认 time.time()

    Returns:
        SuppressionDecision: suppressed=False 表示放行；True 表示抑制。
        aggregated=True 表示这是抑制窗口累计后放行的聚合告警。
    """
    enabled, window, max_count, throttle = _load_config()
    if not enabled:
        return SuppressionDecision(
            suppressed=False, aggregated=False, suppressed_count=0, next_allowed_at=None
        )

    if not dedup_key:
        return SuppressionDecision(
            suppressed=False, aggregated=False, suppressed_count=0, next_allowed_at=None
        )

    r = _get_redis()
    if r is None:
        return SuppressionDecision(
            suppressed=False, aggregated=False, suppressed_count=0, next_allowed_at=None
        )

    ts = now if now is not None else time.time()
    key = f"monitor:suppress:{dedup_key}"

    try:
        raw = r.get(key)
    except Exception as exc:
        logger.warning("alert_suppression Redis GET 失败，放行: %s", exc)
        return SuppressionDecision(
            suppressed=False, aggregated=False, suppressed_count=0, next_allowed_at=None
        )

    if raw:
        try:
            state = json.loads(raw)
            count = int(state.get("count", 0))
            window_start = float(state.get("window_start", ts))
            last_alert_at = float(state.get("last_alert_at", ts))
        except (json.JSONDecodeError, ValueError, TypeError):
            count, window_start, last_alert_at = 0, ts, ts
    else:
        count, window_start, last_alert_at = 0, ts, ts

    if ts - window_start > window:
        count = 0
        window_start = ts

    if count >= max_count and (ts - last_alert_at) >= throttle:
        suppressed_count = count - max_count  # 累计被抑制数
        new_state = json.dumps({
            "count": 1, "window_start": ts, "last_alert_at": ts,
        })
        try:
            r.set(key, new_state, ex=window + throttle)
        except Exception as exc:
            logger.warning("alert_suppression Redis SET 失败（聚合放行）: %s", exc)
        return SuppressionDecision(
            suppressed=False, aggregated=True,
            suppressed_count=suppressed_count, next_allowed_at=None,
        )

    if count >= max_count:
        next_allowed = last_alert_at + throttle
        return SuppressionDecision(
            suppressed=True, aggregated=False,
            suppressed_count=0, next_allowed_at=next_allowed,
        )

    new_count = count + 1
    new_state = json.dumps({
        "count": new_count, "window_start": window_start, "last_alert_at": ts,
    })
    try:
        r.set(key, new_state, ex=window + throttle)
    except Exception as exc:
        logger.warning("alert_suppression Redis SET 失败（放行）: %s", exc)
    return SuppressionDecision(
        suppressed=False, aggregated=False, suppressed_count=0, next_allowed_at=None,
    )
