# -*- coding: utf-8 -*-
"""监控设备类型推荐配置仓库（MonitorDeviceTypeRecommendRepository）

设备类型推荐（/device-type-recommends）的所有数据库访问统一经此仓库，
禁止在 API 路由层直接操作 db.session（项目约束：数据库必须走 Repository 层）。
"""
from typing import List, Optional

from extensions import db
from app.models.monitor_device_type_recommend import MonitorDeviceTypeRecommend


class MonitorDeviceTypeRecommendRepository:

    def __init__(self, session=None):
        self.session = session or db.session

    def list_all(self) -> List[MonitorDeviceTypeRecommend]:
        return self.session.query(MonitorDeviceTypeRecommend).all()

    def find_by_device_type(self, device_type: str) -> Optional[MonitorDeviceTypeRecommend]:
        return (
            self.session.query(MonitorDeviceTypeRecommend)
            .filter_by(device_type=device_type)
            .first()
        )

    def add(self, row: MonitorDeviceTypeRecommend) -> MonitorDeviceTypeRecommend:
        self.session.add(row)
        self.session.flush()
        return row

    def flush(self) -> None:
        self.session.flush()
