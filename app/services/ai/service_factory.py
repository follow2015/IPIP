# -*- coding: utf-8 -*-
"""AI 能力层 Service 构造工厂。

背景
----
项目各 Service 采用**构造函数依赖注入**（如 `RoomService(room_repo, cabinet_repo,
device_repo)`），但 AI 能力层（`capabilities/builtin.py`）与 `inspection_service.py`
沿用了无参构造 `RoomService()` —— 这在运行时必然抛
``TypeError: __init__() missing N required positional arguments``，
导致**所有依赖 Service 的 capability 均不可用**（只是崩溃点先后不同）。

本模块统一封装各 Service 的正确构造方式，供 AI 能力层调用：

- 集中构造逻辑，避免在每个 capability 内重复写 repository 装配；
- 不在 service 内部 import 具体 Service 类（避免模块级循环导入），
  改为函数内惰性导入；
- 无状态适配器（SNMP/IPMI/Zabbix/Ping）进程内复用，避免重复构造开销；
- `MonitorService` 每次返回**新实例**：其内部 `_tpl_cache` 是"本轮内"模板缓存
  （设计上由 worker 每轮重建实例来重置），若在此处单例化会导致模板变更不生效。

用法::

    from app.services.ai.service_factory import get_room_service
    rooms = get_room_service().get_all_rooms()
"""
from typing import Any

_adapters_cache: dict = {}


def _get_adapters() -> tuple:
    """获取（并缓存）四个监控协议适配器。

    Returns:
        (snmp_adapter, ipmi_adapter, zabbix_adapter, ping_adapter) 四元组。
    """
    if not _adapters_cache:
        from app.core.enums import MonitorProtocolCode
        from app.services.monitoring.protocol_registry import build_adapter

        _adapters_cache["snmp"] = build_adapter(MonitorProtocolCode.SNMP.value)
        _adapters_cache["ipmi"] = build_adapter(MonitorProtocolCode.IPMI.value)
        _adapters_cache["zabbix"] = build_adapter(MonitorProtocolCode.ZABBIX.value)
        _adapters_cache["ping"] = build_adapter(MonitorProtocolCode.PING.value)
    return (
        _adapters_cache["snmp"],
        _adapters_cache["ipmi"],
        _adapters_cache["zabbix"],
        _adapters_cache["ping"],
    )



def get_device_service() -> Any:
    """构造 DeviceService（依赖 DeviceRepository）。"""
    from app.persistence.device_repository import DeviceRepository
    from app.services.device_service import DeviceService

    return DeviceService(DeviceRepository())


def get_room_service() -> Any:
    """构造 RoomService（依赖 Room/Cabinet/Device 三个 Repository）。

    构造方式与 `app/api/room.py:35` 保持一致。
    """
    from app.persistence.cabinet_repository import CabinetRepository
    from app.persistence.device_repository import DeviceRepository
    from app.persistence.room_repository import RoomRepository
    from app.services.room_service import RoomService

    return RoomService(
        room_repository=RoomRepository(),
        cabinet_repository=CabinetRepository(),
        device_repository=DeviceRepository(),
    )


def get_cabinet_service() -> Any:
    """构造 CabinetService（依赖 CabinetRepository）。"""
    from app.persistence.cabinet_repository import CabinetRepository
    from app.services.cabinet_service import CabinetService

    return CabinetService(CabinetRepository())


def get_monitor_service() -> Any:
    """构造 MonitorService（四个适配器 + 凭据服务 + 状态仓库）。

    装配方式与 `app/services/monitoring/monitor_worker.py:_build_monitor_service`
    保持一致：适配器统一走协议注册表 `build_adapter`（OCP），
    credential_repo / device_repo / notify / template_repo 省略（
    MonitorService 内部会按需构造默认值）。

    Returns:
        新建的 MonitorService 实例（非单例，保证 `_tpl_cache` 随实例重建）。
    """
    from app.persistence.device_monitor_status_repository import (
        DeviceMonitorStatusRepository,
    )
    from app.services.monitoring.credential_service import MonitorCredentialService
    from app.services.monitoring.monitor_service import MonitorService

    snmp, ipmi, zabbix, ping = _get_adapters()
    return MonitorService(
        snmp,
        ipmi,
        zabbix,
        ping,
        MonitorCredentialService(),
        DeviceMonitorStatusRepository(),
    )


def get_ip_crud_service() -> Any:
    """构造 IPCrudService（依赖 IPManagerRepository）。"""
    from app.persistence.ip_repositories import IPManagerRepository
    from app.services.ip_crud_service import IPCrudService

    return IPCrudService(IPManagerRepository())
