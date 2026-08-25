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
    required_methods = ["parse_routes", "parse_arp", "parse_ports",
                        "get_ban_commands", "get_arp_ban_commands"]
    for method_name in required_methods:
        method = getattr(adapter, method_name, None)
        if method is None:
            raise DeviceNotSupported(
                f"适配器 {device_type!r} 缺少必要方法: {method_name}"
            )


def register_adapter(device_type: str, adapter_cls: type[BaseDeviceAdapter]) -> None:
    _ADAPTER_MAP[device_type.lower()] = adapter_cls
