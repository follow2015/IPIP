# -*- coding: utf-8 -*-
"""存量时间数据 UTC 回填脚本（时间统一 UTC 的配套工具）。

## 用途
2026-09-08 起全仓时间口径统一为 UTC：应用层写 `now_utc_naive()`（UTC），
MySQL 会话时区由 app/extensions.py 固定为 UTC。**切换之前**写入库的值是本地
墙钟（生产服务器 +08:00），同列内出现两种口径混存：旧值被当作 UTC 读取时整体
偏早/偏晚 8 小时。本脚本把切换前的存量值按 `-8h` 修正回 UTC。

## 安全设计
- **默认 dry-run**：只扫描、不改数据；必须显式 `--apply` 才写库。
- **水位保护**：只处理 `--before`（默认=脚本启动时刻，UTC）之前的值，
  天然排除切换后已按 UTC 写入的新数据。
- **单列单批次**：`UPDATE ... WHERE <pk> IN (SELECT ... LIMIT N)`，
  以主键分批（默认 2000 行/批），避免长事务与锁表。
- **分区表默认跳过**：`device_metric_timeseries` 等按 `TO_DAYS(collected_at)`
  分区的表，改 collected_at 会让行在分区间迁移（11M+ 行 / 1.5GB），代价极高；
  需要时用 `--include-partitioned` 显式打开，并按 `--table` 单独跑。

## 用法
    # 1) 预览（强烈建议先跑）
    MYSQL_HOST=... MYSQL_PASSWORD=... python scripts/backfill_utc_timestamps.py

    # 2) 指定表 + 水位后执行
    python scripts/backfill_utc_timestamps.py --apply \
        --table users_log --table monitor_incident \
        --before 2026-09-08T00:00:00

    # 3) 仅看某表单列的待改行数
    python scripts/backfill_utc_timestamps.py --table switch_ports

注意：CONVERT_TZ 对同一行重跑会再减 8 小时。脚本用
`_utc_backfill_state` 状态表记录每列已应用的水位，重复执行同一/重叠水位会被
拒绝（确需重跑用 `--force`，并自行确认上次的执行范围）。执行前建议停写
（或确认该表无并发写入）。
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

import pymysql

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_utc")

DEFAULT_TABLES_SKIP = {
    "schema_migrations",          # 迁移元数据：与业务时间无关
}
# 已知的大分区表（默认跳过，需显式 --include-partitioned）
PARTITIONED_BIG_TABLES = {
    "device_metric_timeseries",
    "device_monitor_probe_events",
}


def get_connection():
    """从环境变量取连接信息（与 scripts/import_sql.py 一致，不硬编码凭据）。"""
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "ip_manager"),
        charset="utf8mb4",
        # 脚本自身也按 UTC 工作：会话时区与运行时 thanks_now 一致
        init_command="SET time_zone='+00:00'",
        autocommit=False,
    )


def list_datetime_columns(conn, tables=None):
    """列出所有 DATETIME 列（排除 TIMESTAMP 列——其读写本就按时区转换）。

    Args:
        conn: DB-API 连接
        tables: 限定表名集合；None 表示全库

    Returns:
        List[(table, column)]
    """
    cur = conn.cursor()
    try:
        sql = (
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND data_type = 'datetime' "
            "AND generation_expression = '' "
            "ORDER BY table_name, ordinal_position"
        )
        cur.execute(sql)
        rows = [(t, c) for t, c in cur.fetchall()]
    finally:
        cur.close()
    if tables:
        rows = [(t, c) for t, c in rows if t in tables]
    return [(t, c) for t, c in rows if t not in DEFAULT_TABLES_SKIP]


def get_partitioned_tables(conn):
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT DISTINCT table_name FROM information_schema.partitions "
            "WHERE table_schema = DATABASE() "
            "AND partition_name IS NOT NULL"
        )
        return {r[0] for r in cur.fetchall()}
    finally:
        cur.close()


def count_pending(conn, table, column, before):
    """统计待回填行数（值在 [min_value, before) 区间内）。"""
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT COUNT(*) FROM `{table}` "
            f"WHERE `{column}` IS NOT NULL AND `{column}` < %s",
            (before,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        cur.close()


STATE_TABLE = "_utc_backfill_state"


def ensure_state_table(conn):
    """创建防重跑状态表（幂等）。

    记录每列已应用的水位 before，重复执行同一/重叠水位会被拒绝。
    """
    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS `{STATE_TABLE}` ("
            f"  `table_name` VARCHAR(64) NOT NULL,"
            f"  `column_name` VARCHAR(64) NOT NULL,"
            f"  `applied_before` DATETIME NOT NULL COMMENT '已回填水位（UTC naive）',"
            f"  `applied_at` DATETIME NOT NULL DEFAULT (now()) COMMENT '执行时刻',"
            f"  `source_tz` VARCHAR(8) NOT NULL DEFAULT '+08:00',"
            f"  `rows_updated` BIGINT NOT NULL DEFAULT 0,"
            f"  PRIMARY KEY (`table_name`, `column_name`)"
            f") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='UTC 回填防重跑水位记录'"
        )
    finally:
        cur.close()
    conn.commit()


def check_watermark(conn, table, column, before, force=False) -> bool:
    """检查该列是否已在 >= before 的水位回填过。

    返回 True 表示可继续，False 表示应跳过（水位重叠）。
    """
    if force:
        return True
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT applied_before FROM `{STATE_TABLE}` "
            f"WHERE table_name = %s AND column_name = %s",
            (table, column),
        )
        row = cur.fetchone()
    finally:
        cur.close()
    if not row:
        return True
    applied = row[0]
    if applied >= before:
        logger.warning(
            "跳过 %s.%s：已在水位 %s 回填（>= 当前 %s），重跑会再减偏移量；"
            "确需重跑用 --force",
            table, column, applied.isoformat(sep=" "), before.isoformat(sep=" "),
        )
        return False
    return True


def record_watermark(conn, table, column, before, source_tz, rows_updated):
    """记录/更新该列的回填水位。"""
    cur = conn.cursor()
    try:
        cur.execute(
            f"INSERT INTO `{STATE_TABLE}` "
            f"(table_name, column_name, applied_before, source_tz, rows_updated) "
            f"VALUES (%s, %s, %s, %s, %s) "
            f"ON DUPLICATE KEY UPDATE "
            f"  applied_before = VALUES(applied_before),"
            f"  applied_at = now(),"
            f"  source_tz = VALUES(source_tz),"
            f"  rows_updated = rows_updated + VALUES(rows_updated)",
            (table, column, before, source_tz, rows_updated),
        )
    finally:
        cur.close()
    conn.commit()


def backfill_column(conn, table, column, before, batch_size, apply_changes,
                    source_tz="+08:00", force=False):
    """按主键分批把 `column` 在 before 之前的值从 source_tz 换算到 UTC。

    分批改一次的 PK 范围通过子查询取 LIMIT N，避免全表 UPDATE。
    """
    pk = _primary_key(conn, table)
    if not pk:
        logger.warning("跳过 %s.%s：无主键，无法分批更新", table, column)
        return 0
    pk_col = pk[0]  # 复合主键取第一列即可保证顺序推进

    pending = count_pending(conn, table, column, before)
    if pending == 0:
        logger.info("%s.%s：无需回填（0 行）", table, column)
        return 0
    logger.info("%s.%s 待回填 %d 行（%s）", table, column, pending,
                "写入" if apply_changes else "dry-run")

    if not apply_changes:
        # dry-run：只统计，不发起 UPDATE（避免无谓锁表）
        return pending

    updated = 0
    last_pk = None
    while True:
        cur = conn.cursor()
        try:
            where_pk = f"AND `{pk_col}` > %s" if last_pk is not None else ""
            params = [before] + ([last_pk] if last_pk is not None else [])
            cur.execute(
                f"SELECT MIN(`{pk_col}`), MAX(`{pk_col}`) FROM ("
                f"  SELECT `{pk_col}` FROM `{table}` "
                f"  WHERE `{column}` IS NOT NULL AND `{column}` < %s {where_pk} "
                f"  ORDER BY `{pk_col}` LIMIT %s"
                f") t",
                params + [batch_size],
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                break
            lo, hi = row
            cur.execute(
                f"UPDATE `{table}` SET `{column}` = CONVERT_TZ(`{column}`, %s, %s) "
                f"WHERE `{pk_col}` BETWEEN %s AND %s "
                f"AND `{column}` IS NOT NULL AND `{column}` < %s",
                (source_tz, "+00:00", lo, hi, before),
            )
            changed = cur.rowcount
            conn.commit()
        finally:
            cur.close()

        updated += changed
        logger.info("  批次 %s ∈ [%s, %s]：更新 %d 行", pk_col, lo, hi, changed)
        last_pk = hi
        if changed == 0:
            break

    return updated


def _primary_key(conn, table):
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT column_name FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = %s "
            "AND index_name = 'PRIMARY' ORDER BY seq_in_index",
            (table,),
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="存量 DATETIME 列 +08:00 → UTC 回填")
    p.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run）")
    p.add_argument("--table", action="append", default=None,
                   help="限定表名，可多次指定（默认全库 DATETIME 列）")
    p.add_argument("--exclude", action="append", default=[], help="排除表名，可多次指定")
    p.add_argument("--before", default=None,
                   help="只处理该时刻之前的值（UTC，YYYY-MM-DD[THH:MM:SS]）；默认=脚本启动时刻")
    p.add_argument("--batch-size", type=int, default=2000, help="每批行数（默认 2000）")
    p.add_argument("--include-partitioned", action="store_true",
                   help="包含分区大表（device_metric_timeseries / probe_events，代价高）")
    p.add_argument("--source-tz", default="+08:00", help="源时区偏移（默认 +08:00）")
    p.add_argument("--force", action="store_true",
                   help="跳过水位重叠检查（确认上次执行范围后再用）")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    before = args.before
    if before:
        before = datetime.fromisoformat(before)
        if before.tzinfo is not None:
            # aware 入参归一到 UTC naive（与库内口径一致）
            before = before.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        before = datetime.now(timezone.utc).replace(tzinfo=None)
    logger.info("回填水位 before=%s（UTC）", before.isoformat(sep=" "))

    conn = get_connection()
    try:
        if args.apply:
            ensure_state_table(conn)

        tables = set(args.table) if args.table else None
        cols = list_datetime_columns(conn, tables)
        cols = [(t, c) for t, c in cols if t not in set(args.exclude)]

        partitioned = get_partitioned_tables(conn)
        if not args.include_partitioned:
            skipped = sorted({t for t, _ in cols} & partitioned)
            if skipped:
                logger.info("跳过分区表（需 --include-partitioned 才处理）: %s", skipped)
            cols = [(t, c) for t, c in cols if t not in partitioned]

        logger.info("计划处理 %d 个 DATETIME 列，覆盖 %d 张表",
                    len(cols), len({t for t, _ in cols}))
        if not args.apply:
            logger.info("★ DRY-RUN：未做任何写入；确认无误后加 --apply 执行")

        total = 0
        for table, column in cols:
            if args.apply and not check_watermark(conn, table, column, before,
                                                  force=args.force):
                continue
            updated = backfill_column(conn, table, column, before,
                                      args.batch_size, args.apply,
                                      source_tz=args.source_tz)
            total += updated
            if args.apply and updated >= 0:
                record_watermark(conn, table, column, before,
                                 args.source_tz, updated)
        logger.info("完成：累计%s %d 行",
                    "回填" if args.apply else "待处理", total)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
