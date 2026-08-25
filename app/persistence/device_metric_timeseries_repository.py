# -*- coding: utf-8 -*-
"""设备指标值历史时序仓库（DeviceMetricTimeseriesRepository）

每次采集后批量 INSERT（与 device_metric_latest upsert 同事务），存储指标值历史时序，
供前端趋势图查询。纯插入无 upsert（时序表无唯一键约束，每次采集都是新行）。
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import and_

from extensions import db
from app.models.device_metric_timeseries import DeviceMetricTimeseries


class DeviceMetricTimeseriesRepository:

    def __init__(self, session=None):
        self.session = session or db.session

    def add_many(self, device_id: int, collected: dict, collected_at: datetime = None) -> int:
        if not collected:
            return 0
        collected_at = collected_at or datetime.now(timezone.utc)
        rows = []
        for metric_key, table in collected.items():
            for index, info in (table or {}).items():
                rows.append({
                    "device_id": device_id,
                    "metric_key": metric_key,
                    "index_key": str(index),
                    "value": str(info.get("value", "")) if info.get("value") is not None else None,
                    "severity": info.get("severity"),
                    "breached": bool(info.get("breached", False)),
                    "collected_at": collected_at,
                })
        if not rows:
            return 0
        self.session.bulk_insert_mappings(DeviceMetricTimeseries, rows)
        self.session.flush()
        return len(rows)

    def list_by_metric(
        self,
        device_id: int,
        metric_key: str,
        index_key: Optional[str] = None,
        from_: Optional[datetime] = None,
        to: Optional[datetime] = None,
        limit: int = 2000,
    ) -> List[DeviceMetricTimeseries]:
        limit = max(1, min(limit, 5000))
        conditions = [
            DeviceMetricTimeseries.device_id == device_id,
            DeviceMetricTimeseries.metric_key == metric_key,
        ]
        if index_key is not None:
            conditions.append(DeviceMetricTimeseries.index_key == index_key)
        if from_ is not None:
            conditions.append(DeviceMetricTimeseries.collected_at >= from_)
        if to is not None:
            conditions.append(DeviceMetricTimeseries.collected_at <= to)
        return (
            self.session.query(DeviceMetricTimeseries)
            .filter(and_(*conditions))
            .order_by(DeviceMetricTimeseries.collected_at.asc())
            .limit(limit)
            .all()
        )

    def list_metric_keys(self, device_id: int) -> List[str]:
        rows = (
            self.session.query(DeviceMetricTimeseries.metric_key)
            .filter_by(device_id=device_id)
            .distinct()
            .order_by(DeviceMetricTimeseries.metric_key.asc())
            .all()
        )
        return [r[0] for r in rows]
