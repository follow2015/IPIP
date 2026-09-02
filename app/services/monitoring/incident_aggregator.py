# -*- coding: utf-8 -*-
"""事件聚合器（Incident）—— 把散落告警归并为可运营事件

三级聚合策略：
- L1（Task 2）：规则聚合 —— 同设备 + 同告警类型 + 时间窗内
- L2（Task 3）：拓扑聚合 —— 把被依赖抑制的下游告警归入上游事件
- L3（Task 4）：变更关联 —— 关联窗口内的配置变更

设计原则：
- 聚合是**旁路**：任何失败都返回 None / False，绝不阻断告警入箱与投递。
- 归并键比 dedup_key **更粗**：dedup_key 含 metric_key:index:action，同设备
  同类型的告警会因 episode/re_alert_seq 不同散成多个 key，导致单次故障被
  拆成多个事件。
- 时间窗等参数全部配置化：当前库内为测试数据，无法回放调参，需待真实数据校准。
"""
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from app.persistence.audit_log_repository import AuditLogRepository
from app.persistence.monitor_incident_repository import IncidentRepository
from app.persistence.monitor_suppressed_alert_log_repository import (
    SuppressedAlertLogRepository,
)
from app.utils.logging import get_logger
from extensions import db

logger = get_logger(__name__)


def _load_config() -> Tuple[bool, int, int]:
    """读取事件聚合配置（支持 current_app 与 get_config 双路径）。

    Returns:
        (enabled, window, change_window)：功能开关、L1 归并时间窗（秒）、
        L3 变更回溯时间窗（秒）。
    """
    try:
        from flask import current_app
        cfg = current_app.config
        return (
            bool(cfg.get("MONITOR_INCIDENT_ENABLED", True)),
            int(cfg.get("MONITOR_INCIDENT_WINDOW", 300)),
            int(cfg.get("MONITOR_INCIDENT_CHANGE_WINDOW", 300)),
        )
    except Exception:
        from config import get_config
        _c = get_config()
        ci = _c() if isinstance(_c, type) else _c
        return (
            bool(getattr(ci, "MONITOR_INCIDENT_ENABLED", True)),
            int(getattr(ci, "MONITOR_INCIDENT_WINDOW", 300)),
            int(getattr(ci, "MONITOR_INCIDENT_CHANGE_WINDOW", 300)),
        )


def build_incident_key(alert_type: str, device_id: int) -> str:
    """构造 L1 归并键：{alert_type}:{device_id}。

    刻意比 dedup_key 粗 —— 不含 metric_key/index/action，避免单次故障
    因 episode/re_alert_seq 不同被拆成多个事件。
    """
    return f"{alert_type}:{device_id}"


def _link_outbox(outbox_id: Optional[int], incident_id: int,
                 reason_code: str) -> None:
    """把 outbox 行关联到事件（回填 incident_id / reason_code）。

    outbox_id 可能为 None（调用方尚未落库 outbox，例如纯聚合测试），
    此时跳过。失败仅告警 —— 关联失败不影响事件本身已创建/归并的事实。
    """
    if outbox_id is None:
        return
    try:
        from app.models.monitor_alert_outbox import MonitorAlertOutbox
        row = db.session.get(MonitorAlertOutbox, outbox_id)
        if row is None:
            return
        row.incident_id = incident_id
        row.reason_code = reason_code
        db.session.flush()
    except Exception:
        logger.warning("outbox 关联事件失败 outbox_id=%s incident_id=%s",
                       outbox_id, incident_id, exc_info=True)


def aggregate_alert(
    device_id: int,
    alert_type: str,
    severity: str,
    outbox_id: Optional[int],
    now: Optional[float] = None,
) -> Optional[int]:
    """L1 规则聚合：把一条入箱告警归入（或新建）事件，返回 incident_id。

    归并键 ``{alert_type}:{device_id}`` 刻意比 dedup_key 粗 —— 同设备同类型
    的告警在时间窗内归入同一事件，避免单次故障被 episode/re_alert_seq
    拆散。

    Args:
        device_id: 告警设备 ID。
        alert_type: 告警类型。
        severity: 严重级别（新建事件时写入）。
        outbox_id: 对应 outbox 行 ID（用于回填 incident_id；None 则跳过关联）。
        now: 当前时间戳（测试注入）；None 取 time.time()。

    Returns:
        incident_id；功能关闭或失败时返回 None（旁路，不阻断告警入箱）。
    """
    enabled, window, _change_window = _load_config()
    if not enabled:
        return None
    ts = now if now is not None else time.time()
    ts_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    try:
        repo = IncidentRepository()
        key = build_incident_key(alert_type, device_id)
        inc = repo.find_active_by_key(key)
        if inc is not None and inc.last_alert_at is not None:
            last_ts = inc.last_alert_at.replace(tzinfo=timezone.utc).timestamp()
            elapsed = ts - last_ts
            if elapsed <= window:
                repo.touch(inc.id, device_id=device_id, now=ts_dt)
                _link_outbox(outbox_id, inc.id, "L1_rule")
                return inc.id
        new_inc = repo.create(
            incident_key=key,
            title=f"设备 {device_id} {alert_type}",
            severity=severity,
            root_device_id=device_id,
            reason_code="L1_rule",
            now=ts_dt,
        )
        _link_outbox(outbox_id, new_inc.id, "L1_rule")
        try_link_change(new_inc, device_id, now=ts_dt)
        return new_inc.id
    except Exception:
        logger.warning("事件聚合失败（不阻断告警）device=%s type=%s",
                       device_id, alert_type, exc_info=True)
        return None


def attach_suppressed_to_incident(
    upstream_device_id: int,
    alert_type: str,
) -> Optional[int]:
    """L2 拓扑聚合：把「因上游被抑制」的留痕告警归属到上游事件。

    上游设备故障时，下游被抑制的告警已留痕（含 upstream_device_id）。
    本函数把这些留痕行批量回填 incident_id，并刷新事件的影响设备数。

    这是事件中心相对告警列表的核心增值：一次上游宕机波及 N 台下游，
    那 N 条告警并未入箱，只有靠留痕才能还原影响面。

    Args:
        upstream_device_id: 上游（根因）设备 ID。
        alert_type: 告警类型。

    Returns:
        归属的事件 ID；无活跃事件或失败时返回 None（旁路）。
    """
    try:
        repo = IncidentRepository()
        key = build_incident_key(alert_type, upstream_device_id)
        inc = repo.find_active_by_key(key)
        if inc is None:
            return None
        log_repo = SuppressedAlertLogRepository()
        updated = log_repo.attach_to_incident(
            upstream_device_id=upstream_device_id,
            alert_type=alert_type,
            incident_id=inc.id,
        )
        if updated:
            repo.refresh_device_count(inc.id)
        return inc.id
    except Exception:
        logger.warning("L2 拓扑聚合失败（不阻断）upstream=%s",
                       upstream_device_id, exc_info=True)
        return None




def find_recent_change(
    device_id: int,
    within_seconds: int = 300,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """查找设备在时间窗内的最近一次配置变更（审计日志）。

    DB 访问走 AuditLogRepository（C5 约束）。

    Args:
        device_id: 设备 ID。
        within_seconds: 回溯窗口秒数。
        now: 当前时间（测试注入）；None 取当前 UTC。

    Returns:
        ``{"at": datetime, "actor": int, "action": str}``；无变更返回 None。
    """
    try:
        return AuditLogRepository().find_recent_change(
            device_id, within_seconds=within_seconds, now=now,
        )
    except Exception:
        logger.warning("find_recent_change 失败 device=%s", device_id,
                       exc_info=True)
        return None


def try_link_change(
    incident,
    device_id: int,
    now: Optional[datetime] = None,
) -> bool:
    """L3 变更关联：若设备在窗口内有配置变更，把事件 reason_code 标为 L3_change。

    用于根因推断 —— 故障若紧随某次配置变更发生，变更很可能是根因。

    Args:
        incident: 事件对象或事件 ID。传对象可避免重复查询（M12）；
            传 ID 时内部 repo.get 取对象。
        device_id: 设备 ID。
        now: 当前时间（测试注入）；None 取当前 UTC。

    Returns:
        True 表示关联到变更；False 表示无变更或失败（旁路）。

    Note:
        仅当事件当前 reason_code 为 ``L1_rule`` 时才覆盖为 ``L3_change``，
        避免覆盖已由 L2 拓扑聚合标记的 ``L2_topology``（M4）。
    """
    try:
        enabled, _window, change_window = _load_config()
        if not enabled:
            return False
        change = find_recent_change(
            device_id, within_seconds=change_window, now=now,
        )
        if change is None:
            return False
        if isinstance(incident, int):
            inc = IncidentRepository().get(incident)
        else:
            inc = incident
        if inc is None:
            return False
        if inc.reason_code == "L1_rule":
            inc.reason_code = "L3_change"
            db.session.flush()
        return True
    except Exception:
        logger.warning("L3 变更关联失败（不阻断）incident=%s device=%s",
                       incident, device_id, exc_info=True)
        return False
