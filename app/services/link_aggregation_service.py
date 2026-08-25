# -*- coding: utf-8 -*-
"""
链路聚合服务模块

提供链路聚合组的业务逻辑，通过 Repository 访问数据，不直接操作 ORM/DB。
"""
from app.utils.logging import get_logger
from typing import Optional, Dict, List

from app.models.link_aggregation import LinkAggregationGroup
from app.persistence.link_aggregation_repository import LinkAggregationRepository
from app.persistence.switch_port_repository import NetworkPortRepository
from app.exceptions.validation import ValidationError

logger = get_logger(__name__)


class LinkAggregationService:

    def __init__(self, repo: LinkAggregationRepository, port_repo=None):
        self.repo = repo
        self.port_repo = port_repo or NetworkPortRepository()

    def get_by_device(self, device_id: int) -> List[LinkAggregationGroup]:
        return self.repo.find_by_device(device_id)

    def get_all_with_device_info(self, room_id: int = None, device_id: int = None) -> List[Dict]:
        return self.repo.find_all_with_device_info(room_id=room_id, device_id=device_id)

    def get_all_with_device_info_paginated(
        self, page: int = 1, per_page: int = 20,
        search: str = None, room_id: int = None, device_id: int = None,
    ) -> Dict:
        return self.repo.find_all_with_device_info_paginated(
            page=page, per_page=per_page, search=search,
            room_id=room_id, device_id=device_id,
        )

    def create(self, data: Dict) -> LinkAggregationGroup:
        existing = self.repo.find_by_device_and_name(data['device_id'], data['lag_name'])
        if existing:
            raise ValidationError(f"聚合组 {data['lag_name']} 在该设备已存在")
        return self.repo.create(data)

    def delete(self, lag_id: int) -> bool:
        return self.repo.delete(lag_id)

    def update(self, lag_id: int, data: Dict) -> LinkAggregationGroup:
        lag = self.repo.find_by_id(lag_id)
        if not lag:
            raise ValidationError(f"聚合组 ID {lag_id} 不存在")
        allowed = {'purpose', 'lag_type', 'algorithm'}
        for key, value in data.items():
            if key in allowed:
                setattr(lag, key, value)
        self.repo.session.flush()
        return lag


    def update_members_manual(self, lag_id: int, port_ids: list) -> None:
        self.port_repo.clear_lag_group_id(lag_id)
        if port_ids:
            self.port_repo.set_lag_group_id(port_ids, lag_id)
        self.repo.update_member_count(lag_id, len(port_ids))
        self.repo.session.flush()

    def get_members(self, lag_id: int) -> list:
        ports = self.port_repo.find_ports_by_lag_group_id(lag_id)
        return [{"port_id": p.id, "port_name": p.port_name} for p in ports]
