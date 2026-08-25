# -*- coding: utf-8 -*-
"""监控协议注册表（M8 / OCP 重构核心）

将「新增一个监控协议需要改多处」的散点逻辑收敛到**单一数据源**：

- 适配器类（无参构造）
- 适用的设备类型（device_type → 候选协议顺序）
- 归属的轮询循环（worker loop grouping，如 snmp / bmc）
- 凭据 payload 必填字段（供 schema 入口校验；SNMP 按子版本细分）

新增协议 = 1 个枚举成员（`app/core/enums.MonitorProtocolCode`）+ 1 条
`ProtocolSpec` 注册；`monitor_service` / `schemas/monitor` / `monitor_worker`
的行为自动跟随，**无需散点改动**。

注意：枚举本身仍是协议「词汇表」，新增协议须在枚举中加一个成员（这是协议
语义的天然归属，无法完全消除）；注册表负责承载所有行为元数据，使枚举之外的
所有散点收敛到一处。
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple, Type

from app.exceptions.validation import ValidationError
from app.core.enums import MonitorProtocolCode
from app.services.monitoring.adapters.base_adapter import MonitorAdapter
from app.services.monitoring.adapters.snmp_adapter import SNMPAdapter
from app.services.monitoring.adapters.ipmi_adapter import IPMIAdapter
from app.services.monitoring.adapters.zabbix_adapter import ZabbixAdapter
from app.services.monitoring.adapters.ping_adapter import PingAdapter
from app.services.monitoring.snmp_versions import SNMP_REQUIRED_BY_VERSION


@dataclass(frozen=True)
class ProtocolSpec:

    code: str
    adapter_class: Type[MonitorAdapter]
    applies_to_device_types: Tuple[str, ...]
    worker_loop: str
    credential_required_fields: Tuple[str, ...] = ()
    excludes_loops: Tuple[str, ...] = ()
    requires_credential: bool = True


PROTOCOL_REGISTRY: Dict[str, ProtocolSpec] = {
    MonitorProtocolCode.SNMP.value: ProtocolSpec(
        code=MonitorProtocolCode.SNMP.value,
        adapter_class=SNMPAdapter,
        applies_to_device_types=("network", "server", "other"),
        worker_loop="snmp",
        credential_required_fields=(),
    ),
    MonitorProtocolCode.IPMI.value: ProtocolSpec(
        code=MonitorProtocolCode.IPMI.value,
        adapter_class=IPMIAdapter,
        applies_to_device_types=("server",),
        worker_loop="bmc",
        credential_required_fields=("username", "password"),
    ),
    MonitorProtocolCode.ZABBIX.value: ProtocolSpec(
        code=MonitorProtocolCode.ZABBIX.value,
        adapter_class=ZabbixAdapter,
        applies_to_device_types=("network", "other", "server"),
        worker_loop="zabbix",
        credential_required_fields=("api_url", "api_token"),
        excludes_loops=("snmp",),
    ),
    MonitorProtocolCode.PING.value: ProtocolSpec(
        code=MonitorProtocolCode.PING.value,
        adapter_class=PingAdapter,
        applies_to_device_types=("network", "server", "other"),
        worker_loop="ping",
        credential_required_fields=(),
        requires_credential=False,
    ),
}


DEFAULT_LOOP_INTERVALS: Dict[str, int] = {"snmp": 60, "bmc": 60, "zabbix": 60, "ping": 60}


def get_adapter_class(code: str) -> Type[MonitorAdapter]:
    return PROTOCOL_REGISTRY[code].adapter_class


def build_adapter(code: str) -> MonitorAdapter:
    return get_adapter_class(code)()


def all_protocol_codes() -> List[str]:
    return list(PROTOCOL_REGISTRY.keys())


def device_type_to_protocols(device_type) -> List[str]:
    matched: List[str] = [
        spec.code
        for spec in PROTOCOL_REGISTRY.values()
        if device_type in spec.applies_to_device_types
    ]
    if not matched:
        return [
            MonitorProtocolCode.SNMP.value,
            MonitorProtocolCode.ZABBIX.value,
            MonitorProtocolCode.PING.value,
        ]
    return matched


def protocol_required_fields(code: str) -> Tuple[str, ...]:
    spec = PROTOCOL_REGISTRY.get(code)
    if spec is None:
        return ()
    return spec.credential_required_fields


def protocol_requires_credential(code: str) -> bool:
    spec = PROTOCOL_REGISTRY.get(code)
    if spec is None:
        return True
    return spec.requires_credential


def worker_loops() -> List[str]:
    seen: List[str] = []
    for spec in PROTOCOL_REGISTRY.values():
        if spec.worker_loop not in seen:
            seen.append(spec.worker_loop)
    return seen


def protocols_for_loop(loop_name: str) -> List[str]:
    return [spec.code for spec in PROTOCOL_REGISTRY.values() if spec.worker_loop == loop_name]


def device_types_for_loop(loop_name: str) -> set:
    types: set = set()
    for spec in PROTOCOL_REGISTRY.values():
        if spec.worker_loop == loop_name:
            types.update(spec.applies_to_device_types)
    return types


def _validate_registry() -> None:
    loop_excludes_seen: Dict[str, Tuple[str, ...]] = {}
    for spec in PROTOCOL_REGISTRY.values():
        loop = spec.worker_loop
        if loop in loop_excludes_seen and loop_excludes_seen[loop] != spec.excludes_loops:
            raise ValidationError(
                f"协议注册表校验失败：同一 loop '{loop}' 下 excludes_loops 不一致 "
                f"({loop_excludes_seen[loop]} vs {spec.excludes_loops})"
            )
        loop_excludes_seen[loop] = spec.excludes_loops

    registry_order = list(PROTOCOL_REGISTRY.keys())
    credential_direct = [
        s.code for s in PROTOCOL_REGISTRY.values()
        if s.requires_credential and not s.excludes_loops
    ]
    fallback_codes = [s.code for s in PROTOCOL_REGISTRY.values() if s.excludes_loops]
    for fb in fallback_codes:
        for dr in credential_direct:
            if registry_order.index(fb) < registry_order.index(dr):
                raise ValidationError(
                    f"协议注册表校验失败：fallback 协议 '{fb}' 排在直连协议 '{dr}' 之前，"
                    f"将抢占直连探测。请将 fallback 协议移至注册表末尾。"
                )
    no_cred_codes = [s.code for s in PROTOCOL_REGISTRY.values() if not s.requires_credential]
    for nc in no_cred_codes:
        for cr in list(credential_direct) + fallback_codes:
            if registry_order.index(nc) < registry_order.index(cr):
                raise ValidationError(
                    f"协议注册表校验失败：无凭据触发源 '{nc}' 排在需凭据协议 '{cr}' 之前，"
                    f"将抢占真实探测。请将 '{nc}' 移至注册表末尾。"
                )


_validate_registry()
