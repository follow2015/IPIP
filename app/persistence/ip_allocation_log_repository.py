# -*- coding: utf-8 -*-
"""
IP分配日志 Repository 实现

提供IP分配日志相关的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import Optional, List

from app.models.ip_allocation_log import IPAllocationLog
from app.persistence.base import SQLAlchemyRepository

logger = get_logger(__name__)


class IPAllocationLogRepository(SQLAlchemyRepository):

    def __init__(self, session=None):
        super().__init__(IPAllocationLog, session)

    def find_by_ip(self, ip_address: str, room_id: Optional[int] = None) -> List[IPAllocationLog]:
        filters = {'ip_address': ip_address}
        if room_id is not None:
            filters['room_id'] = room_id
        return self.find_all(filters=filters, order_by='-created_at')
