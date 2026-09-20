# -*- coding: utf-8 -*-
"""为 rooms 增加 floor（所属楼层），供跨机房总览按楼层过滤

背景：`building`（楼栋）解决的是"一栋楼里有多个数据间"的分组问题，但同一栋楼的
**同一层**也可能有多个 Room——按楼栋分组后，这些机房仍会混在一起（例如 A 栋 3 层
有 3 个机房，与 A 栋 5 层的机房并排列出），运维无法按层收敛视图。

**为什么用字符串而非整数**：真实环境的楼层写法不统一，除 `3`、`5` 外还有 `B1`/`B2`
（地下）、`M`（夹层）。整数列无法表达这些，届时只能改类型或另起一列。

**为什么不做排序**：字符串排序有 `"10F" < "2F"` 的字典序陷阱，而按楼层排序并非
当前需求（总览仍沿用 `order_by="name"`），故不引入会误导人的排序键。

**为什么可空且不建实体表**：与 `building` 同一克制原则（设计文档 §2.4）——运维要的是
"过滤/分组展示"，不是楼层资产台账。存量机房全部留空，不影响现有数据，后续补填
一个生效一个，不需要一次性迁移。

**幂等**：列已存在则跳过；重复执行安全。
"""
import logging

logger = logging.getLogger(__name__)


def _column_exists(conn, table: str, column: str) -> bool:
    """列是否已存在（幂等判断）"""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (table, column),
        )
        row = cur.fetchone()
        return bool(row and row[0])
    finally:
        cur.close()


def apply(conn) -> None:
    """加 rooms.floor（可空，存量落空）"""
    cur = conn.cursor()
    try:
        if _column_exists(conn, "rooms", "floor"):
            logger.info("跳过：rooms.floor 已存在")
        else:
            cur.execute(
                "ALTER TABLE `rooms` ADD COLUMN `floor` VARCHAR(20) NULL "
                "COMMENT '所属楼层(用于跨机房总览按楼层过滤,自由文本;字符串而非整数以容纳 B1/M 等写法)' "
                "AFTER `building`"
            )
            logger.info("已加列 rooms.floor")
    finally:
        cur.close()
    conn.commit()
