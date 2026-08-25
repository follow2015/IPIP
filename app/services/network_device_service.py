# -*- coding: utf-8 -*-
"""网络设备统一管理服务（device + switch_credentials 原子操作）"""
from app.utils.logging import get_logger
from app.models.device import Device
from app.models.switch_credentials import SwitchCredentials
from app.persistence.device_repository import DeviceRepository
from app.persistence.switch_repo import SwitchRepository

logger = get_logger(__name__)


class NetworkDeviceService:
    """网络设备统一管理服务

    封装 Device + SwitchCredentials 的原子创建/更新操作，
    确保数据同步规则（management_ip等）在服务层统一处理。
    """

    def __init__(self, device_repo: DeviceRepository = None, switch_repo: SwitchRepository = None):
        self.device_repo = device_repo or DeviceRepository()
        self.switch_repo = switch_repo or SwitchRepository()

    _DEVICE_ROUTE_KEYS = ("switch_role", "layer")

    _EXT_ROUTE_KEYS = ("uplink_device_id", "core_device_id", "uplink_port_ids", "port_num")

    _STRIP_KEYS = ("auto_create_nodes", "node_hardware", "storage_items", "nic_ports")

    def _route_switch_config(self, switch_config: dict, device: Device) -> dict:
        """将 switch_config 中的字段路由至 Device / DeviceSwitchExt

        - _DEVICE_ROUTE_KEYS → setattr(device, ...)
        - _EXT_ROUTE_KEYS → 收集为 ext_data 返回

        Returns:
            ext_data: 需要写入 DeviceSwitchExt 的字段字典
        """
        for key in self._DEVICE_ROUTE_KEYS:
            if key in switch_config:
                setattr(device, key, switch_config.pop(key))

        ext_data = {k: switch_config.pop(k) for k in self._EXT_ROUTE_KEYS if k in switch_config}
        return ext_data

    def create_network_device(self, device_data: dict, switch_config: dict) -> tuple:
        """原子创建 Device + SwitchCredentials

        数据同步规则（创建时）：
        - switch_config.ip → devices.management_ip
        - device.cabinet.room_id → switch_credentials.room_id（自动同步）

        Args:
            device_data: devices表字段（name/model/brand/cabinet_id等）
            switch_config: switch_credentials表字段（ip/username/password等）

        Returns:
            (Device, SwitchCredentials) 两个对象
        """
        if switch_config.get("ip"):
            device_data["management_ip"] = switch_config["ip"]

        for key in self._STRIP_KEYS:
            device_data.pop(key, None)

        safe_data = {k: v for k, v in device_data.items() if k in DeviceRepository._WRITABLE_FIELDS}
        device = Device(**safe_data)
        self.device_repo.session.add(device)
        self.device_repo.session.flush()

        ext_data = self._route_switch_config(switch_config, device)

        switch_config["device_id"] = device.id

        if not device.cabinet_id or not device.cabinet or not device.cabinet.room_id:
            raise ValueError(
                "创建网络设备必须提供机房信息：请关联机柜以自动获取 room_id"
            )

        sc_data = {k: v for k, v in switch_config.items() if hasattr(SwitchCredentials, k)}
        for k in ("ip", "username", "password", "device_type"):
            if sc_data.get(k) == "":
                sc_data[k] = None
        switch = SwitchCredentials(**sc_data)
        self.switch_repo.session.add(switch)
        self.switch_repo.session.flush()

        if ext_data and device.switch_ext:
            for k, v in ext_data.items():
                setattr(device.switch_ext, k, v)
        elif ext_data:
            from app.models.device_switch_ext import DeviceSwitchExt
            ext = DeviceSwitchExt(device_id=device.id, **ext_data)
            self.device_repo.session.add(ext)
        if ext_data:
            self.device_repo.session.flush()

        return device, switch

    def update_network_device(self, device_id: int, device_data: dict, switch_config: dict = None) -> Device:
        """原子更新 Device（及可选的 SwitchCredentials）

        数据同步规则（更新时）：
        - switch_config.ip 变更时，同步更新 devices.management_ip
        - device.cabinet_id 变更时，自动同步 switch_credentials.room_id

        Args:
            device_id: 设备ID
            device_data: 需要更新的devices表字段
            switch_config: 需要更新的switch_credentials表字段（可选）

        Returns:
            更新后的Device对象
        """
        device = self.device_repo.find_by_id(device_id)
        if not device:
            raise ValueError(f"设备 {device_id} 不存在")

        for k, v in device_data.items():
            if k in DeviceRepository._WRITABLE_FIELDS:
                setattr(device, k, v)

        if switch_config:
            ext_data = self._route_switch_config(switch_config, device)
            if ext_data and device.switch_ext:
                for k, v in ext_data.items():
                    setattr(device.switch_ext, k, v)
            elif ext_data and not device.switch_ext:
                from app.models.device_switch_ext import DeviceSwitchExt
                ext = DeviceSwitchExt(device_id=device.id, **ext_data)
                self.device_repo.session.add(ext)

        if "cabinet_id" in device_data:
            try:
                from app.persistence.virtual_room_repository import VirtualRoomRepository
                affected_vrs = VirtualRoomRepository().find_by_device_id(device_id)
                if affected_vrs:
                    logger.info(
                        "设备 %d 机柜变更，影响虚拟机房: %s",
                        device_id, [vr.id for vr in affected_vrs]
                    )
            except Exception:
                logger.warning("检查设备 %d 虚拟机房影响失败", device_id, exc_info=True)

        if switch_config:
            if switch_config.get("ip"):
                device.management_ip = switch_config["ip"]
            if switch_config.get("password") == "" or switch_config.get("password") is None:
                switch_config.pop("password", None)
            switch = self.switch_repo.find_by_device_id(device_id)
            if switch:
                for k, v in switch_config.items():
                    if hasattr(switch, k) and k != 'device_id':
                        setattr(switch, k, v)
            else:
                sc_data = {k: v for k, v in switch_config.items() if hasattr(SwitchCredentials, k)}
                sc_data["device_id"] = device_id
                for k in ("ip", "username", "password", "device_type"):
                    if sc_data.get(k) == "":
                        sc_data[k] = None
                new_switch = SwitchCredentials(**sc_data)
                self.switch_repo.session.add(new_switch)

        self.device_repo.session.flush()
        return device

    def get_with_switch_info(self, device_id: int) -> dict:
        """获取设备详情，聚合switch_credentials信息

        Args:
            device_id: 设备ID

        Returns:
            包含device和switch_credential的字典
        """
        device = self.device_repo.find_by_id(device_id)
        switch = self.switch_repo.find_by_device_id(device_id)
        return {
            "device": device.to_dict() if device else None,
            "switch_credential": switch.to_dict() if switch else None,
        }
