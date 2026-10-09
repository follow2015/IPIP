# -*- coding: utf-8 -*-
"""多通道采集 · 契约层常量与能力结果四态（T0.3）。

规格：``docs/spec/多通道采集-契约层规格-T0.3.md`` §3.2（精确定义）、决策 1（F8）。

本模块**只**放枚举与契约常量：不含 ``CollectedFacts``（在 ``facts.py``），
不含任何通道实现（T0.4 的 ``base_channel.py``）。刻意保持**零外部依赖**
（仅标准库）：契约层是包内最底层，任何运行期依赖都会把它的可测试性拖下水。

存在理由（为什么要四态而不是布尔/判空）：

- 旧口径用「结果是否为空」判断要不要补采，于是"防火墙没有 MAC 表"这种
  **确定答案**被当成失败 —— 每轮补采、每轮记 error、还累积熔断失败数。
- 四态把「通道支持且成功但确实为空」(``EMPTY``) 与「本通道不声明该能力」
  (``UNSUPPORTED``) 与「声明了但执行失败」(``FAILED``) 分开：前两者都是
  **确定答案**，不再补采；只有 ``FAILED`` 触发补采与熔断计数。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


class CapabilityOutcome(str, Enum):
    """单个采集能力的执行结果四态（唯一真源字段 ``CollectedFacts.outcomes``）。

    SATISFIED   : 采到非空数据（list / dict 非空）。
    EMPTY       : 通道声明了该能力、执行也成功，但结果确实为空。
                  这是**确定答案**，不补采、不记 error、不累积熔断失败数
                  （防火墙无 MAC 表即此态，见 AC-9）。
    UNSUPPORTED : 本通道未声明该能力（矩阵为 ``NONE`` 或调用方显式请求了
                  未声明能力）。同样是确定答案 —— 它是"按角色声明 NONE 后
                  选择器自动跳过"能落到代码的唯一前提。
    FAILED      : 声明了但执行失败（超时 / 认证 / 解析抛错）。唯一会记
                  ``meta["errors"]`` 并累积熔断失败数的态。
    """

    SATISFIED = "satisfied"
    EMPTY = "empty"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


OUTCOME_PRIORITY: dict[CapabilityOutcome, int] = {
    CapabilityOutcome.SATISFIED: 4,
    CapabilityOutcome.EMPTY: 3,
    CapabilityOutcome.FAILED: 2,
    CapabilityOutcome.UNSUPPORTED: 1,
}

SATISFYING_OUTCOMES: frozenset[CapabilityOutcome] = frozenset(
    {CapabilityOutcome.SATISFIED, CapabilityOutcome.EMPTY}
)

META_KEY_CHANNEL = "channel"
META_KEY_CHANNELS = "channels"
META_KEY_REQUESTED = "requested"
META_KEY_SATISFIED = "satisfied"
META_KEY_UNSUPPORTED = "unsupported"
META_KEY_FAILED = "failed"
META_KEY_QUALITY = "quality"
META_KEY_ELAPSED_MS = "elapsed_ms"
META_KEY_COLLECTED_AT = "collected_at"
META_KEY_DEGRADED_FROM = "degraded_from"
META_KEY_ERROR = "error"
META_KEY_ERRORS = "errors"
META_KEY_BUDGET_EXHAUSTED = "budget_exhausted"
META_KEY_SNMP_SECURITY = "snmp_security"

META_DERIVED_KEYS: frozenset[str] = frozenset(
    {META_KEY_SATISFIED, META_KEY_UNSUPPORTED, META_KEY_FAILED}
)


def is_empty_value(value: Any) -> bool:
    """判定采集结果是否为"空"（规格 §3.4 的 ``_is_empty``，唯一实现）。

    ``None`` 与空的 ``list`` / ``dict`` 都算空。非容器标量（如版本号字符串）
    只要有值即为非空 —— 它们不像 list/dict 那样存在"空容器 vs 有内容"的歧义。

    放在契约层而不是某个模块私有的原因：``facts.merge()`` 的字段合并与 T0.4
    ``collect()`` 模板的 outcome 判定用的是**同一条口径**；两处各写一份
    就是典型的"同一语义两个真相源"，口径一改必然漂移。
    """
    if value is None:
        return True
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False



_MERGE_SELF_FIRST: tuple[str, ...] = (
    META_KEY_COLLECTED_AT,
    META_KEY_DEGRADED_FROM,
    META_KEY_ERROR,
)


def merge_meta(
    mine: Mapping[str, Any],
    theirs: Mapping[str, Any],
    *,
    channels: Mapping[str, str] | None = None,
) -> dict:
    """按 §3.3 规则表合并两份 ``meta``，返回**新** dict（不改入参）。

    ``channels`` 是调用方按 **outcome 胜者所在那一侧**挑好的 per-capability 溯源
    （``{cap: channel_code}``）。它必须由胜者侧决定而不是"最后写入者"决定 —— 否则
    混合采集里被降级掉的能力会把自己的通道名留在台账上（B1 / AC-30）。

    默认口径是 ``other`` 覆盖（``snmp_security`` 及其余键）：双通道串行时"最后生效
    通道"的状态优先，这是既有 ``{**mine, **theirs}`` 的语义，只对语义会丢的那几个
    键做特例。
    """
    merged: dict[str, Any] = {**mine, **theirs}

    for key in (META_KEY_QUALITY, META_KEY_ERRORS):
        per_key = {
            **(mine.get(key) or {}),
            **(theirs.get(key) or {}),
        }
        if per_key:
            merged[key] = per_key

    channels_map = {
        **(mine.get(META_KEY_CHANNELS) or {}),
        **(theirs.get(META_KEY_CHANNELS) or {}),
        **(channels or {}),          # 胜者侧优先，覆盖上面的"最后写入者"
    }
    if channels_map:
        merged[META_KEY_CHANNELS] = channels_map

    requested = sorted(
        set(mine.get(META_KEY_REQUESTED) or []) | set(theirs.get(META_KEY_REQUESTED) or [])
    )
    if requested:
        merged[META_KEY_REQUESTED] = requested

    if META_KEY_BUDGET_EXHAUSTED in mine or META_KEY_BUDGET_EXHAUSTED in theirs:
        merged[META_KEY_BUDGET_EXHAUSTED] = bool(
            mine.get(META_KEY_BUDGET_EXHAUSTED) or theirs.get(META_KEY_BUDGET_EXHAUSTED)
        )

    elapsed = [
        value
        for value in (mine.get(META_KEY_ELAPSED_MS), theirs.get(META_KEY_ELAPSED_MS))
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    if elapsed:
        total = sum(elapsed)
        merged[META_KEY_ELAPSED_MS] = (
            int(total) if all(isinstance(value, int) for value in elapsed) else total
        )

    for key in _MERGE_SELF_FIRST:
        value = mine.get(key)
        if value is None or value == "":
            value = theirs.get(key)
        if value is not None and value != "":
            merged[key] = value
        else:
            merged.pop(key, None)

    for key in META_DERIVED_KEYS:
        merged.pop(key, None)
    return merged
