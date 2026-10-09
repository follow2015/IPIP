# -*- coding: utf-8 -*-
"""`CollectedFacts` → 落库字段的适配层（决策 5 的落库侧；T-G1-1 范围）。


采集通道产出的是 `CollectedFacts`（内存对象），数据库要的是行字典。这一层是两者
之间的**唯一**转换点 —— 散在主链路里写就会出现"同一份 facts 在两处映射出不同形状"。


契约层规格原文让溯源落 `raw_info`，但该列**已被端口配置文本缓存占用**
（`switch_repo.write_port_info` 写 `{"port_info": ...}`）。2026-10-05 评审裁决
**拆列**（方案 B）：`collect_trace` 只放溯源，两列各写各的、互不知晓。


不能取标量 `meta["channel"]`。混合采集（PORTS 走 SNMP、MAC 回落 CLI）时标量只能
表达"这台设备的主通道"，用它会给 SNMP 采到的端口硬安一个 `cli` 来源 —— 这正是
守卫 `tests/services/collector/test_meta_channel_guard.py` 禁止整条链路读标量的原因。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from app.core.enums import CollectCapability
from app.services.collector.capability import cap_value
from app.services.collector.contract import (
    META_KEY_CHANNELS,
    META_KEY_COLLECTED_AT,
    META_KEY_DEGRADED_FROM,
    META_KEY_QUALITY,
    CapabilityOutcome,
)
from app.services.collector.facts import CollectedFacts

__all__ = ["attach_trace", "legacy_trace", "trace_from_facts"]

_TRACEABLE_OUTCOMES = (CapabilityOutcome.SATISFIED, CapabilityOutcome.EMPTY)


def trace_from_facts(
    facts: CollectedFacts,
    cap: CollectCapability | str = CollectCapability.PORTS,
) -> dict[str, Any] | None:
    """把 facts 里的单项采集溯源转成 ``collect_trace`` 的列值。

    返回 ``None`` 表示"没有可落库的溯源"（未产出 / 未采集），调用方**不得**为此
    造一条空溯源 —— 空溯源比没有溯源更糟：它会让"这行是谁采的"看起来已记录，
    实际无从追溯。
    """
    key = cap_value(cap)
    outcome = facts.outcomes.get(key)
    channel = (facts.meta.get(META_KEY_CHANNELS) or {}).get(key)
    if outcome not in _TRACEABLE_OUTCOMES or not channel:
        return None

    trace: dict[str, Any] = {
        "channel": channel,                      # ← per-cap 溯源（A1）
        "outcome": getattr(outcome, "value", str(outcome)),
        "via": "channels",
    }
    collected_at = facts.meta.get(META_KEY_COLLECTED_AT)
    if collected_at:
        trace["collected_at"] = collected_at

    quality = (facts.meta.get(META_KEY_QUALITY) or {}).get(key)
    if quality is not None:
        trace["quality"] = getattr(quality, "value", str(quality))

    degraded = (facts.meta.get(META_KEY_DEGRADED_FROM) or {}).get(key)
    if degraded:
        trace["degraded_from"] = degraded

    return trace


def attach_trace(
    rows: Iterable[dict],
    facts: CollectedFacts,
    cap: CollectCapability | str = CollectCapability.PORTS,
) -> list[dict[str, Any]]:
    """给待落库的端口行注入 ``collect_trace``（浅拷贝，不改入参行）。

    无溯源时**原样返回**（不写 `collect_trace: None` 键）—— 让"没采到"与
    "采到了但没溯源"在库里有区别（前者不覆盖既有值，后者才是真更新）。
    """
    trace = trace_from_facts(facts, cap)
    if trace is None:
        return [dict(row) for row in rows]
    return [{**row, "collect_trace": dict(trace)} for row in rows]


def legacy_trace(
    channel: str = "cli",
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """老路径（`SwitchInfoService` 直采）的溯源。

    与通道层 trace 同形状，只多 ``via="legacy"`` 标记 —— 它让两件事可查：
    ① 这行数据到底由谁写入；② 灰度期统计"还有多少行是老路径产的"。

    [WARN] 老路径是 SSH/CLI 直采，故 ``channel`` 固定为 ``"cli"``；``quality`` 不写
    —— 老路径没有质量分级的概念，凭空编一个 ``full`` 会让灰度期没法用质量字段
    区分两条路径的产出。
    """
    stamp = now or datetime.now(timezone.utc)
    return {
        "channel": channel,
        "via": "legacy",
        "collected_at": stamp.isoformat(),
    }
