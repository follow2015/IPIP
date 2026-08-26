# -*- coding: utf-8 -*-
"""设备指标当前值仓库（DeviceMetricLatestRepository）

每次采集后 upsert，存储指标最近一次采集值（含正常值）。
"""
import time
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import OperationalError

from extensions import db
from app.models.device_metric_latest import DeviceMetricLatest

_UPSERT_BATCH_SIZE = 50

_DEADLOCK_MAX_RETRIES = 3
_DEADLOCK_BASE_BACKOFF = 0.05  # 50ms → 100ms → 200ms


class DeviceMetricLatestRepository:
    """设备指标当前值仓库"""

    def __init__(self, session=None):
        self.session = session or db.session

    def find_by_device(self, device_id: int) -> List[DeviceMetricLatest]:
        return (
            self.session.query(DeviceMetricLatest)
            .filter_by(device_id=device_id)
            .order_by(DeviceMetricLatest.metric_key.asc(), DeviceMetricLatest.index_key.asc())
            .all()
        )

    @staticmethod
    def _is_deadlock(exc: OperationalError) -> bool:
        orig = getattr(exc, "orig", None)
        if orig is None:
            return False
        code = getattr(orig, "args", (None,))[0]
        return code == 1213  # Deadlock found when trying to get lock

    def _upsert_batch_with_retry(self, batch: list) -> None:
        """对单批行执行 INSERT...ON DUPLICATE KEY UPDATE，遇 1213 死锁指数退避重试。"""
        for attempt in range(_DEADLOCK_MAX_RETRIES + 1):
            try:
                stmt = mysql_insert(DeviceMetricLatest).values(batch)
                stmt = stmt.on_duplicate_key_update(
                    value=stmt.inserted.value,
                    severity=stmt.inserted.severity,
                    breached=stmt.inserted.breached,
                    collected_at=stmt.inserted.collected_at,
                )
                self.session.execute(stmt)
                self.session.flush()
                return
            except OperationalError as exc:
                if not self._is_deadlock(exc) or attempt == _DEADLOCK_MAX_RETRIES:
                    raise
                self.session.rollback()
                time.sleep(_DEADLOCK_BASE_BACKOFF * (2 ** attempt))

    def upsert_many(self, device_id: int, collected: dict, collected_at: datetime = None) -> int:
        """批量 upsert 采集结果。

        Args:
            device_id: 设备 ID
            collected: {metric_key: {index: {"value":..., "severity":..., "breached":...}}}
            collected_at: 采集时间（缺省 now）
        Returns:
            upsert 行数
        """
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
        for i in range(0, len(rows), _UPSERT_BATCH_SIZE):
            self._upsert_batch_with_retry(rows[i:i + _UPSERT_BATCH_SIZE])
        return len(rows)

    def delete_by_device(self, device_id: int) -> int:
        deleted = (
            self.session.query(DeviceMetricLatest)
            .filter_by(device_id=device_id)
            .delete(synchronize_session=False)
        )
        self.session.flush()
        return deleted
