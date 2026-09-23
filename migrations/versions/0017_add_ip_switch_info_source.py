# -*- coding: utf-8 -*-
"""为 ip_switch_info 增加 source 列（WP-6：降级写入来源标记，可撤回）

背景：B-46 把 `list_non_host_networks` 从 CursorResult 改为真 List[str] 后，
scan_degrader 的 `/24` 兜底（管理 IP 推算网段）从"恒不执行"变成"会执行"——
这是一次静默的行为放大（P1-1）。本迁移给降级写入补来源标记：

- `source = 'degraded_l2'` / `'degraded_l3'`：正常降级路径写入
- `source = 'degraded_l2_24fallback'`：因 /24 兜底而发生的写入（重点回滚对象）
- `source IS NULL`：普通扫描路径（无标记）

**source 语义 = 最近一次写入者**：UPSERT 的 ON DUPLICATE KEY UPDATE 无条件
以新值覆盖 source（含置 NULL）——普通扫描覆盖降级行后标记即消失，
按标记回滚（DELETE ... WHERE source LIKE 'degraded%_24fallback'）不会误删
已被权威数据覆盖的行。

**幂等**：列已存在则跳过。**在线 DDL**：ALGORITHM=INPLACE, LOCK=NONE
（加可空列 + 二级索引均不阻塞并发 DML，0011/0016 同款纪律）。
"""
import logging

logger = logging.getLogger(__name__)

TABLE = "ip_switch_info"
COLUMN = "source"
INDEX = "idx_isi_source"
_MDL_WAIT_TIMEOUT_SECONDS = 300


def _column_exists(conn, table: str, column: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (table, column),
        )
        return bool(cur.fetchone()[0])
    finally:
        cur.close()


def _index_exists(conn, table: str, name: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = %s "
            "AND index_name = %s",
            (table, name),
        )
        return bool(cur.fetchone()[0])
    finally:
        cur.close()


def apply(conn) -> None:
    """加 source 列 + 来源索引（各自幂等）"""
    if not _column_exists(conn, TABLE, COLUMN):
        conn.commit()  # 结束此前语句开启的事务，避免 DDL 与活跃事务互拖
        cur = conn.cursor()
        try:
            cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")
            cur.execute(
                f"ALTER TABLE `{TABLE}` "
                f"ADD COLUMN `{COLUMN}` VARCHAR(32) NULL "
                "COMMENT '写入来源(degraded_l2/l3[_24fallback]=降级/24兜底, NULL=普通扫描)', "
                "ALGORITHM=INPLACE, LOCK=NONE"
            )
            logger.info("已加列 %s.%s（WP-6 降级写入来源标记）", TABLE, COLUMN)
        finally:
            cur.close()
    else:
        logger.info("跳过：列 %s.%s 已存在", TABLE, COLUMN)

    if not _index_exists(conn, TABLE, INDEX):
        conn.commit()
        cur = conn.cursor()
        try:
            cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")
            cur.execute(
                f"ALTER TABLE `{TABLE}` ADD INDEX `{INDEX}` (`{COLUMN}`), "
                "ALGORITHM=INPLACE, LOCK=NONE"
            )
            logger.info("已加索引 %s.%s（按来源回滚的查询路径）", TABLE, INDEX)
        finally:
            cur.close()
    else:
        logger.info("跳过：索引 %s.%s 已存在", TABLE, INDEX)
