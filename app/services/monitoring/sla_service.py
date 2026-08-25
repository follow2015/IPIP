# -*- coding: utf-8 -*-
"""P2-13: SLA/SLO 监控服务

- CRUD: SLA 目标定义（设备/设备组 + 可用率目标 + 评估窗口）
- 达成度计算: 基于 device_monitor_timeseries_hourly 的 reachable 聚合
  - 在 [start, end) 窗口内，对 target_device_ids 的所有设备取 reachable.avg_value 的平均
  - actual_ratio = sum(avg_value) / sample_count
  - met_sla = actual_ratio >= target_ratio
  - 无数据时 actual_ratio=None, sample_count=0, met_sla=False
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)




def list_targets() -> list:
    """列出全部 SLA 目标"""
    from app.persistence.monitor_sla_target_repository import MonitorSlaTargetRepository
    repo = MonitorSlaTargetRepository()
    return [t.to_dict() for t in repo.list_all()]


def create_target(data: dict) -> dict:
    """创建 SLA 目标"""
    from app.models.monitor_sla_target import MonitorSlaTarget
    from app.persistence.monitor_sla_target_repository import MonitorSlaTargetRepository
    from app.exceptions.validation import ValidationError

    name = data.get("name")
    if not name:
        raise ValidationError("name 必填")
    device_ids = data.get("target_device_ids")
    if not device_ids or not isinstance(device_ids, list):
        raise ValidationError("target_device_ids 必填且为非空列表")
    target_ratio = data.get("target_ratio")
    if target_ratio is None or not (0 < target_ratio <= 1):
        raise ValidationError("target_ratio 必须在 (0, 1] 区间")
    window_days = data.get("window_days", 30)
    if not isinstance(window_days, int) or window_days <= 0:
        raise ValidationError("window_days 必须为正整数")

    repo = MonitorSlaTargetRepository()
    target = MonitorSlaTarget(
        name=name,
        target_device_ids=device_ids,
        target_ratio=float(target_ratio),
        window_days=window_days,
        description=data.get("description"),
        enabled=data.get("enabled", True),
    )
    repo.add(target)
    repo.flush()
    return target.to_dict()


def update_target(target_id: int, data: dict) -> dict:
    """更新 SLA 目标"""
    from app.persistence.monitor_sla_target_repository import MonitorSlaTargetRepository
    from app.exceptions.business import BusinessLogicError
    from app.exceptions.validation import ValidationError

    repo = MonitorSlaTargetRepository()
    target = repo.find_by_id(target_id)
    if not target:
        raise BusinessLogicError("SLA 目标不存在", status_code=404)

    if "target_ratio" in data:
        ratio = data["target_ratio"]
        if ratio is None or not (0 < ratio <= 1):
            raise ValidationError("target_ratio 必须在 (0, 1] 区间")
        target.target_ratio = float(ratio)
    if "window_days" in data:
        wd = data["window_days"]
        if not isinstance(wd, int) or wd <= 0:
            raise ValidationError("window_days 必须为正整数")
        target.window_days = wd
    for k in ("name", "target_device_ids", "description", "enabled"):
        if k in data:
            setattr(target, k, data[k])
    repo.flush()
    return target.to_dict()


def delete_target(target_id: int) -> dict:
    """删除 SLA 目标"""
    from app.persistence.monitor_sla_target_repository import MonitorSlaTargetRepository
    from app.exceptions.business import BusinessLogicError
    repo = MonitorSlaTargetRepository()
    target = repo.find_by_id(target_id)
    if not target:
        raise BusinessLogicError("SLA 目标不存在", status_code=404)
    repo.delete(target)
    return {"deleted": target_id}




def compute_achievement(
    target_id: int,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict:
    """计算 SLA 目标在 [start, end) 窗口内的达成度。

    Returns:
        {
            "target_id": int,
            "name": str,
            "target_ratio": float,
            "actual_ratio": float | None,  # None 表示无数据
            "sample_count": int,
            "met_sla": bool,
            "window_start": iso,
            "window_end": iso,
        }
    """
    from app.models.device_monitor_timeseries_hourly import DeviceMonitorTimeseriesHourly
    from app.persistence.monitor_sla_target_repository import MonitorSlaTargetRepository
    from app.exceptions.business import BusinessLogicError
    from extensions import db

    repo = MonitorSlaTargetRepository()
    target = repo.find_by_id(target_id)
    if not target:
        raise BusinessLogicError("SLA 目标不存在", status_code=404)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    end_dt = end or now
    start_dt = start or (end_dt - timedelta(days=target.window_days))

    device_ids = target.target_device_ids or []
    rows = (
        db.session.query(DeviceMonitorTimeseriesHourly.avg_value)
        .filter(
            DeviceMonitorTimeseriesHourly.device_id.in_(device_ids),
            DeviceMonitorTimeseriesHourly.metric == "reachable",
            DeviceMonitorTimeseriesHourly.hour_bucket >= start_dt,
            DeviceMonitorTimeseriesHourly.hour_bucket < end_dt,
        )
        .all()
    )

    sample_count = len(rows)
    if sample_count == 0:
        actual_ratio = None
        met_sla = False
    else:
        actual_ratio = sum(r[0] for r in rows) / sample_count
        met_sla = actual_ratio >= target.target_ratio

    return {
        "target_id": target.id,
        "name": target.name,
        "target_ratio": target.target_ratio,
        "actual_ratio": actual_ratio,
        "sample_count": sample_count,
        "met_sla": met_sla,
        "window_start": start_dt.isoformat(),
        "window_end": end_dt.isoformat(),
    }


def compute_all_achievements(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list:
    """计算全部启用 SLA 目标的达成度（供报表页批量展示）"""
    from app.persistence.monitor_sla_target_repository import MonitorSlaTargetRepository
    repo = MonitorSlaTargetRepository()
    results = []
    for t in repo.list_all():
        if not t.enabled:
            continue
        try:
            results.append(compute_achievement(t.id, start=start, end=end))
        except Exception:
            logger.warning("SLA 达成度计算失败 target_id=%s", t.id, exc_info=True)
    return results
