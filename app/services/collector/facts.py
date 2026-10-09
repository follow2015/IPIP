# -*- coding: utf-8 -*-
"""多通道采集 · 统一产出 ``CollectedFacts``（T0.3）。

规格：``docs/spec/多通道采集-契约层规格-T0.3.md`` §3.3（精确定义）、§4（形状偏差）。

职责边界：本模块只有 ``CollectedFacts`` 及其方法；能力/质量的枚举在
``app.core.enums``，结果四态与契约常量在同包的 ``contract.py``。

两条贯穿全局的约束（违反即视为缺陷，均有守卫盯）：

1. ``outcomes`` 是能力结果的**唯一真源**；``meta`` 的 ``satisfied`` /
   ``unsupported`` / ``failed`` 三键只能由 ``refresh_meta()`` 从它派生。直接写
   即 F8 的"双真源"复发（AST 守卫见 tests/services/collector/）。
2. ``vendor`` 是厂商私有项的**唯一受控出口**，键必须带两级命名空间，且刻意
   **不参与**字段级 ``get()`` / ``merge()`` 合并语义 —— 只做 dict 浅合并。
   这一条正是决策 2（F9）想消除的"特殊分支"，不得重新引入。
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import copy
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import CollectCapability, QualityLevel
from app.services.collector.contract import (
    META_KEY_CHANNELS,
    META_KEY_ERRORS,
    META_KEY_FAILED,
    META_KEY_QUALITY,
    META_KEY_SATISFIED,
    META_KEY_UNSUPPORTED,
    OUTCOME_PRIORITY,
    SATISFYING_OUTCOMES,
    CapabilityOutcome,
    is_empty_value,
    merge_meta,
)

_CAP_FIELD: dict[CollectCapability, str] = {
    CollectCapability.PORTS: "ports",
    CollectCapability.ARP: "arps",
    CollectCapability.MAC: "macs",
    CollectCapability.ROUTES: "routes",
    CollectCapability.LLDP: "lldp",
    CollectCapability.DEVICE_INFO: "device",
    CollectCapability.OPTICS: "optics",
    CollectCapability.COUNTERS: "counters",
    CollectCapability.VLANS: "vlans",
    CollectCapability.LAGS: "lags",
}

CAP_FIELD_BY_VALUE: dict[str, str] = {c.value: f for c, f in _CAP_FIELD.items()}

_SIDE_SELF = "self"
_SIDE_OTHER = "other"


def _key(cap: CollectCapability | str) -> str:
    """把能力归一为 ``outcomes`` / ``meta`` 里用的字符串键。"""
    return cap.value if isinstance(cap, CollectCapability) else str(cap)


def _as_outcome(value: Any) -> CapabilityOutcome | None:
    """把 ``outcomes`` 里的值归一为枚举；非枚举字符串按 value 反查。

    容忍裸字符串是为了让"从 JSON / 旧管道恢复的 facts"也能被正确判定；
    **无法归一的值一律返回 None**（等价于"无确定答案"），而不是猜一个态 ——
    猜错方向（把未知值当成 SATISFIED）会导致真实缺口被静默吞掉。
    """
    if isinstance(value, CapabilityOutcome):
        return value
    if isinstance(value, str):
        try:
            return CapabilityOutcome(value)
        except ValueError:  # 未知/拼错的 outcome 字符串
            return None
    return None


def _coerce_quality(level: QualityLevel | str) -> str:
    """把质量档位归一为枚举 value；未知档位**明确报错**（参考 T-V3-2 取向）。"""
    if isinstance(level, QualityLevel):
        return level.value
    return QualityLevel(level).value


@dataclass
class CollectedFacts:
    """一次采集的统一产出。所有通道必须输出此结构。

    ``ports`` / ``arps`` / ``macs`` / ``routes`` 的**键名**与现有 ``port_rows``
    及 ``scan_context`` 的 ``Parsed*`` 数据类一致（偏差见规格 §4），使下游消费
    无需改动字段语义。注意三点实测偏差，适配层需注意：

    - ``ports`` 行**不含** ``device_id``：CLI 侧 ``port_rows`` 带、SNMP 侧不带，
      契约层统一不带，由 ``collect(device_id)`` 的入参与 facts_adapter 注入。
    - ``arps`` / ``macs`` / ``routes`` 是 ``list[dict]``，而 ``SwitchContext``
      的同名字段是 **dataclass 实例**：类型不同，字段名一致。
    - ``SwitchContext`` 根本没有 ``ports`` 字段，故端口不走 ``SwitchContext``。
    """

    ports: list[dict] = field(default_factory=list)
    arps: list[dict] = field(default_factory=list)
    macs: list[dict] = field(default_factory=list)
    routes: list[dict] = field(default_factory=list)
    lldp: list[dict] = field(default_factory=list)
    device: dict | None = None
    optics: list[dict] = field(default_factory=list)
    counters: list[dict] = field(default_factory=list)
    vlans: list[dict] = field(default_factory=list)
    lags: list[dict] = field(default_factory=list)
    vendor: dict[str, dict] = field(default_factory=dict)
    outcomes: dict[str, CapabilityOutcome] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def get(self, cap: CollectCapability | str) -> list[dict] | dict | None:
        """按 ``_CAP_FIELD`` 取字段值。

        统一走 ``_CAP_FIELD`` 映射，无特殊分支（``VLANS`` 于 2026-10-08 加回后同样
        走这条路）。未知能力抛 ``ValueError``：
        那是调用方的编码错误，静默返回 ``None`` 会让它退化成"某个能力悄悄
        永远采不到"。
        """
        field_name = CAP_FIELD_BY_VALUE.get(_key(cap))
        if field_name is None:
            raise ValueError(f"未知采集能力：{cap!r}")
        return getattr(self, field_name)

    def is_satisfied(self, cap: CollectCapability | str) -> bool:
        """该能力是否已得到**确定答案**（含"确实为空"）—— 是则不再补采。"""
        outcome = _as_outcome(self.outcomes.get(_key(cap)))
        return outcome in SATISFYING_OUTCOMES

    def needs_fallback(self, cap: CollectCapability | str) -> bool:
        """是否需要其它通道补采 —— 只有 ``FAILED`` 需要（F8 的核心修复）。"""
        return _as_outcome(self.outcomes.get(_key(cap))) is CapabilityOutcome.FAILED

    def refresh_meta(
        self,
        quality_matrix: Mapping[Any, Any] | None = None,
    ) -> None:
        """由 ``outcomes`` 重写 ``meta`` 的派生键（唯一写入点）。

        ``quality_matrix`` 为通道的能力矩阵（``{cap: QualityLevel}``，键可为枚举
        或字符串）。矩阵值写入 ``meta["quality"]`` 后，**``FAILED`` 的能力一律降为
        ``none``** —— 失败的能力在本次结果里没有任何质量可言，下游据此拒绝落库
        （见 AC-21：非 ``SATISFIED`` 的结果不得进入端口三步删除）。

        ``collect()`` 返回前与 ``merge()`` 结束后必须调用，派生键才不会过期。
        三个派生键是**重写**而非"补齐"：即便调用方手工往 ``meta`` 塞过值，也会被
        outcomes 覆盖 —— 这正是防"双真源"的那道闸。
        """
        quality = dict(self.meta.get(META_KEY_QUALITY) or {})
        if quality_matrix:
            for cap, level in quality_matrix.items():
                quality[_key(cap)] = _coerce_quality(level)

        satisfied: list[str] = []
        unsupported: list[str] = []
        failed: list[str] = []
        for key, raw in self.outcomes.items():
            outcome = _as_outcome(raw)
            if outcome in SATISFYING_OUTCOMES:
                satisfied.append(key)
            elif outcome is CapabilityOutcome.UNSUPPORTED:
                unsupported.append(key)
            elif outcome is CapabilityOutcome.FAILED:
                failed.append(key)

        failed_set = frozenset(failed)
        quality = {
            key: (QualityLevel.NONE.value if key in failed_set else level)
            for key, level in quality.items()
        }
        for key in failed_set:
            quality.setdefault(key, QualityLevel.NONE.value)

        self.meta[META_KEY_SATISFIED] = satisfied
        self.meta[META_KEY_UNSUPPORTED] = unsupported
        self.meta[META_KEY_FAILED] = failed
        self.meta[META_KEY_QUALITY] = quality

    def merge(self, other: "CollectedFacts") -> "CollectedFacts":
        """合并两份 facts，返回**新**对象（不改 self / other）。

        五条合并规则：

        1. ``outcomes``：按 ``OUTCOME_PRIORITY`` 择优（``SATISFIED > EMPTY >
           FAILED > UNSUPPORTED``，AC-11）；键按 capability value 排序写入，使派生
           出来的三键顺序稳定。**并记录胜者来自哪一侧**（``winners``）—— 见规则 2。
        2. 字段：**以 outcome 胜者所在那一侧为准**（B3）。字段与 outcome 必须同源，
           否则会出现"outcome 说 A 通道的确定答案胜出、数据却是 B 通道那一份"的
           自相矛盾结果。胜者侧值为空时才退到"非空覆盖"（规则 1 的旧口径），避免
           把已有数据丢掉。两者都不是追加 —— 同一能力只应有一个权威结果。
        3. ``vendor``：只做 dict 浅合并，**不**参与上面的字段级语义（O6 约束 3）。
        4. ``meta``：**逐键**合并（B2），规则见 ``contract.merge_meta``；``channels``
           按规则 1 的 ``winners`` 取胜者侧的值（B1 / AC-30）。
        5. 结束时必须调 ``refresh_meta()``，派生键才不会过期。``errors`` 里已被别的
           通道救回的能力条目会被剔除：outcome 说了算。
        """
        merged = CollectedFacts()
        winners: dict[str, str] = {}

        for key in sorted(set(self.outcomes) | set(other.outcomes)):
            candidates = [
                outcome
                for outcome in (
                    _as_outcome(self.outcomes.get(key)),
                    _as_outcome(other.outcomes.get(key)),
                )
                if outcome is not None
            ]
            if not candidates:
                continue
            best = max(candidates, key=lambda o: OUTCOME_PRIORITY[o])
            merged.outcomes[key] = best
            winners[key] = (
                _SIDE_OTHER if _as_outcome(other.outcomes.get(key)) is best else _SIDE_SELF
            )

        for cap, field_name in _CAP_FIELD.items():
            current = getattr(self, field_name)
            incoming = getattr(other, field_name)
            side = winners.get(_key(cap))
            if side == _SIDE_SELF:
                value = current
            elif side == _SIDE_OTHER:
                value = incoming
            else:
                value = incoming if not is_empty_value(incoming) else current
            setattr(merged, field_name, copy(value) if isinstance(value, (list, dict)) else value)

        merged.vendor = {**self.vendor, **other.vendor}

        channels: dict[str, str] = {}
        for key, side in winners.items():
            source = other if side == _SIDE_OTHER else self
            code = (source.meta.get(META_KEY_CHANNELS) or {}).get(key)
            if code:
                channels[key] = code
        merged.meta = merge_meta(self.meta, other.meta, channels=channels)

        remaining = {
            key: value
            for key, value in (merged.meta.get(META_KEY_ERRORS) or {}).items()
            if merged.needs_fallback(key)
        }
        if remaining:
            merged.meta[META_KEY_ERRORS] = remaining
        else:
            merged.meta.pop(META_KEY_ERRORS, None)

        merged.refresh_meta()
        return merged


__all__ = ["CAP_FIELD_BY_VALUE", "CollectedFacts"]
