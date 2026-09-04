# -*- coding: utf-8 -*-
"""基线计算服务：从 DeviceMetricTimeseries 按近 28 天样本计算滑动基线。

设计文档第四节：
- 样本 ≥ 28 天：按 hour_of_day × day_of_week 分桶，baseline_status="normal"
- 样本 7-28 天：仅全局均值±σ（hour_of_day=day_of_week=-1），baseline_status="degraded"
- 样本 < 7 天：不计算，baseline_status="insufficient_samples"（新上线设备/新增采集项）

异常检测算法（按优先级）：基线偏离（3-sigma，主判据）→ 环比突变（>50%）→ 同比。
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.device_metric_baseline import DeviceMetricBaseline
from app.models.device_metric_timeseries import DeviceMetricTimeseries
from app.utils.logging import get_logger
from extensions import db

logger = get_logger(__name__)

_BASELINE_WINDOW_DAYS = 28
_INSUFFICIENT_THRESHOLD_DAYS = 7
_DEGRADED_THRESHOLD_DAYS = 28


def _parse_value(raw: str) -> Optional[float]:
    """把 timeseries.value（字符串）解析为数值。"""
    if raw is None:
        return None
    m = re.search(r"-?\d+\.?\d*", str(raw))
    if m is None:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _mean_stddev(values: List[float]) -> Tuple[float, float]:
    """计算均值与标准差。"""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n == 1:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(variance)


class BaselineService:
    """基线计算与查询。"""

    def recompute_all_baselines(self, window_days: int = _BASELINE_WINDOW_DAYS) -> int:
        """重算所有设备的所有指标基线（供 CLI 调用）。

        Returns:
            更新的基线行数。
        """
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=window_days)

        rows = (
            db.session.query(
                DeviceMetricTimeseries.device_id,
                DeviceMetricTimeseries.metric_key,
                DeviceMetricTimeseries.index_key,
                DeviceMetricTimeseries.value,
                DeviceMetricTimeseries.collected_at,
            )
            .filter(DeviceMetricTimeseries.collected_at >= since)
            .all()
        )

        grouped: Dict[Tuple, List[Tuple[str, datetime]]] = {}
        for device_id, metric_key, index_key, value, collected_at in rows:
            key = (device_id, metric_key, index_key)
            grouped.setdefault(key, []).append((value, collected_at))

        updated = 0
        for (device_id, metric_key, index_key), samples in grouped.items():
            updated += self._recompute_one(device_id, metric_key, index_key, samples, now)

        db.session.commit()
        return updated

    def _recompute_one(
        self,
        device_id: int,
        metric_key: str,
        index_key: str,
        samples: List[Tuple[str, datetime]],
        now: datetime,
    ) -> int:
        """重算单个 (device, metric, index) 的基线。"""
        index_key = index_key or ""
        parsed: List[Tuple[float, datetime]] = []
        for value_raw, collected_at in samples:
            v = _parse_value(value_raw)
            if v is not None:
                parsed.append((v, collected_at))

        unique_days = {(c.date()) for _, c in parsed}
        day_count = len(unique_days)

        if day_count < _INSUFFICIENT_THRESHOLD_DAYS:
            self._delete_baselines(device_id, metric_key, index_key)
            db.session.add(DeviceMetricBaseline(
                device_id=device_id, metric_key=metric_key, index_key=index_key,
                hour_of_day=-1, day_of_week=-1,
                mean=0, stddev=0, sample_count=day_count,
                baseline_status="insufficient_samples",
            ))
            return 1

        if day_count < _DEGRADED_THRESHOLD_DAYS:
            values = [v for v, _ in parsed]
            mean, stddev = _mean_stddev(values)
            self._delete_baselines(device_id, metric_key, index_key)
            db.session.add(DeviceMetricBaseline(
                device_id=device_id, metric_key=metric_key, index_key=index_key,
                hour_of_day=-1, day_of_week=-1,
                mean=mean, stddev=stddev, sample_count=len(values),
                baseline_status="degraded",
            ))
            return 1

        self._delete_baselines(device_id, metric_key, index_key)
        buckets: Dict[Tuple[int, int], List[float]] = {}
        for v, c in parsed:
            ct = c if c.tzinfo else c.replace(tzinfo=timezone.utc)
            local = ct.astimezone()  # 转本地时区（按业务小时分桶）
            h = local.hour
            dow = local.weekday()  # 0=Monday
            buckets.setdefault((h, dow), []).append(v)

        count = 0
        for (h, dow), vals in buckets.items():
            mean, stddev = _mean_stddev(vals)
            db.session.add(DeviceMetricBaseline(
                device_id=device_id, metric_key=metric_key, index_key=index_key,
                hour_of_day=h, day_of_week=dow,
                mean=mean, stddev=stddev, sample_count=len(vals),
                baseline_status="normal",
            ))
            count += 1
        return count

    def _delete_baselines(self, device_id: int, metric_key: str, index_key: str) -> None:
        """删除某 device/metric/index 的所有旧基线（重算前清理）。"""
        db.session.query(DeviceMetricBaseline).filter_by(
            device_id=device_id, metric_key=metric_key, index_key=index_key,
        ).delete(synchronize_session=False)

    def get_baseline(
        self,
        device_id: int,
        metric_key: str,
        index_key: str = "",
        at: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """查某指标在指定时刻的基线（供 device.live_inspection 调用）。

        Args:
            at: 指定时刻（默认 now），按其 hour/weekday 找对应分桶。

        Returns:
            {"mean", "stddev", "sample_count", "baseline_status"} 或 None。
        """
        at = at or datetime.now()
        h = at.hour
        dow = at.weekday()
        row = (
            db.session.query(DeviceMetricBaseline)
            .filter_by(
                device_id=device_id, metric_key=metric_key,
                index_key=index_key, hour_of_day=h, day_of_week=dow,
            )
            .first()
        )
        if row is None:
            row = (
                db.session.query(DeviceMetricBaseline)
                .filter_by(
                    device_id=device_id, metric_key=metric_key,
                    index_key=index_key, hour_of_day=-1, day_of_week=-1,
                )
                .first()
            )
        if row is None:
            return None
        return {
            "mean": float(row.mean),
            "stddev": float(row.stddev),
            "sample_count": row.sample_count,
            "baseline_status": row.baseline_status,
        }

    def detect_anomaly(
        self,
        device_id: int,
        metric_key: str,
        current_value: float,
        index_key: str = "",
    ) -> Dict[str, Any]:
        """异常检测（按优先级：基线偏离 3-sigma → 环比突变 → 同比）。

        Returns:
            {"is_anomaly", "deviation_pct", "baseline", "reason"}
        """
        baseline = self.get_baseline(device_id, metric_key, index_key)
        if baseline is None or baseline["baseline_status"] == "insufficient_samples":
            return {
                "is_anomaly": False,
                "deviation_pct": None,
                "baseline": None,
                "reason": "insufficient_samples",
            }

        mean = baseline["mean"]
        stddev = baseline["stddev"]
        if mean == 0:
            deviation_pct = None
        else:
            deviation_pct = ((current_value - mean) / mean) * 100

        if stddev > 0 and abs(current_value - mean) > 3 * stddev:
            return {
                "is_anomaly": True,
                "deviation_pct": deviation_pct,
                "baseline": baseline,
                "reason": "baseline_3sigma",
            }

        if deviation_pct is not None and abs(deviation_pct) > 100:
            return {
                "is_anomaly": True,
                "deviation_pct": deviation_pct,
                "baseline": baseline,
                "reason": "baseline_deviation",
            }

        return {
            "is_anomaly": False,
            "deviation_pct": deviation_pct,
            "baseline": baseline,
            "reason": "normal",
        }
