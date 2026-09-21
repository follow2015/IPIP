# -*- coding: utf-8 -*-
"""设备硬件信息仓储（DeviceHardwareRepository）

B-44 device_service 批：device_hardware 表的清理面收进本仓储。
"""
from app.models.device_hardware import DeviceHardware
from app.persistence.base import SQLAlchemyRepository


class DeviceHardwareRepository(SQLAlchemyRepository):
    """设备硬件信息仓储（device_hardware 表）"""

    def __init__(self, session=None):
        super().__init__(DeviceHardware, session)

    def delete_by_device(self, device_id: int) -> int:
        """清空该设备的硬件信息行（B-44 收敛：机箱重建的清理面）。"""
        return (
            self.session.query(DeviceHardware)
            .filter_by(device_id=device_id)
            .delete()
        )
