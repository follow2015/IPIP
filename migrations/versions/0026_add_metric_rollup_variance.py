# -*- coding: utf-8 -*-
"""给指标侧两张预聚合表补「波动性」列：`sum_sq` + `numeric_count`

为什么现在补
------------
``hourly`` / ``daily`` 原本只有 ``avg/min/max/sample_count`` —— **只有极差，
给不出分布形状**。AI 故障预测要的是**波动性**（方差），而 min/max 无法还原它。

补这两列后，方差可**不依赖明细**算出（并行方差合成）：

    Var = Σx² / n − mean²

即 ``app/utils/metric_value.py::variance_from_sum_sq``。``sum_sq`` 与
``numeric_count`` 都是**可加**的量 ⇒ 从 hourly 合成到 daily 只需逐层求和，
无需回源明细（明细保留 90 天，而 daily 覆盖 730 天 —— 后者根本没有明细可回）。

**成本窗口**：两张表现在仍是**空表**（迁移 0025 刚建、聚合尚未回填），
加列代价≈0。等 2,200 万行聚合回填后再补，就要带着数据 ALTER 并重算全表。
这是本迁移**现在就做**的全部理由。

为什么是独立迁移而不是改 0025
------------------------------
0025 的建表幂等是 ``SHOW TABLES LIKE`` —— 表已存在就**整体跳过**，不做逐列补齐。
因此直接改 0025 的 DDL 会得到这样一个陷阱：

- 全新安装：baseline 已含新列 ⇒ 看起来对；
- **已跑过 0025 的库**：表已存在 ⇒ 跳过 ⇒ **永远缺这两列** ⇒ 后续降采样
  INSERT 撞 1054，而且看不出是这次改动引起的。

独立迁移用 ``information_schema.COLUMNS`` 判列，**无论 0025 是否已执行都能补齐**，
两个方向都安全。

为什么必须同时加 `numeric_count`
--------------------------------
``AVG(value_num)`` 忽略 NULL，``COUNT(*)`` 不忽略 ⇒ 非数值指标混入时两者不等。
直接用 ``sample_count``（= COUNT(*)）当方差分母会让方差**静默偏小**。
故单独存 ``numeric_count``（= COUNT(value_num)，与 AVG 的分母严格一致）。

在线 DDL 纪律
------------
两张表都是**空表**，ADD COLUMN 无行重写；走 INSTANT → INPLACE 分级降级，
**不回退 COPY**（与 0025 同一取舍）。

**无 downgrade**：回滚走手工 DDL（DROP COLUMN）；两列都是派生量，可随时重算。
"""
import logging

logger = logging.getLogger(__name__)

_MDL_WAIT_TIMEOUT_SECONDS = 300

_COLUMNS = (
    (
        "device_metric_timeseries_hourly",
        "sum_sq",
        "double DEFAULT NULL",
        "桶内 value_num 的平方和 Σ(x²)，供方差合成（非数值指标为 NULL）",
    ),
    (
        "device_metric_timeseries_hourly",
        "numeric_count",
        "int NOT NULL DEFAULT '0'",
        "桶内 value_num 非 NULL 的行数（= AVG 的分母；方差合成必需）",
    ),
    (
        "device_metric_timeseries_daily",
        "sum_sq",
        "double DEFAULT NULL",
        "当天各小时桶 sum_sq 之和，供方差合成",
    ),
    (
        "device_metric_timeseries_daily",
        "numeric_count",
        "int NOT NULL DEFAULT '0'",
        "当天各小时桶 numeric_count 之和",
    ),
)


def _column_exists(conn, table: str, column: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.COLUMNS "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (table, column),
        )
        return bool(cur.fetchall())
    finally:
        cur.close()


def _add_column(conn, table: str, column: str, ddl: str, comment: str) -> None:
    """加一列，按 INSTANT → INPLACE/LOCK=NONE 分级降级；都不行则明确失败。"""
    last_err = None
    for algo_lock in ("ALGORITHM=INSTANT", "ALGORITHM=INPLACE, LOCK=NONE"):
        sql = f"ALTER TABLE `{table}` ADD COLUMN `{column}` {ddl} COMMENT '{comment}', {algo_lock}"
        try:
            conn.cursor().execute(sql)
        except Exception as exc:  # noqa: BLE001 —— 按算法逐个试，异常即控制流
            last_err = exc
            logger.warning("加列 %s.%s 的算法 %s 不可用：%s", table, column, algo_lock, exc)
            continue
        logger.info("已加列 %s.%s（%s）", table, column, algo_lock)
        return
    raise RuntimeError(
        f"无法为 {table} 在线加列 {column}：INSTANT 与 INPLACE/LOCK=NONE 均被拒绝"
        f"（最后错误：{last_err}）。本迁移不回退 COPY —— 目标表即将承载 730 天"
        "聚合数据，静默 COPY 比明确失败更难归因。请于低峰重跑或手工确认算法支持。"
    ) from last_err


def apply(conn) -> None:
    """给两张聚合表补波动性列（逐列幂等，缺哪列补哪列）"""
    cur = conn.cursor()
    try:
        cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")
        for table, column, ddl, comment in _COLUMNS:
            if _column_exists(conn, table, column):
                logger.info("跳过：%s.%s 已存在", table, column)
                continue
            _add_column(conn, table, column, ddl, comment)
    finally:
        cur.close()
