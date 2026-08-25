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
    """设备配置服务

    备份与变更管理，所有业务逻辑通过 Repository 访问数据库。
    """

    def __init__(self, backup_repo: DeviceConfigBackupRepository,
                 change_repo: DeviceConfigChangeRepository):
        self.backup_repo = backup_repo
        self.change_repo = change_repo

    def create_backup(self, device_id: int, config_content: str,
                      backup_type: str = 'manual') -> DeviceConfigBackup:
        """创建配置备份

        Args:
            device_id: 设备ID
            config_content: 配置内容
            backup_type: 备份类型（manual/auto）

        Returns:
            DeviceConfigBackup: 创建的备份记录
        """
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
        """获取设备最新配置

        Args:
            device_id: 设备ID

        Returns:
            DeviceConfigBackup: 最新备份记录，不存在则返回None
        """
        return self.backup_repo.find_latest_by_device(device_id)

    def get_config_history(self, device_id: int, page: int = 1, per_page: int = 20) -> dict:
        """获取配置备份历史

        Args:
            device_id: 设备ID
            page: 页码
            per_page: 每页数量

        Returns:
            dict: 分页结果
        """
        return self.backup_repo.paginate(
            page=page, page_size=per_page,
            filters={'device_id': device_id}, order_by='-created_at'
        )

    def submit_change(self, device_id: int, change_summary: str,
                      requested_by: int, backup_id: Optional[int] = None,
                      change_detail: Optional[str] = None) -> DeviceConfigChange:
        """提交配置变更请求

        Args:
            device_id: 设备ID
            change_summary: 变更摘要
            requested_by: 申请人ID
            backup_id: 关联备份ID（可选）
            change_detail: 变更详情（可选）

        Returns:
            DeviceConfigChange: 创建的变更请求记录
        """
        return self.change_repo.create({
            'device_id': device_id,
            'backup_id': backup_id,
            'change_summary': change_summary,
            'change_detail': change_detail,
            'status': 'pending',
            'requested_by': requested_by,
        })

    def approve_change(self, change_id: int, approved_by: int) -> DeviceConfigChange:
        """审批配置变更

        Args:
            change_id: 变更ID
            approved_by: 审批人ID

        Returns:
            DeviceConfigChange: 更新后的变更记录

        Raises:
            ValidationError: 变更请求不存在或状态不允许审批
        """
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
        """拒绝配置变更

        Args:
            change_id: 变更ID
            approved_by: 审批人ID

        Returns:
            DeviceConfigChange: 更新后的变更记录

        Raises:
            ValidationError: 变更请求不存在或状态不允许拒绝
        """
        change = self.change_repo.find_by_id(change_id)
        if not change:
            raise ValidationError("变更请求不存在")
        if change.status != 'pending':
            raise ValidationError(f"变更状态为 {change.status}，无法拒绝")
        return self.change_repo.update(change_id, {
            'status': 'rejected',
            'approved_by': approved_by,
        })
