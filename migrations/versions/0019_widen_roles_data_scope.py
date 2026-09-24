# -*- coding: utf-8 -*-
"""拓宽 roles.data_scope 到 VARCHAR(32)（P0-B/R-B：数据域隔离启用前置）

背景：data_scope 取值 `responsible_person` 有 18 个字符，varchar(16) 装不下——
严格模式报 1406；非严格模式截断为 `responsible_per` ⇒ 落入 data_scope_service
的「未知取值」分支 ⇒ 按最小权限返回空集，该角色用户看到零设备、收到零告警
（可用性事故）。列拓宽是补写入端点（同批提交）的前置。

**幂等**：按 information_schema 的 CHARACTER_MAXIMUM_LENGTH 判断，已是 32 则跳过。
**在线 DDL**：ALGORITHM=INPLACE, LOCK=NONE（列上无索引、表极小，0011/0016/0017/0018
同款纪律）。**不改语义**：DEFAULT 'all' 与注释原样保留。
"""
import logging

logger = logging.getLogger(__name__)

TABLE = "roles"
COLUMN = "data_scope"
_TARGET_LENGTH = 32
_MDL_WAIT_TIMEOUT_SECONDS = 300


def _current_length(conn) -> int:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (TABLE, COLUMN),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        cur.close()


def apply(conn) -> None:
    """拓宽 data_scope 到 VARCHAR(32)（幂等）"""
    length = _current_length(conn)
    if length == 0:
        logger.info("跳过：列 %s.%s 不存在（全新库由 baseline 建表，已是 32）", TABLE, COLUMN)
        return
    if length >= _TARGET_LENGTH:
        logger.info("跳过：%s.%s 已是 VARCHAR(%d)", TABLE, COLUMN, length)
        return

    conn.commit()  # 结束此前语句开启的事务，避免 DDL 与活跃事务互拖
    cur = conn.cursor()
    try:
        cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")
        cur.execute(
            f"ALTER TABLE `{TABLE}` "
            f"MODIFY `{COLUMN}` VARCHAR({_TARGET_LENGTH}) NOT NULL DEFAULT 'all' "
            f"COMMENT '数据权限范围: all/responsible_person/room/custom'",
            (),
        )
        logger.info(
            "已拓宽 %s.%s：VARCHAR(%d) → VARCHAR(%d)", TABLE, COLUMN, length, _TARGET_LENGTH
        )
    finally:
        cur.close()
