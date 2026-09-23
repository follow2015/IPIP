# -*- coding: utf-8 -*-
"""设备指标基线仓库（DeviceMetricBaselineRepository）

按 ``(device_id, metric_key, index_key, hour_of_day, day_of_week)`` 分桶存储
基线与标准差，供 AI 异常检测读取。

B-44 收敛：`BaselineService` 原先直用 `db.session.query(...)`（4 处），
现统一收进本仓储 —— 与 `device_metric_latest_repository` 同族的取数入口。

口径说明（无软删除）：`DeviceMetricBaseline` 继承 `BaseModel` 但**未开启**
``__soft_delete__``，故仓储不走 `_base_query()`（与 Device 那类不同），
行为与原裸查询逐字一致。
"""
from typing import Optional

from extensions import db
from app.models.device_metric_baseline import DeviceMetricBaseline


class DeviceMetricBaselineRepository:
    """设备指标基线仓库"""

    def __init__(self, session=None):
        self.session = session or db.session

    def delete_scope(self, device_id: int, metric_key: str, index_key: str) -> int:
        """删除某 ``(device, metric, index)`` 的**全部**基线（重算前清理）。

        Returns:
            int: 删除行数（含所有时间桶）
        """
        return (
            self.session.query(DeviceMetricBaseline)
            .filter_by(
                device_id=device_id, metric_key=metric_key, index_key=index_key,
            )
            .delete(synchronize_session=False)
        )

    def find_bucket(
        self, device_id: int, metric_key: str, index_key: str,
        hour_of_day: int, day_of_week: int,
    ) -> Optional[DeviceMetricBaseline]:
        """取某个时间桶的基线行。

        [WARN] "精确桶（当时刻的 hour/weekday）→ 降级桶（-1/-1）"的两段回退是
        **调用方**的业务语义（`BaselineService.get_baseline`），故此处只表达
        "取一个桶"，回退顺序留在 service（换仓储不改变回退行为）。
        """
        return (
            self.session.query(DeviceMetricBaseline)
            .filter_by(
                device_id=device_id, metric_key=metric_key, index_key=index_key,
                hour_of_day=hour_of_day, day_of_week=day_of_week,
            )
            .first()
        )
