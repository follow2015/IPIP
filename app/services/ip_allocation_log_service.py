# -*- coding: utf-8 -*-
"""
IP分配日志服务模块

提供IP分配日志的业务逻辑，通过 Repository 访问数据，不直接操作 ORM/DB。
"""
from app.utils.logging import get_logger
from typing import Optional, Dict

from app.models.ip_allocation_log import IPAllocationLog
from app.persistence.ip_allocation_log_repository import IPAllocationLogRepository

logger = get_logger(__name__)


class IPAllocationLogService:
    """IP分配日志服务

    所有业务逻辑通过 IPAllocationLogRepository 访问数据库。
    """

    def __init__(self, repo: IPAllocationLogRepository):
        self.repo = repo

    def log_allocation(self, ip_address: str, room_id: int, action: str,
                       old_status: Optional[int], new_status: Optional[int],
                       operator_id: int, detail: Optional[Dict] = None) -> IPAllocationLog:
        """记录IP分配日志

        Args:
            ip_address: IP地址
            room_id: 机房ID
            action: 操作类型
            old_status: 原状态
            new_status: 新状态
            operator_id: 操作人ID
            detail: 操作详情

        Returns:
            IPAllocationLog: 创建的分配日志记录
        """
        return self.repo.create({
            'ip_address': ip_address,
            'room_id': room_id,
            'action': action,
            'old_status': old_status,
            'new_status': new_status,
            'operator_id': operator_id,
            'detail': detail,
        })

    def get_history(self, ip_address: str, room_id: Optional[int] = None,
                    page: int = 1, per_page: int = 20) -> dict:
        """查询IP分配历史

        Args:
            ip_address: IP地址
            room_id: 机房ID（可选）
            page: 页码
            per_page: 每页数量

        Returns:
            dict: 分页结果
        """
        filters = {'ip_address': ip_address}
        if room_id is not None:
            filters['room_id'] = room_id
        return self.repo.paginate(page=page, page_size=per_page, filters=filters, order_by='-created_at')
