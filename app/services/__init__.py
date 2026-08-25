# -*- coding: utf-8 -*-
"""
服务层包

包含所有业务逻辑服务类。
老模块(ip_service/switch_service/network_scanner)已迁移至 app.new.services。
"""
from app.services.base import BaseService
from app.services.cabinet_service import CabinetService
from app.services.customer_service import CustomerService
from app.services.device_service import DeviceService
from app.services.room_service import RoomService
from app.services.network_port_service import NetworkPortService
from app.services.user_service import UserService
from app.services.wx_service import WeChatService, WeChatTokenManager

from app.services.network_service import NetworkService
from app.services.network_scanner_service import NetworkScannerService
from app.services.switch_info_service import SwitchInfoService
from app.services.switch_config_service import SwitchConfigService
from app.services.switch_events import emit_resource_change
from app.services.ip_crud_service import IPRudService
from app.services.ip_ban_service import IPBanService
from app.services.ip_status_service import detect_ip_status
from app.services.virtual_room_service import VirtualRoomService
from app.exceptions.system import (
    SSHConnectionError as SwitchConnectionError,
    SwitchConfigError,
)

__all__ = [
    "BaseService",
    "RoomService",
    "CabinetService",
    "DeviceService",
    "CustomerService",
    "UserService",
    "SwitchInfoService",
    "SwitchConfigService",
    "emit_resource_change",
    "NetworkPortService",
    "NetworkService",
    "NetworkScannerService",
    "IPRudService",
    "IPBanService",
    "detect_ip_status",
    "VirtualRoomService",
    "WeChatService",
    "WeChatTokenManager",
    "SwitchConnectionError",
    "SwitchConfigError",
]
