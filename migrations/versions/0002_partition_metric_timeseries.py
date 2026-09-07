# -*- coding: utf-8 -*-
"""device_metric_timeseries 分区化落地（docs/2026-09-07-性能评估报告与patch评审.md P1）。

背景：该表生产实测 1100+ 万行 / 1.5GB，占全库 96%，且未分区、无清理
（增长 ≈54 万行/天）。旧散迁移 add_metric_timeseries.py 虽写了分区 DDL，
但建表早于该迁移，CREATE TABLE IF NOT EXISTS 成为空操作，表停留在
PK(id) 无分区状态（模型 docstring 声明的"按日分区"从未真正落地）。

本迁移做两件事（两条 ALTER，各一次 COPY 重建；MySQL 规定 PARTITION BY
必须单独成句、不能与其他 alter option 合并，故无法一条完成）：
  1. 主键 (id) → (id, collected_at)：MySQL 分区键必须包含在主键内；
  2. PARTITION BY RANGE (TO_DAYS(collected_at)) 按日分区 + p_future 兜底。
分区范围覆盖 [min(最早数据日, today-30), today+5]，保证存量数据全部落位。

幂等性：已分区（且 PK 已含 collected_at）则整体跳过；若在第 1 步后中断，
重跑时 PK 已复合，直接走第 2 步补分区，重跑安全。
前置纪律：执行前必须停止监控进程（COPY 重建期间禁止写入；生产执行当天
业务已暂停）。重建耗时与磁盘请参照评审文档 P1 节。

维护：monitor-manage-partitions / monitor-archive CLI 承担未来分区预建
与 90 天保留清理（METRIC_RETENTION_DAYS）。
"""
import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

TABLE = "device_metric_timeseries"
PARTITION_FUTURE_DAYS = 5
PARTITION_HISTORY_BUFFER_DAYS = 30


def _pk_columns(conn) -> set:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT column_name FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = %s "
            "AND index_name = 'PRIMARY'",
            (TABLE,),
        )
        return {r[0] for r in cur.fetchall()}
    finally:
        cur.close()


def _partition_count(conn) -> int:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.partitions "
            "WHERE table_schema = DATABASE() AND table_name = %s "
            "AND partition_name IS NOT NULL",
            (TABLE,),
        )
        return int(cur.fetchone()[0])
    finally:
        cur.close()


def _earliest_collected_date(conn):
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT MIN(collected_at) FROM `{TABLE}`")
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        v = row[0]
        return v.date() if isinstance(v, datetime) else v
    finally:
        cur.close()


def _build_partition_clause(start: date, end: date) -> str:
    parts = []
    d = start
    while d <= end:
        pname = f"p{d.strftime('%Y%m%d')}"
        next_d = (d + timedelta(days=1)).strftime("%Y-%m-%d")
        parts.append(f"PARTITION {pname} VALUES LESS THAN (TO_DAYS('{next_d}'))")
        d += timedelta(days=1)
    parts.append("PARTITION p_future VALUES LESS THAN MAXVALUE")
    return ",\n    ".join(parts)


def apply(conn) -> None:
    pk = _pk_columns(conn)
    nparts = _partition_count(conn)

    if nparts > 0:
        if not {"id", "collected_at"} <= pk:
            raise RuntimeError(
                f"{TABLE} 已分区但主键异常（{sorted(pk)}），请人工核查"
            )
        logger.info("跳过 %s（已有 %d 个分区，幂等）", TABLE, nparts)
        return

    today = date.today()
    earliest = _earliest_collected_date(conn)
    start = min(earliest, today - timedelta(days=PARTITION_HISTORY_BUFFER_DAYS)) \
        if earliest else today - timedelta(days=PARTITION_HISTORY_BUFFER_DAYS)
    end = today + timedelta(days=PARTITION_FUTURE_DAYS)
    clause = _build_partition_clause(start, end)

    cur = conn.cursor()
    try:
        if not {"id", "collected_at"} <= pk:
            cur.execute(
                f"ALTER TABLE `{TABLE}` "
                f"DROP PRIMARY KEY, ADD PRIMARY KEY (id, collected_at)"
            )
            logger.info("%s 主键已改为 (id, collected_at)", TABLE)

        cur.execute(
            f"ALTER TABLE `{TABLE}` "
            f"PARTITION BY RANGE (TO_DAYS(collected_at)) (\n"
            f"    {clause}\n)"
        )
        logger.info(
            "%s 分区化完成：分区范围 %s ~ %s + p_future，共 %d 个日分区",
            TABLE, start, end, (end - start).days + 2,
        )
    finally:
        cur.close()
    conn.commit()
