# -*- coding: utf-8 -*-
"""
设备适配器工厂

根据设备类型字符串返回对应的适配器实例。
"""
from app.adapters.base_adapter import BaseDeviceAdapter
from app.adapters.huawei_adapter import HuaweiAdapter
from app.adapters.h3c_adapter import H3CAdapter
from app.adapters.cisco_adapter import CiscoAdapter
from app.core.enums import SwitchDeviceTypeCode
from app.exceptions.business import DeviceNotSupported

_ADAPTER_MAP: dict[str, type[BaseDeviceAdapter]] = {
    SwitchDeviceTypeCode.HUAWEI: HuaweiAdapter,
    SwitchDeviceTypeCode.H3C: H3CAdapter,
    SwitchDeviceTypeCode.CISCO: CiscoAdapter,
}


def get_adapter(device_type: str) -> BaseDeviceAdapter:
    """根据设备类型返回对应适配器实例

    去掉 _telnet 后缀后查找注册表，未知厂商抛出 DeviceNotSupported。
    实例化后校验关键抽象方法已实现，防止注册不完整的适配器。

    Args:
        device_type: 设备类型字符串（如 huawei, h3c, cisco, huawei_telnet）

    Returns:
        BaseDeviceAdapter: 适配器实例

    Raises:
        DeviceNotSupported: 不支持的设备类型
    """
    normalized = (device_type or "").lower().split("_")[0]
    cls = _ADAPTER_MAP.get(normalized)
    if cls is None:
        raise DeviceNotSupported(
            f"不支持的设备类型: {device_type!r}。"
            f"可选值: {list(_ADAPTER_MAP.keys())}"
        )
    adapter = cls()
    _validate_adapter(adapter, normalized)
    return adapter


def _validate_adapter(adapter: BaseDeviceAdapter, device_type: str) -> None:
    """校验适配器实例的关键方法已实现

    检查适配器是否正确实现了核心抽象方法，
    防止注册了仅继承但未覆写关键方法的残缺适配器。

    Args:
        adapter: 适配器实例
        device_type: 设备类型标识（用于错误消息）
    """
    required_methods = ["parse_routes", "parse_arp", "parse_ports",
                        "get_ban_commands", "get_arp_ban_commands"]
    for method_name in required_methods:
        method = getattr(adapter, method_name, None)
        if method is None:
            raise DeviceNotSupported(
                f"适配器 {device_type!r} 缺少必要方法: {method_name}"
            )


def register_adapter(device_type: str, adapter_cls: type[BaseDeviceAdapter]) -> None:
    """注册新的设备适配器

    用于扩展支持新的设备类型。

    Args:
        device_type: 设备类型标识
        adapter_cls: 适配器类
    """
    _ADAPTER_MAP[device_type.lower()] = adapter_cls
