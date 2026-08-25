# -*- coding: utf-8 -*-
"""
设备配置服务模块

提供设备配置备份与变更管理的业务逻辑，通过 Repository 访问数据，不直接操作 ORM/DB。
"""
import hashlib
from app.utils.logging import get_logger
from typing import Optional

from app.models.device_config_backup import DeviceConfigBackup, DeviceConfigChange
from app.persistence.device_config_backup_repository import (
    DeviceConfigBackupRepository, DeviceConfigChangeRepository
)
from app.exceptions.validation import ValidationError

logger = get_logger(__name__)


class DeviceConfigService:

    def __init__(self, backup_repo: DeviceConfigBackupRepository,
                 change_repo: DeviceConfigChangeRepository):
        self.backup_repo = backup_repo
        self.change_repo = change_repo

    def create_backup(self, device_id: int, config_content: str,
                      backup_type: str = 'manual') -> DeviceConfigBackup:
        config_hash = hashlib.sha256(config_content.encode()).hexdigest()
        file_size = len(config_content.encode('utf-8'))
        return self.backup_repo.create({
            'device_id': device_id,
            'config_content': config_content,
            'config_hash': config_hash,
            'backup_type': backup_type,
            'file_size': file_size,
        })

    def get_latest_config(self, device_id: int) -> Optional[DeviceConfigBackup]:
        return self.backup_repo.find_latest_by_device(device_id)

    def get_config_history(self, device_id: int, page: int = 1, per_page: int = 20) -> dict:
        return self.backup_repo.paginate(
            page=page, page_size=per_page,
            filters={'device_id': device_id}, order_by='-created_at'
        )

    def submit_change(self, device_id: int, change_summary: str,
                      requested_by: int, backup_id: Optional[int] = None,
                      change_detail: Optional[str] = None) -> DeviceConfigChange:
        return self.change_repo.create({
            'device_id': device_id,
            'backup_id': backup_id,
            'change_summary': change_summary,
            'change_detail': change_detail,
            'status': 'pending',
            'requested_by': requested_by,
        })

    def approve_change(self, change_id: int, approved_by: int) -> DeviceConfigChange:
        change = self.change_repo.find_by_id(change_id)
        if not change:
            raise ValidationError("变更请求不存在")
        if change.status != 'pending':
            raise ValidationError(f"变更状态为 {change.status}，无法审批")
        return self.change_repo.update(change_id, {
            'status': 'approved',
            'approved_by': approved_by,
        })

    def reject_change(self, change_id: int, approved_by: int) -> DeviceConfigChange:
        change = self.change_repo.find_by_id(change_id)
        if not change:
            raise ValidationError("变更请求不存在")
        if change.status != 'pending':
            raise ValidationError(f"变更状态为 {change.status}，无法拒绝")
        return self.change_repo.update(change_id, {
            'status': 'rejected',
            'approved_by': approved_by,
        })
