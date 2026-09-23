# -*- coding: utf-8 -*-
"""为 room_layout_markers 增加 version 列（WP-7：乐观锁消 lost-update）

背景：位置编辑此前只有逐条 PUT，两个编辑端各自"读-改-写"时后写者静默覆盖
先写者（lost-update）。`uk_marker_position` 只兜"同目标位冲突"，不防
"读过的位置已被别人改走"。本迁移给标记行加乐观锁版本号：

- 存量行回填 version=0（ADD COLUMN 带 NOT NULL DEFAULT '0'，MySQL 自动回填）
- 新端点 `POST /rooms/<id>/layout-markers/batch` 的 CAS 判据放 UPDATE 谓词内
- 单条 PUT 同步递增，version 语义 = 该行被改过几次的完整计数

**幂等**：列已存在则跳过。**在线 DDL**：ALGORITHM=INPLACE, LOCK=NONE
（加带默认值的整型列，0011/0016/0017 同款纪律）。
"""
import logging

logger = logging.getLogger(__name__)

TABLE = "room_layout_markers"
COLUMN = "version"
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


def apply(conn) -> None:
    """加 version 列（幂等）"""
    if not _column_exists(conn, TABLE, COLUMN):
        conn.commit()  # 结束此前语句开启的事务，避免 DDL 与活跃事务互拖
        cur = conn.cursor()
        try:
            cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")
            cur.execute(
                f"ALTER TABLE `{TABLE}` "
                f"ADD COLUMN `{COLUMN}` INT NOT NULL DEFAULT '0' "
                "COMMENT '乐观锁版本号（每次编辑+1，WP-7）', "
                "ALGORITHM=INPLACE, LOCK=NONE"
            )
            logger.info("已加列 %s.%s（WP-7 乐观锁版本号）", TABLE, COLUMN)
        finally:
            cur.close()
    else:
        logger.info("跳过：列 %s.%s 已存在", TABLE, COLUMN)
