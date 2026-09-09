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
            dict: 分页结果，记录列表在 "data" 键下
        """
        return self.backup_repo.paginate(
            page=page, page_size=per_page,
            filters={'device_id': device_id}, order_by='-created_at'
        )

    def capture_backup_from_device(self, device_id: int, timeout: int = 60) -> DeviceConfigBackup:
        """从设备实时拉取 running-config 并落库。

        备份命令按厂商命令族选取（H3C/Huawei: display current-configuration，
        Cisco: show running-config），避免硬编码命令在其它厂商设备上失败。

        Args:
            device_id: 设备ID
            timeout: SSH 超时（秒）

        Returns:
            DeviceConfigBackup: 备份记录（配置未变化则复用已有同 hash 记录）

        Raises:
            ValidationError: 设备不存在 / 无 SSH 凭据 / 未开启 SSH / 命令族不支持 /
                采集内容为空或 SSH 失败
        """
        from app.infra import SSHManager
        from app.models.device import Device
        from app.persistence.switch_repo import SwitchRepository
        from app.services.ai.command_safety import get_backup_command
        from app.services.ai.circuit_breaker import get_circuit_breaker, AICircuitOpenError
        from app.services.device_op_lock import device_op_lock, DeviceOperationConflict
        from extensions import db

        device = (
            db.session.query(Device)
            .filter(Device.id == device_id, Device.deleted_at.is_(None))
            .first()
        )
        if not device:
            raise ValidationError("设备不存在")

        switch = SwitchRepository().find_by_device_id(device_id)
        if not switch:
            raise ValidationError("该设备未配置 SSH 凭据，无法自动采集配置")
        if switch.has_ssh is False:
            raise ValidationError("该设备未开启 SSH 权限，无法自动采集配置")

        command = get_backup_command(device.brand)
        if not command:
            raise ValidationError(f"暂不支持该厂商的配置采集（brand={device.brand}）")

        try:
            with device_op_lock.acquire(device_id, timeout=10, mode="read"):
                try:
                    raw_config = get_circuit_breaker("ssh").call(
                        lambda: SSHManager().send_show_command(switch, command, timeout=timeout)
                    )
                except AICircuitOpenError:
                    raise ValidationError("SSH 通道熔断中，请稍后重试")
        except DeviceOperationConflict:
            raise ValidationError("设备繁忙（存在进行中的操作），请稍后重试")

        if not raw_config or not isinstance(raw_config, str):
            raise ValidationError("采集到的配置内容为空")

        config_hash = hashlib.sha256(raw_config.encode("utf-8")).hexdigest()
        existing = self.backup_repo.find_all(
            filters={'device_id': device_id, 'config_hash': config_hash}, limit=1,
        )
        if existing:
            return existing[0]

        return self.create_backup(device_id, raw_config, backup_type='manual')

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

    def list_changes(self, device_id: int) -> list[DeviceConfigChange]:
        """获取设备的配置变更（审批）列表

        Args:
            device_id: 设备ID

        Returns:
            list[DeviceConfigChange]: 按创建时间倒序
        """
        return self.change_repo.find_by_device(device_id)

    def review_change(self, device_id: int, change_id: int, action: str,
                      approved_by: int) -> DeviceConfigChange:
        """审批配置变更请求（approve / reject）

        校验归属（变更必须属于该设备）与双人复核（审批人不得是申请人），
        否则"谁能提交谁就能自己批准"会让审批流形同虚设。

        Args:
            device_id: 设备ID（路径参数，用于校验归属）
            change_id: 变更请求ID
            action: approve 或 reject
            approved_by: 审批人ID

        Returns:
            DeviceConfigChange: 更新后的变更记录

        Raises:
            ValidationError: 变更不存在 / 归属不符 / 状态不允许 / 自审
        """
        change = self.change_repo.find_by_id(change_id)
        if not change:
            raise ValidationError("变更请求不存在")
        if change.device_id != device_id:
            raise ValidationError("变更请求不属于该设备")
        if change.status != 'pending':
            raise ValidationError(f"变更状态为 {change.status}，无法审批")
        if change.requested_by is not None and change.requested_by == approved_by:
            raise ValidationError("审批人不能是申请人本人")

        status = 'approved' if action == 'approve' else 'rejected'
        return self.change_repo.update(change_id, {
            'status': status,
            'approved_by': approved_by,
        })
