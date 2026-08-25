# -*- coding: utf-8 -*-
"""设备级阈值覆盖仓库（DeviceMetricOverrideRepository）

G4.3：设备级阈值覆盖（/threshold-overrides）的所有数据库访问统一经此仓库，
禁止在 API 路由层直接操作 db.session（项目约束：数据库必须走 Repository 层）。
"""
from typing import List, Optional

from extensions import db
from app.models.device_metric_override import DeviceMetricOverride


class DeviceMetricOverrideRepository:

    def __init__(self, session=None):
        self.session = session or db.session

    def list_by_filters(self, device_id: Optional[int] = None,
                        metric_key: Optional[str] = None) -> List[DeviceMetricOverride]:
        q = self.session.query(DeviceMetricOverride)
        if device_id is not None:
            q = q.filter(DeviceMetricOverride.device_id == device_id)
        if metric_key is not None:
            q = q.filter(DeviceMetricOverride.metric_key == metric_key)
        return q.order_by(DeviceMetricOverride.updated_at.desc()).all()

    def find_by_device_metric(self, device_id: int, metric_key: str) -> Optional[DeviceMetricOverride]:
        return (
            self.session.query(DeviceMetricOverride)
            .filter(
                DeviceMetricOverride.device_id == device_id,
                DeviceMetricOverride.metric_key == metric_key,
            )
            .first()
        )

    def find_by_id(self, override_id: int) -> Optional[DeviceMetricOverride]:
        return self.session.get(DeviceMetricOverride, override_id)

    def find_enabled_by_device_metric(self, device_id: int, metric_key: str) -> Optional[DeviceMetricOverride]:
        return (
            self.session.query(DeviceMetricOverride)
            .filter(
                DeviceMetricOverride.device_id == device_id,
                DeviceMetricOverride.metric_key == metric_key,
                DeviceMetricOverride.enabled == True,
            )
            .first()
        )

    def add(self, rule: DeviceMetricOverride) -> DeviceMetricOverride:
        self.session.add(rule)
        self.session.flush()
        return rule

    def delete(self, rule: DeviceMetricOverride) -> None:
        self.session.delete(rule)
        self.session.flush()

    def flush(self) -> None:
        self.session.flush()
