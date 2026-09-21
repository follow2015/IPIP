# -*- coding: utf-8 -*-
"""交换机状态缓存仓储（SwitchStatusCacheRepository）

B-44 扫尾批：`switch_info_service` 的采集缓存读取原先直用
``SwitchStatusCache.query``，现收进本仓储。
"""
from typing import Optional

from app.models.switch_credentials import SwitchStatusCache
from app.persistence.base import SQLAlchemyRepository


class SwitchStatusCacheRepository(SQLAlchemyRepository):
    """交换机状态缓存仓储（与设备 1:1）"""

    def __init__(self, session=None):
        super().__init__(SwitchStatusCache, session)

    def delete_by_device(self, device_id: int) -> int:
        """清空该设备的采集缓存行（B-44 收敛：设备彻底删除的清理面）。"""
        return (
            self.session.query(SwitchStatusCache)
            .filter_by(device_id=device_id)
            .delete()
        )

    def find_by_device(self, device_id: int) -> Optional[SwitchStatusCache]:
        """按设备取缓存行（1:1 关联，可能不存在 ⇒ None）。"""
        return self._base_query().filter_by(device_id=device_id).first()
