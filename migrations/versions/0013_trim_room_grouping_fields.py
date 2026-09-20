# -*- coding: utf-8 -*-
"""订正 rooms.building / rooms.floor 的首尾空白

背景：这两个字段是跨机房总览的**分组键**，但此前写入路径没有做 trim（本轮已在
`RoomService` 补齐）。存量数据里已出现 `'A '`（尾随空格）。

后果不是"显示难看"那么轻：`GET /rooms/buildings` 的去重是按原始值做的，`'A'` 与
`'A '` 会被当成两个楼栋，于是表单联想里出现两个几乎一样的选项，总览里同一栋楼
裂成两组——正是设计文档 §2.4 担心的"同一栋楼被打成两个分组"，只是成因从"用词
不一致"变成了"手滑空格"。

**为什么用 SQL 的 TRIM 而不是逐行读改写**：逻辑完全可以在库内表达，逐行读改写
需要拉全表进内存再逐条 UPDATE，在机房表上没有必要。且 `UPDATE ... WHERE 值 <> TRIM(值)`
只命中真正需要改的行，正常库上影响面极小。

**幂等**：第二次执行时条件已不匹配任何行，影响 0 行。

**空串归一**：trim 后变成空串的值统一置 NULL——空串与 NULL 在分组时都表示"未填"
（`get_overview` 用 `room.building or ""` 归桶），但空串会让 `isnot(None) AND != ""`
这类既有过滤条件多绕一层，统一为 NULL 更省心。
"""
import logging

logger = logging.getLogger(__name__)

_FIELDS = ("building", "floor")


def apply(conn) -> None:
    """去除首尾空白，并把空串归一为 NULL（各自幂等）"""
    cur = conn.cursor()
    try:
        for field in _FIELDS:
            cur.execute(
                f"UPDATE `rooms` SET `{field}` = TRIM(`{field}`) "
                f"WHERE `{field}` IS NOT NULL AND `{field}` <> TRIM(`{field}`)"
            )
            trimmed = cur.rowcount
            if trimmed:
                logger.info("已去除 rooms.%s 的首尾空白：%s 行", field, trimmed)
            else:
                logger.info("跳过：rooms.%s 无需订正", field)

            cur.execute(
                f"UPDATE `rooms` SET `{field}` = NULL "
                f"WHERE `{field}` IS NOT NULL AND `{field}` = ''"
            )
            blanked = cur.rowcount
            if blanked:
                logger.info("已把 rooms.%s 的空串归一为 NULL：%s 行", field, blanked)
    finally:
        cur.close()
    conn.commit()
