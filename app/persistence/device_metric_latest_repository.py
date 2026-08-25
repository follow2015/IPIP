# -*- coding: utf-8 -*-
"""设备指标当前值仓库（DeviceMetricLatestRepository）

每次采集后 upsert，存储指标最近一次采集值（含正常值）。
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.dialects.mysql import insert as mysql_insert

from extensions import db
from app.models.device_metric_latest import DeviceMetricLatest


class DeviceMetricLatestRepository:

    def __init__(self, session=None):
        self.session = session or db.session

    def find_by_device(self, device_id: int) -> List[DeviceMetricLatest]:
        return (
            self.session.query(DeviceMetricLatest)
            .filter_by(device_id=device_id)
            .order_by(DeviceMetricLatest.metric_key.asc(), DeviceMetricLatest.index_key.asc())
            .all()
        )

    def upsert_many(self, device_id: int, collected: dict, collected_at: datetime = None) -> int:
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
        stmt = mysql_insert(DeviceMetricLatest).values(rows)
        update_cols = {
            "value": stmt.inserted.value,
            "severity": stmt.inserted.severity,
            "breached": stmt.inserted.breached,
            "collected_at": stmt.inserted.collected_at,
        }
        stmt = stmt.on_duplicate_key_update(**update_cols)
        self.session.execute(stmt)
        self.session.flush()
        return len(rows)

    def delete_by_device(self, device_id: int) -> int:
        deleted = (
            self.session.query(DeviceMetricLatest)
            .filter_by(device_id=device_id)
            .delete(synchronize_session=False)
        )
        self.session.flush()
        return deleted
