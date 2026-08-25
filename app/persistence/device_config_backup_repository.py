# -*- coding: utf-8 -*-
"""
设备配置备份与变更 Repository 实现

提供设备配置备份与变更相关的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import Optional, List

from app.models.device_config_backup import DeviceConfigBackup, DeviceConfigChange
from app.persistence.base import SQLAlchemyRepository

logger = get_logger(__name__)


class DeviceConfigBackupRepository(SQLAlchemyRepository):
    """设备配置备份 Repository

    提供设备配置备份相关的数据访问方法。
    """

    def __init__(self, session=None):
        super().__init__(DeviceConfigBackup, session)

    def find_by_device(self, device_id: int) -> List[DeviceConfigBackup]:
        """按设备查询备份"""
        return self.find_all(filters={'device_id': device_id}, order_by='-created_at')

    def find_latest_by_device(self, device_id: int) -> Optional[DeviceConfigBackup]:
        """获取设备最新备份"""
        results = self.find_all(filters={'device_id': device_id}, order_by='-created_at', limit=1)
        return results[0] if results else None

    def find_by_hash(self, config_hash: str) -> Optional[DeviceConfigBackup]:
        """按哈希查询备份"""
        return self.find_one(filters={'config_hash': config_hash})

    def delete_by_device_id(self, device_id: int) -> int:
        """删除指定设备的所有配置备份

        Args:
            device_id: 设备 ID

        Returns:
            int: 删除行数
        """
        return self.session.query(DeviceConfigBackup).filter_by(device_id=device_id).delete(
            synchronize_session=False,
        )


class DeviceConfigChangeRepository(SQLAlchemyRepository):
    """设备配置变更 Repository

    提供设备配置变更相关的数据访问方法。
    """

    def __init__(self, session=None):
        super().__init__(DeviceConfigChange, session)

    def find_by_device(self, device_id: int) -> List[DeviceConfigChange]:
        """按设备查询变更"""
        return self.find_all(filters={'device_id': device_id}, order_by='-created_at')

    def find_pending(self) -> List[DeviceConfigChange]:
        """查询待审批变更"""
        return self.find_all(filters={'status': 'pending'}, order_by='-created_at')

    def delete_by_device_id(self, device_id: int) -> int:
        """删除指定设备的所有配置变更

        Args:
            device_id: 设备 ID

        Returns:
            int: 删除行数
        """
        return self.session.query(DeviceConfigChange).filter_by(device_id=device_id).delete(
            synchronize_session=False,
        )
