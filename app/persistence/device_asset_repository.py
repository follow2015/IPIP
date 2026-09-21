# -*- coding: utf-8 -*-
"""设备资产（保修/生命周期）仓储（DeviceAssetRepository）

B-44 扫尾批：`asset_warranty_alert` 的保修到期扫描原先直用
``db.session.query(...)``，现收进本仓储。
"""
from typing import List, Tuple


from app.models.device import Device
from app.models.device_asset import DeviceAsset
from app.core.enums import DeviceStatus
from extensions import db


class DeviceAssetRepository:
    """设备资产仓储"""

    def __init__(self, session=None):
        self.session = session or db.session

    def list_warranty_rows(self) -> List[Tuple]:
        """取**在役**设备的资产行（保修到期扫描的数据源）。

        返回 6 列行元组 ``(device_id, device_name, warranty_end,
        lifecycle_years, online_date, offline_date)`` —— 调用方用它构造
        ``AssetRow`` 命名元组，故保持行元组形态（不整行拉实体）。

        过滤（与原实现逐条一致，勿增删）：
        · ``Device.deleted_at IS NULL``（软删设备不出现在保修提醒里）；
        · ``Device.status != SCRAPPED``（报废设备无保修意义）；
        · ``DeviceAsset.offline_date IS NULL``（已下线设备不提醒）。
        """
        return (
            self.session.query(
                DeviceAsset.device_id,
                Device.device_name,
                DeviceAsset.warranty_end,
                DeviceAsset.lifecycle_years,
                DeviceAsset.online_date,
                DeviceAsset.offline_date,
            )
            .join(Device, Device.id == DeviceAsset.device_id)
            .filter(
                Device.deleted_at.is_(None),
                Device.status != DeviceStatus.SCRAPPED,
                DeviceAsset.offline_date.is_(None),
            )
            .all()
        )
