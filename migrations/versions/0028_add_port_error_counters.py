# -*- coding: utf-8 -*-
"""端口错包 / 丢弃计数：network_ports 加 4 个计数列 + 1 个采样时间列


``raw_info`` 的既有语义是"端口配置原始文本"（CLI 侧回显），把计数混进去会
带来两个具体问题：

1. **不可查询**：JSON 里的数没法排序 / 筛选 / 加索引，而"哪些端口在丢包"恰恰
   是排障时最想**排序**看的一张表；
2. **语义混杂**：`raw_info` 是"采集到的原始文本"，计数是"结构化指标"，两者生命
   周期也不同（配置变了才更新 vs 每轮采集都更新）。


只加**错包与丢弃**四项：`in_errors` / `out_errors` / `in_discards` /
`out_discards`。**不含流量速率** —— 速率需要两次采样求差，而监控侧已有内置
模板 `if_utilization`（ifHC*Octets 64 位差分、60s 轮询、阈值 80/95）且前端已
展示，通道层再存一套就是两套口径。

四项都是 Counter32 **累计值**（RFC 1158），`NULL` 表示设备没上报该列 —— 与
"设备确实报 0"严格区分（宁缺勿错）。


**纯增量 DDL**（`ADD COLUMN`，可空、无默认值），不读不改任何既有数据，与
0023 同口径：幂等（列已存在则跳过），无不可逆风险。


上面第 1 条说"JSON 里的数没法**排序 / 筛选 / 加索引**，而『哪些端口在丢包』恰恰是
排障时最想排序看的一张表" —— 那句话说明的是**能力**（JSON 连排都排不了），
**不是**"存在一个需要索引支撑的查询"。评审据此追问"列加了索引没加"，复核结论是
**不加**，依据如下（均可 `rg` 自证，复核日期 2026-10-10）：

1. 全仓**没有任何**按这四列排序 / 筛选 / 聚合的读路径 ——
   ``rg -n 'NetworkPort\\.(in_errors|out_errors|in_discards|out_discards)' app/`` 为**空**；
2. `network_ports` 的读查询**全部**以 `device_id` / 端口 id / `customer_id` 为入口
   （`NetworkPortRepository` 的每个方法首参都是 `device_id`；`switch_repo` 的四处
   查询也都带 `NetworkPort.device_id == switch_id`）；
3. 唯一的 `ORDER BY` 是 `slot, card, port_number`，与计数无关；
4. 排序发生在**单设备域内**（前端 `DeviceDetail/UnifiedPortTab`），单设备端口
   数十行 —— 该设备几十行的 filesort 成本可忽略，且既有
   `uq_device_port_name(device_id, port_name)` / `idx_np_device_status_link`
   已能以 `device_id` 打头定位到这些行；
5. 反面代价是确定的：这四列**每轮采集都会写**（`bulk_update_error_counters`），
   加索引 = 每次批量写都维护索引 = **纯写放大、零读收益**，正是
   `0001_drop_redundant_indexes` 清理过的那类回潮。

**重新评估的触发条件**（写清以免下次又只能凭印象争论）：出现"跨设备的错包 Top-N /
按错包筛选设备列表 / 对错包做设备级聚合"这类**新读路径**时，才需要按实际
`WHERE`/`ORDER BY` 的首列设计复合索引；届时以 `EXPLAIN` 为准，不要凭"有这列就该有索引"
倒推。


本迁移落的列注释是"最近一次采样时间"。**运行时语义随后被收窄**（2026-10-10
评审 N8）：只有**四项齐全**的一次写入才前进该时间戳 —— 前端把 1 个时间戳与
4 个值并列展示，部分上报时前进时间戳等于替 `NULL` 列背书。DDL 注释按"已被应用
的历史"保持原样，权威语义在 ORM 注释（`app/models/network_port.py`）与写入方
（`NetworkPortRepository.bulk_update_error_counters`）。


```sql
ALTER TABLE `network_ports`
  DROP COLUMN `in_errors`,
  DROP COLUMN `out_errors`,
  DROP COLUMN `in_discards`,
  DROP COLUMN `out_discards`,
  DROP COLUMN `error_counters_at`;
```

只是丢掉计数快照，不影响端口本体数据。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_TABLE = "network_ports"

_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("in_errors", "bigint NULL", "入向错包累计（ifInErrors，Counter32；NULL=设备未上报）"),
    ("out_errors", "bigint NULL", "出向错包累计（ifOutErrors；NULL=设备未上报）"),
    ("in_discards", "bigint NULL", "入向丢弃累计（ifInDiscards；NULL=设备未上报）"),
    ("out_discards", "bigint NULL", "出向丢弃累计（ifOutDiscards；NULL=设备未上报）"),
    ("error_counters_at", "datetime NULL", "上述计数的最近一次采样时间"),
)


def _column_exists(cur, column: str) -> bool:
    """列是否已存在（INFORMATION_SCHEMA 预检，保证幂等）。"""
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (_TABLE, column),
    )
    row = cur.fetchone()
    return bool(row and row[0])


def apply(conn) -> None:
    """加列（幂等：已存在则跳过）。"""
    cur = conn.cursor()
    try:
        for column, coltype, comment in _COLUMNS:
            if _column_exists(cur, column):
                logger.info("跳过：%s.%s 已存在", _TABLE, column)
                continue
            cur.execute(
                f"ALTER TABLE `{_TABLE}` ADD COLUMN `{column}` {coltype} "
                f"COMMENT %s",
                (comment,),
            )
            logger.info("已新增 %s.%s（%s，纯增量）", _TABLE, column, coltype)
    finally:
        cur.close()
    conn.commit()


def rollback(conn) -> None:
    """删列（仅用于开发/回滚演练；会丢掉计数快照）。"""
    cur = conn.cursor()
    try:
        for column, _coltype, _comment in _COLUMNS:
            if not _column_exists(cur, column):
                continue
            cur.execute(f"ALTER TABLE `{_TABLE}` DROP COLUMN `{column}`")
            logger.info("已删除 %s.%s", _TABLE, column)
    finally:
        cur.close()
    conn.commit()
