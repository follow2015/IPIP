# -*- coding: utf-8 -*-
"""修正 room_channels / room_layout_markers 的 room_id 索引名，消除 db-check 索引漂移。

根因：0009 建表时手补的索引名 `ix_<表>_room` 与 SQLAlchemy `index=True` 的默认
命名 `ix_<表>_<列>`（即 `ix_room_channels_room_id`）不一致——表结构正确，仅索引名
不匹配，故 `flask db-check` / 启动自检报「缺索引」。

修正策略：**先建正确名（幂等），再删旧名（幂等）**。顺序不可颠倒——MySQL 要求
外键列上始终有可用索引，先建后删才不会触发
"Cannot drop index ... needed in a foreign key constraint"。
"""
import logging

logger = logging.getLogger(__name__)

FIXES = [
    ("room_channels", "ix_room_channels_room", "ix_room_channels_room_id", "room_id"),
    (
        "room_layout_markers",
        "ix_room_layout_markers_room",
        "ix_room_layout_markers_room_id",
        "room_id",
    ),
]


def _index_exists(conn, table: str, index: str) -> bool:
    """索引是否已存在（MySQL 索引名大小写不敏感，此处按库中实际名比对）"""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s",
            (table, index),
        )
        row = cur.fetchone()
        return bool(row and row[0])
    finally:
        cur.close()


def apply(conn) -> None:
    """逐表对齐索引名（幂等；两个分支都存在时也不重复动作）"""
    cur = conn.cursor()
    try:
        for table, old_name, new_name, column in FIXES:
            if _index_exists(conn, table, new_name):
                logger.info("跳过：%s.%s 已存在", table, new_name)
            else:
                cur.execute(f"CREATE INDEX `{new_name}` ON `{table}` (`{column}`)")
                logger.info("已建索引 %s.%s", table, new_name)

            if _index_exists(conn, table, old_name):
                cur.execute(f"DROP INDEX `{old_name}` ON `{table}`")
                logger.info("已删旧索引 %s.%s", table, old_name)
            else:
                logger.info("跳过：%s.%s 不存在", table, old_name)
    finally:
        cur.close()
    conn.commit()
