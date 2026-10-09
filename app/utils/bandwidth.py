# -*- coding: utf-8 -*-
"""带宽换算工具（后端单一实现）

设计口径（`docs/design/G1-线路管理-数据模型设计文档-20260928.md` §5.1）：

- **底存恒为绝对 Mbps**（`circuits.bandwidth_mbps`），是唯一真源；
- `bandwidth_step`（1000 = SI 十进制 / 1024 = IEC 二进制）**只影响展示与输入换算**，
  不改变底存值。可比较、可聚合的属性来自底存，与步进无关；
- 步进差异是**合同计量口径**，跟线路走，不是全局设置。

**前端另有一份 TS 实现**（`BandwidthInput.tsx`）。两份必须由判据钉住，否则必然漂移
（本仓已有 `backup_type` 前后端 parity 门禁先例 `tests/test_backup_type_provenance.py`）。
"""
from __future__ import annotations

from typing import Optional, Tuple

from app.core.enums import BANDWIDTH_STEP_IEC, BANDWIDTH_STEP_SI

_UNITS: Tuple[str, ...] = ("M", "G", "T", "P")

_VALID_STEPS = (BANDWIDTH_STEP_SI, BANDWIDTH_STEP_IEC)


def _normalize_step(step: Optional[int]) -> int:
    """把步进归一到合法值，非法值回落 SI（1000）。

    为什么不抛异常：展示层对一个脏步进抛错会让整个列表页 500，而回落只会让
    这一行显示成十进制口径。带宽的**真值**在底存里，不受影响。
    """
    if step in _VALID_STEPS:
        return step
    return BANDWIDTH_STEP_SI


def format_bandwidth(mbps: Optional[int], step: Optional[int] = None) -> str:
    """把绝对 Mbps 格式化为带单位的展示串。

    Args:
        mbps: 绝对带宽（Mbps）。为 None 或 <= 0 时返回空串。
        step: 进位步进（1000 / 1024）。None 或非法值按 1000 处理。

    Returns:
        形如 ``"10 G"`` / ``"1000 M"`` / ``"97.6562 G"`` 的串。

    精度取**六位有效数字**（``%.6g``）：100000 Mbps @1024 得 ``97.6562 G``
    而非 ``97.65625 G``。这是判据 AC-C-30 钉死的口径，改精度会让前后端对不上。

    不足一级不升级：1000 Mbps @1024 仍是 ``1000 M``（AC-C-18）——1024 进制下
    1000 还没到 1 G，升级成 ``0.976562 G`` 反而更难读，也和合同口径不一致。
    """
    if mbps is None:
        return ""
    st = _normalize_step(step)
    try:
        value = float(mbps)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""

    idx = 0
    while value >= st and idx < len(_UNITS) - 1:
        value /= st
        idx += 1
    return f"{value:.6g} {_UNITS[idx]}"


def parse_bandwidth(value: float, unit: str, step: Optional[int] = None) -> int:
    """把「数值 + 单位」换算为绝对 Mbps。

    Args:
        value: 数值，如 ``10``。
        unit: 单位，``M`` / ``G`` / ``T`` / ``P``（大小写不敏感）。
        step: 进位步进（1000 / 1024）。None 或非法值按 1000 处理。

    Returns:
        绝对 Mbps（取整）。

    Raises:
        ValueError: 单位不在阶梯内，或数值为负。
    """
    st = _normalize_step(step)
    u = (unit or "").strip().upper()
    if u not in _UNITS:
        raise ValueError(f"不支持的带宽单位：{unit!r}，可选 {list(_UNITS)}")
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"带宽数值非法：{value!r}") from exc
    if v < 0:
        raise ValueError("带宽不能为负")

    return int(round(v * (st ** _UNITS.index(u))))


def bandwidth_display_pair(mbps: Optional[int], step: Optional[int] = None) -> dict:
    """返回 API 下发的带宽二元组。

    同时下发**绝对值**与**格式化串**：前端无需重复实现换算即可直接展示，
    而需要比较/聚合的场景仍取绝对值（设计文档 §6「带宽入参约定」）。
    """
    return {
        "bandwidth_mbps": mbps,
        "bandwidth_display": format_bandwidth(mbps, step),
    }
