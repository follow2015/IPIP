# -*- coding: utf-8 -*-
"""网络设备端口管理服务"""
from app.utils.logging import get_logger
from typing import Dict, List, Optional

from app.persistence.switch_port_repository import NetworkPortRepository
from app.models.network_port import NetworkPort

logger = get_logger(__name__)


class NetworkPortService:
    """网络设备端口管理服务"""

    def __init__(self, repo: NetworkPortRepository):
        self.repo = repo

    def get_port_by_id(self, port_id: int) -> Optional[Dict]:
        """根据端口ID获取端口信息"""
        return self.repo.find_by_id(port_id)

    def get_ports_by_device(self, device_id: int) -> List[Dict]:
        """获取设备全部端口列表"""
        return self.repo.find_ports_by_device(device_id)

    def get_available_ports(self, device_id: int) -> List[Dict]:
        """获取空闲端口"""
        return self.repo.find_available_ports(device_id)

    def find_port_by_name(self, device_id: int, port_name: str) -> Optional[Dict]:
        """按名称查找端口"""
        return self.repo.find_port_by_name(device_id, port_name)

    def count_ports_by_device(self, device_id: int, filters: Dict = None) -> int:
        """统计端口数量"""
        return self.repo.count_ports_by_device(device_id, filters)

    def create_ports_batch(self, device_id: int, ports: List[Dict]) -> int:
        """批量创建端口"""
        if not ports:
            return 0
        return self.repo.create_ports_batch(device_id, ports)

    def update_port_status(self, port_id: int, status: str) -> bool:
        """更新端口占用状态"""
        valid = {"free", "occupied", "disabled", "error"}
        if status not in valid:
            raise ValueError(f"无效端口状态: {status}, 有效值: {valid}")
        return self.repo.update_port(port_id, {"usage_status": status})

    def delete_port(self, port_id: int) -> bool:
        """删除端口"""
        return self.repo.delete_port(port_id)

    def update_port(self, port_id: int, data: Dict) -> bool:
        """更新端口信息"""
        return self.repo.update_port(port_id, data)

    def delete_device_ports(self, device_id: int) -> int:
        """删除设备全部端口"""
        return self.repo.delete_device_ports(device_id)

    def get_by_device(self, device_id: int) -> List[NetworkPort]:
        """获取设备所有端口（返回 ORM 对象列表）"""
        return self.repo.get_by_device(device_id)

    def get_port_names_by_device(self, device_id: int) -> List[str]:
        """获取设备端口名称列表"""
        return self.repo.get_port_names_by_device(device_id)

    def incremental_update(self, device_id: int, port_rows: list) -> None:
        """端口增量更新（委托 NetworkPortRepository）"""
        return self.repo.incremental_update(device_id, port_rows)

