# -*- coding: utf-8 -*-
"""网络设备端口管理服务"""
from app.utils.logging import get_logger
from typing import Dict, List, Optional

from app.persistence.switch_port_repository import NetworkPortRepository
from app.models.network_port import NetworkPort

logger = get_logger(__name__)


class NetworkPortService:

    def __init__(self, repo: NetworkPortRepository):
        self.repo = repo

    def get_port_by_id(self, port_id: int) -> Optional[Dict]:
        return self.repo.find_by_id(port_id)

    def get_ports_by_device(self, device_id: int) -> List[Dict]:
        return self.repo.find_ports_by_device(device_id)

    def get_available_ports(self, device_id: int) -> List[Dict]:
        return self.repo.find_available_ports(device_id)

    def find_port_by_name(self, device_id: int, port_name: str) -> Optional[Dict]:
        return self.repo.find_port_by_name(device_id, port_name)

    def count_ports_by_device(self, device_id: int, filters: Dict = None) -> int:
        return self.repo.count_ports_by_device(device_id, filters)

    def create_ports_batch(self, device_id: int, ports: List[Dict]) -> int:
        if not ports:
            return 0
        return self.repo.create_ports_batch(device_id, ports)

    def update_port_status(self, port_id: int, status: str) -> bool:
        valid = {"free", "occupied", "disabled", "error"}
        if status not in valid:
            raise ValueError(f"无效端口状态: {status}, 有效值: {valid}")
        return self.repo.update_port(port_id, {"usage_status": status})

    def delete_port(self, port_id: int) -> bool:
        return self.repo.delete_port(port_id)

    def update_port(self, port_id: int, data: Dict) -> bool:
        return self.repo.update_port(port_id, data)

    def delete_device_ports(self, device_id: int) -> int:
        return self.repo.delete_device_ports(device_id)

    def get_by_device(self, device_id: int) -> List[NetworkPort]:
        return self.repo.get_by_device(device_id)

    def get_port_names_by_device(self, device_id: int) -> List[str]:
        return self.repo.get_port_names_by_device(device_id)

    def incremental_update(self, device_id: int, port_rows: list) -> None:
        return self.repo.incremental_update(device_id, port_rows)
