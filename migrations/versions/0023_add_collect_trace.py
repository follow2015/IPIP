# -*- coding: utf-8 -*-
"""network_ports 新增 collect_trace 列（采集溯源，独立于 raw_info）

> 编号说明：初稿误用 `0014`，与既有 `0014_add_room_number_and_name_grouping.py`
> **同号** —— 而 `SchemaMigrationRunner` 按 version 记录已应用迁移，同号会导致
> 后一个**永不执行**（静默吞掉别人的迁移）。已改为当时的下一可用号 0023，
> 并由 `tests/test_migration_versions_numbering.py` 守卫编号唯一性。



契约层规格决策 5 要求把采集溯源落库（"这条端口数据是哪个通道采的、质量如何、
什么时候采的"）。原计划写进既有 JSON 列 `raw_info`，但复核时发现**该列已被占用**：

- `switch_repo.write_port_info()` 往 `raw_info` 写 `{"port_info": "<配置文本>"}`
- 读方（`switch_repo` / 前端"查看端口配置"）按该形状解析

两种格式同列共存 = 谁后写谁赢，症状是**随机丢失**（取决于采集与配置抓取的时序），
且排查极难。故拆列：`collect_trace` 只放溯源，`raw_info` 继续只管端口配置文本。


**纯增量 DDL**（`ADD COLUMN`，可空、无默认值），不读不改任何既有数据 ——
与 0013 那类"数据改写"不同，本迁移没有不可逆风险，但仍保持幂等：
列已存在时直接跳过（重复执行安全，且兼容手工加过列的环境）。


```sql
ALTER TABLE network_ports DROP COLUMN collect_trace;
```

删列会丢掉溯源信息，但**不影响端口数据本身**（端口行、配置文本都不在本列）。
"""
import logging

logger = logging.getLogger(__name__)

_TABLE = "network_ports"
_COLUMN = "collect_trace"
_COMMENT = "采集溯源：通道/质量/时间（与 raw_info 的端口配置文本职责分开）"


def _column_exists(cur) -> bool:
    """列是否已存在（INFORMATION_SCHEMA 预检，保证幂等）。"""
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (_TABLE, _COLUMN),
    )
    row = cur.fetchone()
    return bool(row and row[0])


def apply(conn) -> None:
    """加列（幂等）。"""
    cur = conn.cursor()
    try:
        if _column_exists(cur):
            logger.info("跳过：%s.%s 已存在", _TABLE, _COLUMN)
            return
        cur.execute(
            f"ALTER TABLE `{_TABLE}` ADD COLUMN `{_COLUMN}` JSON NULL "
            f"COMMENT %s",
            (_COMMENT,),
        )
        logger.info("已新增 %s.%s（JSON NULL，纯增量，无数据改写）", _TABLE, _COLUMN)
    finally:
        cur.close()
    conn.commit()
