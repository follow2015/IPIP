# -*- coding: utf-8 -*-
"""网络管理服务"""
from app.utils.logging import get_logger
from typing import Optional

from app.persistence.network_repo import NetworkRepository
from app.persistence.ip_repositories import IPManagerRepository
from app.services.switch_events import emit_resource_change_global

logger = get_logger(__name__)


class NetworkService:
    """网络段管理服务"""

    def __init__(self, network_repo: NetworkRepository, ip_repo: IPManagerRepository):
        self.network_repo = network_repo
        self.ip_repo = ip_repo

    def get_networks_paginated(self, **filters) -> dict:
        """分页获取网段列表"""
        return self.network_repo.find_networks_by_filters(filters)

    def delete_network(self, network_id: int) -> bool:
        """删除网段"""
        result = self.network_repo.delete_network(network_id)
        if result:
            emit_resource_change_global("network", "delete", ids=[network_id])
        return result

    def update_network_customer(self, network_id: int, customer_id: Optional[int], force: bool = False) -> bool:
        """更新网段客户，并级联同步网段内 IP 的客户归属

        级联策略：
        - force=False（默认）：只填充 customer_id IS NULL 的 IP，保留已手工 IP 级单独分配的不被覆盖。
        - force=True：覆盖网段内所有 IP 的 customer_id，用于网段换客户时一步到位。

        扫描为增量更新（INSERT IGNORE + UPDATE status），不会冲掉此处同步的 customer_id。
        """
        if customer_id is not None:
            from app.services.customer_service import CustomerService
            from app.persistence.customer_repository import CustomerRepository
            CustomerService(CustomerRepository()).assert_allocatable(customer_id)
        result = self.network_repo.update_network(network_id, {"customer_id": customer_id})
        if result:
            net_record = self.network_repo.find_by_id(network_id)
            if net_record and net_record.network and net_record.room_id is not None:
                try:
                    if force:
                        self.ip_repo.bulk_update_customer_all(
                            net_record.room_id, net_record.network, customer_id,
                        )
                    else:
                        self.ip_repo.bulk_update_customer_where_null(
                            net_record.room_id, net_record.network, customer_id,
                        )
                except Exception as e:
                    logger.warning(
                        "级联同步网段 IP 客户归属失败（网段记录已更新）: network_id=%s, error=%s",
                        network_id, e,
                    )
            emit_resource_change_global("network", "update", ids=[network_id])
        return result

    def get_ip_networks_paginated(self, **filters) -> dict:
        """分页获取IP网段"""
        return self.network_repo.find_networks_by_filters(filters)

    def get_network_detail(self, ip_network: str, room_id: Optional[int] = None, page: int = 1, page_size: int = 20) -> dict:
        """获取网段中的IP列表（按CIDR范围精确查询）"""
        return self.ip_repo.search_ips_by_cidr(network_cidr=ip_network, room_id=room_id, page=page, page_size=page_size)
