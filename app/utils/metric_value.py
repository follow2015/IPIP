# -*- coding: utf-8 -*-
"""指标值 → 数值的解析口径（`value_num` 派生列的唯一实现）。

为什么单独开一个模块
--------------------
``device_metric_timeseries.value`` 是 ``VARCHAR(255)``：它既承载数值
（``"37.5"``、``"85%"``），也承载状态词（``"up"``、``"down"``、``"port 3 down"``）。
聚合（AVG/MIN/MAX）必须在**数值列**上做，否则每次都要 ``CAST(value AS ...)``
全表扫，且非数值行会静默变 0。故增设 ``value_num`` 派生列，本模块是它的
**唯一填充口径**（多份实现各说各话是本仓反复踩的坑）。

为什么是**严格**解析而不是宽松抓取
----------------------------------
``app/services/ai/baseline_service.py::_parse_value`` 用的是
``re.search(r"-?\\d+\\.?\\d*", raw)`` —— 它会在字符串里**任意位置**抓第一个数字。
这对"尽力读出一个数"是合适的，但用作聚合列会静默出错：

- ``"port 3 down"`` → 宽松得 ``3.0``，严格得 ``None``；
- 前者会让某个端口状态指标的 ``MIN`` 变成 3，而 3 既不是任何真实指标值，
  也不会报错 —— 正是最难发现的那一类错。

聚合列的可预测性 > 覆盖率：宁可填 NULL（AVG 自动跳过），不可填一个来历不明的数。
故本模块**不复用** ``_parse_value``，也不改动它（它的调用方是既有基线口径，
改语义属于行为变更，留到 B4 基线改走聚合层时自然废弃）。

允许的形态
----------
- ``"37.5"`` / ``"-3"`` / ``".5"`` / ``"1e3"`` → 对应数值；
- ``"85%"`` → ``85.0``（百分号是**唯一**被容忍的后缀，监控指标里极其常见，
  且去掉它不改变数值语义）；
- 首尾空白容忍；
- 其余（含 ``"up"``、``"1.2.3"``、``"N/A"``、``"port 3 down"``、空串）→ ``None``。
"""
from __future__ import annotations

import re
from typing import Optional

_NUMERIC_RE = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*%?\s*$")


def parse_metric_value_num(raw) -> Optional[float]:
    """把指标原始值解析为数值；非数值返回 ``None``（**不抛异常**）。

    Args:
        raw: ``device_metric_timeseries.value`` 的原始字符串（也容忍数值入参）。

    Returns:
        解析成功返回 ``float``；非数值 / ``None`` / 空串一律返回 ``None``。
        调用方**不需要** try/except —— 少一处吞异常就少一处静默偏差。
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    m = _NUMERIC_RE.match(str(raw))
    if m is None:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def variance_from_sum_sq(
    sum_sq: Optional[float],
    numeric_count: int,
    mean: Optional[float],
    *,
    sample: bool = True,
) -> Optional[float]:
    """由「平方和 + 样本数 + 均值」还原方差（**无需原始样本点**）。

    这是聚合层能承载波动性特征的关键：``hourly`` / ``daily`` 只存
    ``sum_sq`` / ``numeric_count`` / ``avg_value``，不存明细，故方差只能这样算。

    推导（总体方差）：
        Var = E[x²] − (E[x])² = (Σx²)/n − mean²

    样本方差（``sample=True``，默认）再乘 ``n/(n−1)`` 做无偏修正。

    **为什么必须存 numeric_count 而不能复用 sample_count**：
    ``AVG(value_num)`` 忽略 NULL、``COUNT(*)`` 不忽略 ⇒ 两者仅在
    "整桶全是数值或全是非数值"时才相等。用错分母会让方差静默偏小。

    Args:
        sum_sq: Σ(x²)，来自聚合表。
        numeric_count: 数值样本数 n（**不是** sample_count）。
        mean: 均值，来自聚合表的 ``avg_value``。
        sample: True 返回样本方差（n−1 分母），False 返回总体方差。

    Returns:
        方差；任一输入缺失或 ``n`` 不足时返回 ``None``（**不抛异常**）。
        浮点误差可能让结果出现极小负数 ⇒ 截断到 0。
    """
    if sum_sq is None or mean is None or numeric_count <= 0:
        return None
    if not sample and numeric_count < 1:
        return None
    if sample and numeric_count < 2:
        return None  # 单点无样本方差（分母 n−1 = 0）
    var = sum_sq / numeric_count - mean * mean
    if sample:
        var *= numeric_count / (numeric_count - 1)
    return var if var > 0 else 0.0
