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
    """链路聚合服务

    所有业务逻辑通过 LinkAggregationRepository 访问数据库。
    """

    def __init__(self, repo: LinkAggregationRepository, port_repo=None):
        self.repo = repo
        self.port_repo = port_repo or NetworkPortRepository()

    def get_by_device(self, device_id: int) -> List[LinkAggregationGroup]:
        """获取设备的聚合组

        Args:
            device_id: 设备ID

        Returns:
            List[LinkAggregationGroup]: 该设备的聚合组列表
        """
        return self.repo.find_by_device(device_id)

    def get_all_with_device_info(self, room_id: int = None, device_id: int = None) -> List[Dict]:
        """获取所有聚合组（含设备名称和机房信息）

        Args:
            room_id: 可选机房ID筛选
            device_id: 可选设备ID筛选

        Returns:
            List[Dict]: 包含设备信息的聚合组字典列表
        """
        return self.repo.find_all_with_device_info(room_id=room_id, device_id=device_id)

    def get_all_with_device_info_paginated(
        self, page: int = 1, per_page: int = 20,
        search: str = None, room_id: int = None, device_id: int = None,
    ) -> Dict:
        """获取所有聚合组（含设备名称和机房信息，分页）

        Args:
            page: 页码
            per_page: 每页数量
            search: 模糊搜索（匹配聚合组名称）
            room_id: 可选机房ID筛选
            device_id: 可选设备ID筛选

        Returns:
            Dict: {"items": [...], "total": int}
        """
        return self.repo.find_all_with_device_info_paginated(
            page=page, per_page=per_page, search=search,
            room_id=room_id, device_id=device_id,
        )

    def create(self, data: Dict) -> LinkAggregationGroup:
        """创建聚合组

        Args:
            data: 聚合组字段字典

        Returns:
            LinkAggregationGroup: 创建的聚合组记录

        Raises:
            ValidationError: 聚合组名在该设备已存在
        """
        existing = self.repo.find_by_device_and_name(data['device_id'], data['lag_name'])
        if existing:
            raise ValidationError(f"聚合组 {data['lag_name']} 在该设备已存在")
        return self.repo.create(data)

    def delete(self, lag_id: int) -> bool:
        """删除聚合组

        Args:
            lag_id: 聚合组ID

        Returns:
            bool: 是否删除成功
        """
        return self.repo.delete(lag_id)

    def update(self, lag_id: int, data: Dict) -> LinkAggregationGroup:
        """更新聚合组字段（如 purpose）

        Args:
            lag_id: 聚合组ID
            data: 待更新字段字典

        Returns:
            LinkAggregationGroup: 更新后的聚合组记录

        Raises:
            ValidationError: 聚合组不存在
        """
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
        """手动更新LAG成员端口（全量替换，has_ssh=false专用）

        清空旧lag_group_id，设置新lag_group_id，同步 member_count 列。

        Args:
            lag_id: LAG组ID
            port_ids: 端口ID列表
        """
        self.port_repo.clear_lag_group_id(lag_id)
        if port_ids:
            self.port_repo.set_lag_group_id(port_ids, lag_id)
        self.repo.update_member_count(lag_id, len(port_ids))
        self.repo.session.flush()

    def get_members(self, lag_id: int) -> list:
        """获取LAG成员端口列表

        Args:
            lag_id: LAG组ID

        Returns:
            list: 成员端口字典列表
        """
        ports = self.port_repo.find_ports_by_lag_group_id(lag_id)
        return [{"port_id": p.id, "port_name": p.port_name} for p in ports]
