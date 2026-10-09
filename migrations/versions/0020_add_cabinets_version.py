# -*- coding: utf-8 -*-
"""为 cabinets 增加 version 列（乐观锁，消机柜换位的 lost-update）

背景：机柜坐标此前只有逐条 PUT。`_assert_position_available` 按**当前快照**
判占用，因此"两台机柜互换格子"必然失败——处理 A 时目标格还站着 B（B 尚未移走），
直接 409；两个编辑端各自"读-改-写"时后写者还会静默覆盖先写者（lost-update）。
`uk_cabinet_position` 只兜"同目标位冲突"，不防"读过的位置已被别人改走"。

第六轮评审 §三 残留缺口点名：标记（room_layout_markers）已由 0018 立好
"version 列 + CAS + 批量端点"的模板，机柜是现成同型，补齐即可。

- 存量行回填 version=0（ADD COLUMN 带 NOT NULL DEFAULT '0'，MySQL 自动回填）
- CAS 判据放 UPDATE 谓词内（MySQL RR 下先读后比会被事务快照骗过）
- 单条 PUT 同步递增，version 语义 = 该行被改过几次的完整计数

**幂等**：列已存在则跳过。**在线 DDL**：ALGORITHM=INPLACE, LOCK=NONE
（加带默认值的整型列，0011/0016/0017/0018/0019 同款纪律）。
"""
import logging

logger = logging.getLogger(__name__)

TABLE = "cabinets"
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
                "COMMENT '乐观锁版本号（每次编辑+1，机柜换位 CAS）', "
                "ALGORITHM=INPLACE, LOCK=NONE"
            )
            logger.info("已加列 %s.%s（机柜乐观锁版本号）", TABLE, COLUMN)
        finally:
            cur.close()
    else:
        logger.info("跳过：列 %s.%s 已存在", TABLE, COLUMN)
