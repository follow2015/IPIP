# -*- coding: utf-8 -*-
"""IP CRUD 服务"""
import asyncio
from app.utils.logging import get_logger
from typing import Optional

from app.core.enums import IPStatus
from config import Config
from app.persistence.ip_repositories import IPManagerRepository
from app.services.switch_events import emit_resource_change_global
from app.services.ip_status_service import detect_ip_status, _async_ping, _async_tcp_probe

logger = get_logger(__name__)


class IPCrudService:
    """IP地址CRUD服务"""

    def __init__(self, repo: IPManagerRepository):
        self.repo = repo

    def update_ip_customer(self, ip_address: str, customer_id: int, room_id: Optional[int] = None) -> int:
        """更新IP客户关联"""
        if customer_id is not None:
            from app.services.customer_service import CustomerService
            from app.persistence.customer_repository import CustomerRepository
            CustomerService(CustomerRepository()).assert_allocatable(customer_id)
        result = self.repo.update_customer_by_ip(ip_address, customer_id, room_id)
        if result:
            emit_resource_change_global("ip", "update", ids=[ip_address])
        return result

    def get_ip_notes(self, ip_address: str, room_id: Optional[int] = None) -> list:
        """获取IP备注"""
        return self.repo.find_notes_by_ip(ip_address, room_id)

    def update_ip_notes(self, ip_address: str, notes: str, room_id: Optional[int] = None) -> int:
        """更新IP备注"""
        result = self.repo.update_notes_by_ip(ip_address, notes, room_id)
        if result:
            emit_resource_change_global("ip", "update", ids=[ip_address])
        return result

    def get_ip_detail(self, ip_address: str, room_id: Optional[int] = None) -> Optional[dict]:
        """获取IP详细信息"""
        record = self.repo.find_by_ip_address(ip_address)
        return record.to_dict() if record else None

    def get_ip_addresses_paginated(self, keyword: str = None, customer_id: int = None, room_id: int = None, status: int = None, page: int = 1, page_size: int = 20) -> dict:
        """分页查询IP列表"""
        return self.repo.search_ips(keyword, customer_id, room_id, status, page, page_size)

    def ping_ip(self, ip_address: str) -> bool:
        """Ping检测"""
        status = detect_ip_status(ip_address)
        return status == IPStatus.ACTIVE

    def scan_ports(self, ip_address: str, ports: list = None) -> dict:
        """端口扫描，返回开放端口列表

        用 _async_tcp_probe 异步探测指定端口，默认扫 Config.COMMON_PORTS。
        """
        port_list = ports if ports else list(Config.COMMON_PORTS)
        loop = asyncio.new_event_loop()
        try:
            open_ports = loop.run_until_complete(self._scan_ports_async(ip_address, port_list))
        finally:
            loop.close()
        return {"ip_address": ip_address, "open_ports": open_ports}

    async def _scan_ports_async(self, ip_address: str, ports: list) -> list:
        """异步并发探测多个端口，返回开放端口列表"""
        tasks = [_async_tcp_probe(ip_address, int(p), timeout=1.5) for p in ports]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        open_ports = []
        for port, ok in zip(ports, results):
            if ok is True:
                open_ports.append(int(port))
        return open_ports


IPRudService = IPCrudService
