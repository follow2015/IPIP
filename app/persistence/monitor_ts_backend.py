# -*- coding: utf-8 -*-
"""时序存储后端选择器（D3）—— 纯函数，无 IO、无全局状态。

为什么要有它
------------
CH 路线要能把写入/查询**按时间**切到不同后端，而这件事必须能被**单独测试**：
写路径边上散落 `if 该用 CH` 的判断，是这条路线最容易长出不一致的地方
（写去 CH、读还在 MySQL；或者分界点那一条两边都没有）。

故选择器收成一个纯函数：`(device_id, ts) -> "mysql" | "clickhouse"`。
它是整套切换的**唯一判据来源**，任何写/读路径都必须问它，不得自行判断。

用户口径：**CH 是"选择开启"，不是自动开启**
-------------------------------------------
默认 `MONITOR_TS_BACKEND=mysql` ⇒ 本函数恒返回 `"mysql"`，
在没有任何 CH 配置的机器上行为与改造前**逐字节相同**。

三种模式
--------
- ``mysql``：全部走 MySQL（默认）；
- ``clickhouse``：全部走 CH（迁移期结束后只用这个）；
- ``split``：以 ``MONITOR_TS_SPLIT_AT`` 为界 —— **>= 分界**走 CH，
  **< 分界**走 MySQL（读历史）。这样切换当天不需要搬旧数据。

边界取 `>=` 而不是 `>` 的理由（G2 的反例判据）
----------------------------------------------
若取 ``>``，则**恰好等于分界点的那一条**既不属于"分界之前"（不满足 `<`），
也不属于"分界之后"（不满足 `>`）⇒ **两边都不写**，静默丢一行。
这类"只在边界上丢数据"的 bug 极难复现，故边界方向由测试钉死。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

MYSQL = "mysql"
CLICKHOUSE = "clickhouse"

DEFAULT_BACKEND = MYSQL


def _config_get(name: str, default: str = "") -> str:
    """读配置。

    优先 ``current_app.config``（Flask 上下文内，测试与运行时都走这里），
    无上下文时回退环境变量 —— 选择器要在 CLI / 后台线程里也能用。
    """
    try:
        from flask import current_app

        if current_app:
            val = current_app.config.get(name)
            if val is not None:
                return str(val)
    except Exception:  # noqa: BLE001, S110 —— 无 app 上下文属正常路径，不该抛
        pass
    return os.getenv(name, default) or default


def get_backend_mode() -> str:
    """当前后端模式：``mysql`` / ``clickhouse`` / ``split``（非法值按 mysql）。"""
    mode = (_config_get("MONITOR_TS_BACKEND", DEFAULT_BACKEND) or DEFAULT_BACKEND).lower()
    if mode not in (MYSQL, CLICKHOUSE, "split"):
        return DEFAULT_BACKEND
    return mode


def get_split_at() -> Optional[datetime]:
    """解析 ``MONITOR_TS_SPLIT_AT``；未设置或非法时返回 ``None``。

    统一转成 **aware-aware 无关** 的比较基准：解析结果一律带 tzinfo
    （naive 输入按 UTC 解释）。项目内时序统一用 ``now_utc_naive()``（UTC 无 tz），
    故比较前要把两边拉到同一基准，否则会踩 "can't compare offset-naive and
    offset-aware datetimes"。
    """
    raw = (_config_get("MONITOR_TS_SPLIT_AT", "") or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _normalize(ts: datetime) -> datetime:
    """把时间拉到 UTC-aware（naive 视为 UTC）。"""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def choose_ts_backend(
    device_id: Optional[int] = None,
    ts: Optional[datetime] = None,
) -> str:
    """选择时序后端。**这是全套切换的唯一判据来源。**

    Args:
        device_id: 设备 ID。当前**不参与**判断（预留：将来要按设备灰度时在此加
            白名单，调用方签名不用改）。保留参数是为了让所有调用点从一开始
            就传它 —— 否则将来加灰度要改遍全仓。
        ts: 该条数据的时间戳。``None`` 视为"当前"，此时 split 模式下走 CH
            （新数据总是进新后端）。

    Returns:
        ``"mysql"`` 或 ``"clickhouse"``。

    边界：``split`` 模式下 **ts >= split_at ⇒ clickhouse**（含等于，见模块
    docstring 的反例说明）；``split_at`` 缺失时退回 ``mysql``（安全侧）。
    """
    mode = get_backend_mode()
    if mode == MYSQL:
        return MYSQL
    if mode == CLICKHOUSE:
        return CLICKHOUSE

    split_at = get_split_at()
    if split_at is None:
        return MYSQL
    if ts is None:
        return CLICKHOUSE
    return CLICKHOUSE if _normalize(ts) >= split_at else MYSQL


def use_clickhouse_for(
    device_id: Optional[int] = None,
    ts: Optional[datetime] = None,
) -> bool:
    """``choose_ts_backend`` 的布尔糖（调用点读起来更顺）。"""
    return choose_ts_backend(device_id, ts) == CLICKHOUSE
