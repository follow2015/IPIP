# -*- coding: utf-8 -*-
"""告警统一治理门面（AlertIngress）—— P1-2：统一两条入箱路径的治理逻辑

背景：监控告警存在两条入箱路径：
1. ``MonitorService._enqueue_alert``（连通性告警）—— 已内置静默（G4.1）/风暴抑制（G13）/
   SSE publish（G1，含 target_user_ids 权限过滤）；
2. ``MetricAlertService._enqueue``（指标告警）—— 原先**裸入箱**，未走任何治理。

本模块把「治理判定 + SSE 发布」抽成可复用函数，供两条路径共用，确保
指标告警与连通性告警获得一致的静默、抑制与权限过滤，避免越权/告警风暴。

约定：
- 本模块只做「判定 + 发布」副作用（Redis/SSE），**不落库** outbox；
  落库仍由调用方（各 Service 的 Repository/Model）完成。
- 治理判定失败一律 fail-open（放行），避免 Redis/DB 故障导致告警全丢。
- SSE publish 失败不影响 outbox 落库。
"""
import json
from datetime import datetime, timedelta, timezone

from app.utils.logging import get_logger
from app.utils.time_utils import now_utc_naive
from typing import Optional, Tuple

logger = get_logger(__name__)


_MAINT_CACHE_TTL = 60  # 秒；维护态变更时主动失效


def _get_redis():
    """惰性获取 Redis 客户端（失败返回 None，走降级直查 DB）。"""
    try:
        from app.services.monitoring.monitor_worker import _redis_client
        from flask import current_app
        return _redis_client(current_app._get_current_object())
    except Exception:
        return None


def _maint_cache_key(device_id: int) -> str:
    return f"monitor:maint:{device_id}"


def invalidate_maintenance_cache(device_id: int) -> None:
    """设备状态变更时主动失效维护态缓存（供 device_service 调用）。"""
    r = _get_redis()
    if r is not None:
        try:
            r.delete(_maint_cache_key(device_id))
        except Exception:
            logger.warning("维护态缓存失效失败 device=%s", device_id, exc_info=True)


def _is_maintenance_cached(device_id: int) -> Optional[bool]:
    """查缓存返回维护态；未命中返回 None（需回源 DB）。"""
    r = _get_redis()
    if r is None:
        return None
    try:
        val = r.get(_maint_cache_key(device_id))
        if val is None:
            return None
        return val == "1"
    except Exception:
        logger.warning("维护态缓存读取失败 device=%s", device_id, exc_info=True)
        return None


def _set_maintenance_cache(device_id: int, is_maint: bool) -> None:
    """回填维护态缓存。"""
    r = _get_redis()
    if r is None:
        return
    try:
        r.set(_maint_cache_key(device_id), "1" if is_maint else "0", ex=_MAINT_CACHE_TTL)
    except Exception:
        logger.warning("维护态缓存写入失败 device=%s", device_id, exc_info=True)


def governance_should_emit(
    device_id: int,
    alert_type: str,
    idempotency_key: str,
    now: Optional[float] = None,
    severity: str = "warning",
    skip_maintenance_cache: bool = False,
) -> Tuple[bool, bool, int]:
    """统一告警治理判定：静默检查（G4.1）+ 风暴抑制（G13）。

    Args:
        device_id: 设备 ID
        alert_type: 告警类型（字符串）
        idempotency_key: 告警幂等/去重键（供风暴抑制窗口计数）
        now: 当前时间戳（测试注入）
        severity: 告警严重级别（被依赖抑制时写入留痕表需要）
        skip_maintenance_cache: 跳过维护态 Redis 缓存判定。调用方已用内存
            device 对象判过维护态时传 True，避免缓存 stale 误静默（如
            monitor_service 路径已有 device.status，且测试场景下缓存可能
            跨用例污染）。

    Returns:
        (should_emit, aggregated, suppressed_count):
        - should_emit=False：命中静默或被抑制，调用方应**不**入箱；
        - should_emit=True：放行；
        - aggregated=True：这是抑制窗口累计后放行的一条聚合告警（应标注 suppressed_count）；
        - suppressed_count：聚合时累计被抑制的告警数。
    """
    if not skip_maintenance_cache:
        try:
            from app.core.enums import DeviceStatus

            cached = _is_maintenance_cached(device_id)
            if cached is True:
                logger.info(
                    "设备维护中（缓存命中），告警静默 device=%s alert_type=%s", device_id, alert_type
                )
                return False, False, 0
            if cached is None:
                from app.models.device import Device
                from extensions import db
                device = db.session.get(Device, device_id)
                is_maint = device is not None and device.status == DeviceStatus.MAINTENANCE
                _set_maintenance_cache(device_id, is_maint)
                if is_maint:
                    logger.info(
                        "设备维护中，告警静默 device=%s alert_type=%s", device_id, alert_type
                    )
                    return False, False, 0
        except Exception:
            logger.warning("维护模式判定失败（fail-open 不阻断）", exc_info=True)

    try:
        from app.services.monitoring.silence_service import is_silenced
        if is_silenced(device_id, alert_type):
            logger.info(
                "告警被静默规则命中 device=%s alert_type=%s", device_id, alert_type
            )
            return False, False, 0
    except Exception:
        logger.warning("告警抑制判定失败（fail-open 不阻断）", exc_info=True)

    try:
        from app.services.monitoring.alert_dependency_service import check_dependency
        decision = check_dependency(device_id, alert_type)
        if decision["suppressed"]:
            logger.info(
                "告警被依赖抑制 device=%s alert_type=%s reason=%s",
                device_id, alert_type, decision["reason"],
            )
            try:
                from app.persistence.monitor_suppressed_alert_log_repository import (
                    SuppressedAlertLogRepository,
                )
                SuppressedAlertLogRepository().add(
                    device_id=device_id,
                    alert_type=alert_type,
                    severity=severity,
                    reason_code=("L2_topology" if decision["source"] == "topology"
                                 else "L2_manual_rule"),
                    upstream_device_id=decision["upstream_device_id"],
                )
                try:
                    from app.services.monitoring.incident_aggregator import (
                        attach_suppressed_to_incident,
                    )
                    attach_suppressed_to_incident(
                        decision["upstream_device_id"], alert_type,
                    )
                except Exception:
                    logger.warning("L2 拓扑聚合调用失败（不阻断）device=%s",
                                   device_id, exc_info=True)
            except Exception:
                logger.warning("依赖抑制留痕失败（不阻断治理）device=%s",
                               device_id, exc_info=True)
            return False, False, 0
    except Exception:
        logger.warning("告警依赖抑制判定失败（fail-open 不阻断）", exc_info=True)

    try:
        from app.services.monitoring.alert_suppression_service import should_emit
        decision = should_emit(idempotency_key, now=now)
        if decision["suppressed"]:
            logger.info(
                "告警被风暴抑制 device=%s alert_type=%s dedup_key=%s next_allowed_at=%s",
                device_id, alert_type, idempotency_key,
                decision.get("next_allowed_at"),
            )
            return False, False, 0
        if decision["aggregated"]:
            return True, True, int(decision.get("suppressed_count", 0))
    except Exception:
        logger.warning("告警抑制判定失败（fail-open 不阻断）", exc_info=True)

    return True, False, 0


def publish_monitor_alert_event(
    device_id: int,
    alert_type: str,
    severity: str,
    idempotency_key: str,
    outbox_id: int,
    payload: dict,
    target_user_ids=None,
) -> None:
    """G1: 入箱后 best-effort publish 到 Redis global channel，驱动 SSE 实时推送。

    target_user_ids 由 data_scope_service 按设备可见用户反查（多用户隔离）；
    为 None 视为全局广播。publish 失败不影响 outbox 落库与后续投递。
    """
    try:
        from app.utils.time_utils import now_iso_utc
        from app.services.monitoring.data_scope_service import (
            get_users_with_device_access,
        )
        from app.services.switch_events import _redis_publish_global

        if target_user_ids is None:
            target_user_ids = get_users_with_device_access(device_id)

        alert_type_str = getattr(alert_type, "value", alert_type)
        _redis_publish_global(json.dumps({
            "event_type": "monitor_alert",
            "device_id": device_id,
            "alert_type": alert_type_str,
            "severity": severity,
            "dedup_key": idempotency_key,
            "outbox_id": outbox_id,
            "timestamp": now_iso_utc(),
            "target_user_ids": target_user_ids if target_user_ids else None,
            "payload": payload,
        }, ensure_ascii=False))
    except Exception:
        logger.warning(
            "SSE 监控告警推送失败 device=%s alert_type=%s",
            device_id, alert_type, exc_info=True,
        )




def build_dedup_key(
    alert_type: str,
    device_id: int,
    metric_key: Optional[str] = None,
    index: Optional[str] = None,
    action: Optional[str] = None,
) -> str:
    """统一构造告警去重/幂等键。

    规范格式：``{alert_type}:{device_id}:{metric_key}:{index}:{action}``

    - 指标告警：metric_key/index/action=raise|recover 全填
    - 连通性告警：metric_key 留空，action=raise|recover，index 可放 episode 等扩展
    - 各段为 None 时归一化为空字符串，保证段数恒为 5，便于解析与 LIKE 过滤

    所有告警入箱路径（MetricAlertService / MonitorService）必须经此函数生成 dedup_key，
    禁止各处自行 f-string 拼接，避免格式漂移导致去重失效或过滤错位。
    """
    return ":".join([
        str(alert_type) if alert_type is not None else "",
        str(device_id) if device_id is not None else "",
        str(metric_key) if metric_key is not None else "",
        str(index) if index is not None else "",
        str(action) if action is not None else "",
    ])



_EPOCH = datetime(1970, 1, 1)


def build_notification_key(
    dedup_key: str,
    now: Optional[datetime] = None,
    *,
    bucket_seconds: int = 0,
) -> str:
    """由稳态去重键派生「带幕次」的通知幂等键：``{dedup_key}#{幕次令牌}``。

    幕次令牌是告警**发生时刻**的紧凑表示（naive UTC，``YYYYmmddTHHMMSS``）。

    Args:
        dedup_key: ``build_dedup_key`` 产出的稳态键（不携带幕次）
        now: 告警时刻（naive UTC）。缺省取 ``now_utc_naive()``；
            tz-aware 入参统一折算为 UTC 再去掉 tzinfo，避免不同时区进程
            产生不同令牌。
        bucket_seconds: 幕次时间桶大小（秒）。``0``（默认）= 不设桶，幕次即
            秒级时刻——适用于**去重完全由状态机驱动**的指标告警（同幕次内
            不会再产生过渡，故秒级已足以区分两幕）。``>0`` = 把时刻对齐到该
            秒数的桶——适用于 trap 这类**按节流窗口去重**的告警：同一节流
            窗口内（含聚合放行的那一条）必须复用同一幂等键，否则"节流"
            反被拆成刷屏；跨窗口才允许再次通知。

    为什么追加在末尾且用 ``#`` 分隔：``dedup_key`` 的 5 段契约（供
    ``parse_dedup_key`` 与 ``dedup_key LIKE '%:段:%'`` 过滤）保持完好——每段
    后仍是冒号，第 5 段仅多出 ``#`` 后缀，且该后缀**只出现在通知幂等键上**，
    不出现在 outbox 行的 `dedup_key` 里。

    注意：秒级幕次依赖「同一 (device, metric, index) 的两幕之间至少相隔一个
    轮询周期」（指标告警的过渡由状态机按轮次产生，不会同秒连发）。若极端情况下
    同秒复用同一幕次，退化为**去重**（少发一条）而非丢失——是安全方向。
    """
    ts = now if now is not None else now_utc_naive()
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    if bucket_seconds and bucket_seconds > 0:
        epoch = int((ts - _EPOCH).total_seconds())
        ts = _EPOCH + timedelta(seconds=epoch - (epoch % bucket_seconds))
    return f"{dedup_key}#{ts.strftime('%Y%m%dT%H%M%S')}"


def parse_dedup_key(dedup_key: str) -> dict:
    """解析 dedup_key 为结构化字段（供过滤/统计使用）。

    返回 dict 含 alert_type/device_id/metric_key/index/action，
    缺段补 None，device_id 转 int（失败保留原字符串）。
    """
    parts = (dedup_key or "").split(":")
    parts = (parts + [""] * 5)[:5]
    device_id_raw = parts[1] if parts[1] else None
    device_id: Optional[int] = None
    if device_id_raw:
        try:
            device_id = int(device_id_raw)
        except ValueError:
            device_id = None  # type: ignore
    return {
        "alert_type": parts[0] or None,
        "device_id": device_id,
        "metric_key": parts[2] or None,
        "index": parts[3] or None,
        "action": parts[4] or None,
    }
