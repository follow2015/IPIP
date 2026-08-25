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

    def __init__(self, repo: IPAllocationLogRepository):
        self.repo = repo

    def log_allocation(self, ip_address: str, room_id: int, action: str,
                       old_status: Optional[int], new_status: Optional[int],
                       operator_id: int, detail: Optional[Dict] = None) -> IPAllocationLog:
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
        filters = {'ip_address': ip_address}
        if room_id is not None:
            filters['room_id'] = room_id
        return self.repo.paginate(page=page, page_size=per_page, filters=filters, order_by='-created_at')
