# -*- coding: utf-8 -*-
"""设备信息的补采流程（序列号 / 主机名）—— 单一实现（T0.5）。

原实现是 ``SwitchInfoService._collect_serial`` / ``_collect_hostname`` 两个方法：
它们**本身是 SSH 命令编排**，而不是"服务层私有细节"。通道层的
``DEVICE_INFO`` 能力要产出同样的结果，抄一份就会重演"同一份补采规则、两处实现"。

因此把流程抽成函数，**唯一的外部依赖是 ``send_command(switch, command) -> str``
回调**：

- ``SwitchInfoService`` 传 ``self.ssh_mgr.send_show_command``（一次性连接路径，
  行为与抽函数前**完全一致**）；
- ``CliChannel`` 传自己在复用连接上执行的发送器（握手 N→1）。

两条链路的差异因此被压缩到一个回调里，其余规则（命令串、正则、异常降级为
warning 而非失败）两处共享。

为什么异常是"吞掉并按原样返回"而不是抛：这两项都是**锦上添花**的补采——序列号
没采到不影响型号/版本，主机名采不到不影响任何主链路。现状就是在 except 里
warning 后继续，抽函数不改变这个语义（把它改成抛异常会让原本成功的整次采集
因为一台不支持 ``display esn`` 的设备而失败）。
"""
from __future__ import annotations

import re
from typing import Any, Protocol

from app.adapters.base_adapter import ParsedDeviceInfo
from app.core.enums import SwitchDeviceTypeCode
from app.utils.logging import get_logger

logger = get_logger(__name__)

CMD_ESN = "display esn"
CMD_MANUINFO = "display device manuinfo"


class _Sender(Protocol):
    """``send_command(switch, command) -> str`` 的窄协议（运行时鸭子类型）。"""

    def __call__(self, switch: Any, command: str) -> str:  # pragma: no cover - 协议声明
        ...


def _device_type_of(switch: Any) -> str:
    return ((getattr(switch, "device_type", None) or "").lower())


def collect_serial_if_missing(
    switch: Any,
    info: ParsedDeviceInfo,
    send_command: _Sender,
) -> ParsedDeviceInfo:
    """序列号为空时按厂商命令补采；失败或不支持则原样返回。

    华为：``display esn`` → 取所有槽位 ESN，逗号拼接（多槽位框架交换机）；
    H3C：``display device manuinfo`` → 取 ``SN:`` 后字段；
    Cisco：现状不支持（无对应命令），直接返回原 ``info``。
    """
    dt = _device_type_of(switch)
    try:
        if SwitchDeviceTypeCode.HUAWEI in dt:
            output = send_command(switch, CMD_ESN)
            sns = re.findall(r"(?:ESN|SN)\s*(?:of\s+slot\s+\d+\s*)?:\s*(\S+)", output)
        elif SwitchDeviceTypeCode.H3C in dt or "comware" in dt:
            output = send_command(switch, CMD_MANUINFO)
            sns = re.findall(r"SN\s*[:\s]+(\S+)", output)
        else:
            return info

        if sns:
            return ParsedDeviceInfo(
                model=info.model,
                version=info.version,
                serial=",".join(sns),
                uptime=info.uptime,
                hostname=info.hostname,
                brand=info.brand,
            )
    except Exception as e:  # noqa: BLE001 -- 序列号补充采集非致命：主机信息主流程不受影响
        logger.warning(
            "补充采集序列号失败（非致命）device_id=%s: %s",
            getattr(switch, "device_id", "?"), e,
        )
    return info


def collect_hostname_if_missing(
    switch: Any,
    adapter: Any,
    info: ParsedDeviceInfo,
    send_command: _Sender,
) -> ParsedDeviceInfo:
    """主机名为空时用 ``adapter.get_sysname_command()`` 补采；失败则原样返回。"""
    try:
        output = send_command(switch, adapter.get_sysname_command())
        hostname = adapter.parse_sysname(output)
        if hostname:
            return ParsedDeviceInfo(
                model=info.model,
                version=info.version,
                serial=info.serial,
                uptime=info.uptime,
                hostname=hostname,
                brand=info.brand,
            )
    except Exception as e:  # noqa: BLE001 -- 主机名采集非致命：同 82
        logger.warning(
            "采集主机名失败（非致命）device_id=%s: %s",
            getattr(switch, "device_id", "?"), e,
        )
    return info


def collect_full_device_info(
    switch: Any,
    adapter: Any,
    send_command: _Sender,
) -> ParsedDeviceInfo:
    """完整的设备信息采集流程（版本 → 补序列号 → 补主机名）。

    对应原 ``SwitchInfoService.collect_device_info`` 里 fetch+补采的那一段，
    **不含**写库。返回 ``ParsedDeviceInfo``。
    """
    info = adapter.parse_device_info(send_command(switch, adapter.get_version_command()))
    if not info.serial:
        info = collect_serial_if_missing(switch, info, send_command)
    if not info.hostname:
        info = collect_hostname_if_missing(switch, adapter, info, send_command)
    return info


__all__ = [
    "CMD_ESN",
    "CMD_MANUINFO",
    "collect_full_device_info",
    "collect_hostname_if_missing",
    "collect_serial_if_missing",
]
