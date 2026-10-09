# -*- coding: utf-8 -*-
"""通道层运行时装配（T-G1 接入点）。

把"开关 → 通道实例 → 选择器"接起来，业务侧一行调用即可；通道怎么装配是通道层
自己的事，业务侧只该看到"这轮走不走通道、走哪些通道"。**独立成模块的理由**：
`SwitchInfoService` 属业务编排层，不该 import `CliChannel` / `SnmpChannel` 的构造细节
（那会让通道的依赖变化扩散到业务层）。


| 开关 | 默认 | 作用 |
|---|---|---|
| `SCAN_CHANNEL_ENABLED` | False | 通道层**总开关**；关掉即回 G6 老路径（零发版回退） |
| `SCAN_CHANNEL_AUTO_ENABLED` | False | **自动扫描**（调度触发）是否也走通道层；手动/API 触发只看总开关 |

两开关默认皆 False ⇒ **本模块接入本身零行为变更**。


设计文档 §0.4 的路线是 `G1 旁路灰度 → 影子模式(A3) 跑全量 diff → G2 扩大灰度`。
本轮按此落地：通道层与老路径**并行采集**，比对结果并留痕，**落库仍走老路径**。
两条理由：

1. 老路径的 `parsed_ports` 还承担 `_sync_port_ips` / `_sync_vlan_trunk_bases` 两次
   附属同步，而 `port_rows` 不含 trunk 信息 —— 直接接管会**静默丢功能**；
2. 影子模式零数据风险，且恰好为下一阶段的"真机测试"提供 diff 数据。

接管只需一处改动：把 `shadow_compare` 的返回结果用于落库，见 `SwitchInfoService`
的 `_shadow_compare_channels` docstring。
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from app.core.enums import DeviceSubtypeCode
from app.services.channel_config import (
    ChannelRuntimeConfig,
    load_channel_runtime_config as _load_channel_runtime_config,
)
from app.services.collector.base_channel import BaseChannel
from app.services.collector.cli_channel import CliChannel
from app.services.collector.selector import ChannelSelector
from app.services.collector.snmp_channel import SnmpChannel
from app.utils.logging import get_logger

logger = get_logger(__name__)

_CONFIG_CACHE_TTL = 5.0

_cache_lock = threading.Lock()
_cache: tuple[float, ChannelRuntimeConfig] | None = None


def reset_config_cache() -> None:
    """清空开关缓存（单测用；运维侧不需要 —— 5s 后自然过期）。"""
    global _cache
    with _cache_lock:
        _cache = None


def load_config_cached() -> ChannelRuntimeConfig:
    """读取开关快照（进程内 5s 缓存）。"""
    global _cache
    now = time.monotonic()
    with _cache_lock:
        if _cache is not None and now - _cache[0] < _CONFIG_CACHE_TTL:
            return _cache[1]
    cfg = _load_channel_runtime_config()
    with _cache_lock:
        _cache = (now, cfg)
    return cfg

_ROLE_BY_SUBTYPE = {
    DeviceSubtypeCode.FIREWALL.value: "firewall",
}


def resolve_device_role(switch: Any) -> str | None:
    """从设备画像推导通道层角色（``firewall`` / ``l2_switch`` / ``None``）。

    - 防火墙（``device_subtype == "firewall"``）：不维护转发 MAC 表 → 跳过 MAC；
    - 二层接入交换机（``layer == 2``）：没有路由表 → 跳过 ROUTES。

    画像字段缺失/异常一律返回 ``None``（= 不做角色过滤），**不得**让画像问题
    影响采集 —— 这与"灰度白名单写错只丢一台灰度"是同一条纪律。
    """
    device = getattr(switch, "device", None)
    if device is None:
        return None
    subtype = (getattr(device, "device_subtype", "") or "").strip().lower()
    if not subtype:
        return None
    if subtype in _ROLE_BY_SUBTYPE:
        return _ROLE_BY_SUBTYPE[subtype]
    try:
        layer = getattr(device, "layer", None)
    except Exception as exc:  # noqa: BLE001 —— 画像读取失败不致命（退化为不过滤）
        logger.debug("设备角色推导失败（按不过滤处理）：%s", exc)
        return None
    return "l2_switch" if layer == 2 else None


def build_channels(
    cfg: ChannelRuntimeConfig,
    *,
    device_id: int | None = None,
    room_id: int | None = None,
    virtual_room_id: int | None = None,
    ssh_manager: Any | None = None,
    switch_repo: Any | None = None,
) -> list[BaseChannel]:
    """按开关快照装配通道实例（含优先级排序与 G6 回退过滤）。

    ``cfg.allowed_channels`` 是 G6 的回退点：总开关关闭时返回空列表，调用方据空
    走老路径；这里再按它做优先级排序与过滤，两处口径一致。
    """
    candidates: list[BaseChannel] = [
        CliChannel(ssh_manager=ssh_manager, switch_repo=switch_repo),
    ]
    if cfg.snmp_allowed(device_id, room_id, virtual_room_id):
        candidates.append(SnmpChannel(snapshot_enabled=cfg.snmp_snapshot_enabled))

    allowed = cfg.allowed_channels([ch.code for ch in candidates])
    if not allowed:
        return []
    by_code = {ch.code: ch for ch in candidates}
    return [by_code[code] for code in allowed if code in by_code]


def build_selector(
    cfg: ChannelRuntimeConfig,
    *,
    device_id: int | None = None,
    room_id: int | None = None,
    virtual_room_id: int | None = None,
    ssh_manager: Any | None = None,
    switch_repo: Any | None = None,
    role_for: Callable[[int], str | None] | None = None,
) -> ChannelSelector | None:
    """装配选择器；无可用通道时返回 ``None``。"""
    channels = build_channels(
        cfg, device_id=device_id, room_id=room_id, virtual_room_id=virtual_room_id,
        ssh_manager=ssh_manager, switch_repo=switch_repo,
    )
    if not channels:
        return None
    return ChannelSelector(channels, role_resolver=role_for, **cfg.selector_kwargs())


def selector_for(
    switch: Any,
    *,
    ssh_manager: Any | None = None,
    switch_repo: Any | None = None,
    triggered_by_auto: bool = False,
    virtual_room_id: int | None = None,
    config_reader: Callable[[], ChannelRuntimeConfig] | None = None,
) -> ChannelSelector | None:
    """本轮是否走通道层；不走返回 ``None``（调用方走既有 CLI 直采路径）。

    :param triggered_by_auto: 本次来自**自动扫描**（调度）时为真 —— 除总开关外
        还要求 `SCAN_CHANNEL_AUTO_ENABLED`（G3 才打开），手动/API 触发不看它。
    :param virtual_room_id: 调用方所处的**虚拟机房**上下文（G2 跨机房灰度维度）。
    :param config_reader: 测试可注入的开关读取器，避免为单测起 Redis/app context。
        **注入了就不走缓存**（单测要可控）。
    """
    try:
        cfg = (config_reader or load_config_cached)()
    except Exception as exc:  # noqa: BLE001 —— 开关读不到不该影响采集（退化为老路径）
        logger.warning("通道开关读取失败，本轮走 CLI 直采：%s", exc)
        return None

    if not cfg.enabled:
        return None
    if triggered_by_auto and not cfg.auto_enabled:
        return None

    device_id = getattr(switch, "device_id", None)
    device = getattr(switch, "device", None)
    room_id = None
    if device is not None:
        cabinet = getattr(device, "cabinet", None)
        room_id = getattr(cabinet, "room_id", None) if cabinet is not None else None

    selector = build_selector(
        cfg,
        device_id=device_id,
        room_id=room_id,
        virtual_room_id=virtual_room_id,
        ssh_manager=ssh_manager,
        switch_repo=switch_repo,
        role_for=lambda _device_id: resolve_device_role(switch),
    )
    if selector is None:
        logger.info("通道层总开关已开，但本设备无可用通道（检查 SCAN_CHANNEL_PRIORITY/SNMP 白名单）")
    return selector


def selector_for_snmp_takeover(
    switch: Any,
    *,
    ssh_manager: Any | None = None,
    switch_repo: Any | None = None,
    triggered_by_auto: bool = False,
    virtual_room_id: int | None = None,
    config_reader: Callable[[], ChannelRuntimeConfig] | None = None,
) -> ChannelSelector | None:
    """**G1.5 接管专用**入口：只在「无 SSH 且 SNMP 被白名单放行」时返回选择器。

    为什么单独一个入口，而不是让调用方自己拼几个 if：接管范围收窄是**决策**
    （设计文档《接管落库与无SSH设备主路径设计》修订 R1），把它写成单一判据，
    后来者才不会"顺手放宽"。

    R1 的理由（要点）：有 SSH 设备的 CLI 老路径工作正常，把它切到通道层属
    "换实现重做同一件事"，收益是架构统一、代价是全部 CLI 回归面；**无 SSH 设备
    才是唯一真缺口**（当前完全采不到端口）。

    返回 ``None`` 的四种情形，调用方一律回退既有 CLI 直采路径：
    1. 设备**有 SSH** ⇒ 不接管（R1 收窄；这类设备的接管留 G2 子项）；
    2. 总开关关（`SCAN_CHANNEL_ENABLED=false`，默认）；
    3. 自动扫描触发但 `SCAN_CHANNEL_AUTO_ENABLED` 未开（G3 才放开）；
    4. SNMP **未被白名单放行**（设备/机房/虚拟机房三维）⇒ 无 SSH 设备没有任何
       可用通道，接管只会产出空结果。
    """
    if getattr(switch, "has_ssh", False):
        return None

    try:
        cfg = (config_reader or load_config_cached)()
    except Exception as exc:  # noqa: BLE001 —— 开关读不到不该影响采集（退化为老路径）
        logger.warning("通道开关读取失败，本轮走 CLI 直采：%s", exc)
        return None

    if not cfg.enabled:
        return None
    if triggered_by_auto and not cfg.auto_enabled:
        return None

    device_id = getattr(switch, "device_id", None)
    device = getattr(switch, "device", None)
    cabinet = getattr(device, "cabinet", None) if device is not None else None
    room_id = getattr(cabinet, "room_id", None) if cabinet is not None else None

    if not cfg.snmp_allowed(device_id, room_id):
        return None

    if cfg.snmp_subtypes:
        device = getattr(switch, "device", None)
        subtype = str(getattr(device, "device_subtype", "") or "").strip().lower()
        if subtype not in cfg.snmp_subtypes:
            return None

    return build_selector(
        cfg,
        device_id=device_id,
        room_id=room_id,
        virtual_room_id=virtual_room_id,
        ssh_manager=ssh_manager,
        switch_repo=switch_repo,
        role_for=lambda _device_id: resolve_device_role(switch),
    )


def diff_port_rows(
    legacy_rows: Sequence[dict],
    channel_rows: Sequence[dict],
) -> dict[str, Any]:
    """比对老路径与通道层产出的端口行（影子模式的判据）。

    只比**共同字段**：``port_rows`` 的字段集合是两侧共用实现（`port_rows.py`）保证的，
    但老路径的 dict 可能多带附属键（如 `id`），按共同字段比才不会被噪音淹没。

    返回 ``{same, only_legacy, only_channel, field_mismatches}``；``same=True`` 表示
    两侧逐行逐字段一致（影子模式通过）。
    """
    def _index(rows: Sequence[dict]) -> dict[str, dict]:
        return {str(r.get("port_name") or r.get("port")): r for r in rows}

    left, right = _index(legacy_rows), _index(channel_rows)
    only_legacy = sorted(set(left) - set(right))
    only_channel = sorted(set(right) - set(left))
    mismatches: list[dict[str, Any]] = []
    for key in sorted(set(left) & set(right)):
        a, b = left[key], right[key]
        for field in sorted(set(a) & set(b)):
            if a[field] != b[field]:
                mismatches.append({
                    "port": key, "field": field,
                    "legacy": a[field], "channel": b[field],
                })
    return {
        "same": not only_legacy and not only_channel and not mismatches,
        "only_legacy": only_legacy,
        "only_channel": only_channel,
        "field_mismatches": mismatches,
    }


__all__ = [
    "build_channels",
    "build_selector",
    "diff_port_rows",
    "load_config_cached",
    "reset_config_cache",
    "resolve_device_role",
    "selector_for",
    "selector_for_snmp_takeover",
]
