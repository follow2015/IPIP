# -*- coding: utf-8 -*-
"""M1 分层对称化：给指标侧补上预聚合层

背景：分层保留架构在指标侧是断的
--------------------------------
``device_metric_timeseries``（指标明细）22,330,077 行 / 3,744 MB，
``device_monitor_probe_events``（探测明细）269,020 行 / 55 MB —— **体积比 68:1**，
指标明细占了时序总存量的 98.5%。而它恰恰是**唯一没有预聚合层**的表：
探测侧有 hourly(90d) + daily(730d) 两级，指标侧一级都没有。

结果就是"分层保留"只在占 1.5% 的那张表上生效。本迁移把指标侧补成同构：
``明细 7~14d → hourly 90d → daily 730d``，让 3.7 GB 的明细不再是唯一副本。

本迁移做三件事
--------------
1. ``device_metric_timeseries`` 增 ``value_num DOUBLE NULL``（B2）；
2. 建 ``device_metric_timeseries_hourly``（B1）；
3. 建 ``device_metric_timeseries_daily``（B1）。

不做：历史数据的 ``value_num`` 回填与聚合回填 —— 见下方"回填不是本迁移的事"。

分区表加列的在线 DDL 纪律（**本迁移最大的操作风险**）
------------------------------------------------------
``device_metric_timeseries`` 是**按日 RANGE 分区**的大表（3,744 MB）。
对它 ADD COLUMN 若退化成 COPY，会重建全部分区并长时间持锁。故本迁移
采用**分级降级**，且**刻意不把 COPY 作为兜底**：

1. ``ALGORITHM=INSTANT`` —— MySQL 8.0.29+ / 8.4 支持 instant 加列
   （加在末尾、允许 NULL ⇒ 满足 instant 前提），只改元数据，秒级；
   **注意 INSTANT 不允许与任何 LOCK 子句同用**，故此处不写 LOCK（写 LOCK=NONE
   会被 MySQL 以 1221 拒绝，反而落不到 instant 快速通道）。
2. 失败则 ``ALGORITHM=INPLACE, LOCK=NONE`` —— 仍需重建但**不阻塞 DML**；
3. 两者都失败 ⇒ **抛异常并停在这里**，不做 COPY。

第 3 点是刻意的：一次静默的 COPY（锁住 3.7 GB 的采集写入表若干分钟到几十分钟）
比一次明确的失败危险得多 —— 前者会表现为"监控采集那阵子没数据"，且没人会
把它和这次升级联系起来。故把决策权交回人：**在业务低峰重跑本迁移**，
或先手工确认 ``ALTER`` 的实际算法。

回填不是本迁移的事
------------------
- ``value_num``：存量 22M 行加列后全为 NULL，需要回填。回填必须走应用层
  （``app/utils/metric_value.py::parse_metric_value_num`` 的**严格**口径），
  因为 MySQL 的 ``REGEXP_SUBSTR`` 无法提取捕获组，写不出等价 SQL。
  擅自用宽松正则回填会让 ``"port 3 down"`` 变成 ``3.0`` 并污染聚合。
- 聚合回填：由 ``flask monitor-archive`` 的 ``downsample_to_metric_hourly()``
  在下一归档周期自然完成（按 ``collected_at < cutoff`` 全量扫）。

**部署顺序（硬约束）**：本迁移**必须先于**写入侧代码生效。
``DeviceMetricTimeseriesRepository.add_many()`` 会写 ``value_num`` 列，
列不存在时 INSERT 直接 1054 ⇒ **整条指标采集链路全挂**。
即：升级流程必须是「跑迁移 → 再重启应用」，不能倒过来。

幂等
----
- 加列：``information_schema.COLUMNS`` 已存在则跳过；
- 建表：``SHOW TABLES LIKE`` 已存在则跳过（与 0022/0024 同策略）。
  注意全新安装的库也会跑到本迁移（``0000_baseline.covers`` 只 stamp 0000/0001），
  其 baseline 已含本迁移的全部目标对象 ⇒ 走跳过分支，不做任何写操作。

**无 downgrade**：本仓 0013–0024 全部只有 ``apply(conn)``，``def downgrade``
零命中，``app/__init__.py`` 也未注册 ``db-downgrade`` 命令。回滚走手工 DDL：
DROP 两张聚合表 + DROP COLUMN value_num（聚合表空表可随时重建，value_num
为派生列可随时重算 ⇒ 回滚代价低）。
"""
import logging

logger = logging.getLogger(__name__)

_MDL_WAIT_TIMEOUT_SECONDS = 300

_TABLE_METRIC = "device_metric_timeseries"
_COLUMN = "value_num"

_TABLES = (
    "device_metric_timeseries_hourly",
    "device_metric_timeseries_daily",
)

_DDL_HOURLY = """
CREATE TABLE `device_metric_timeseries_hourly` (
  `device_id` bigint NOT NULL COMMENT '关联设备ID',
  `metric_key` varchar(64) NOT NULL COMMENT '指标 key，与明细表同名同义（如 cpu_usage / if_status）',
  `index_key` varchar(128) NOT NULL DEFAULT '' COMMENT '指标实例索引（端口号 ifIndex）；不可省，跨实例平均是错语义',
  `hour_bucket` datetime NOT NULL COMMENT '小时桶起点（UTC）',
  `avg_value` double DEFAULT NULL COMMENT '桶内 value_num 均值；非数值指标为 NULL',
  `min_value` double DEFAULT NULL COMMENT '桶内 value_num 最小值；非数值指标为 NULL',
  `max_value` double DEFAULT NULL COMMENT '桶内 value_num 最大值；非数值指标为 NULL',
  `sample_count` int NOT NULL DEFAULT '0' COMMENT '桶内采样点数',
  `last_value` varchar(255) DEFAULT NULL COMMENT '桶内时间最晚的原始 value（状态词靠它保真）',
  `state_changes` int NOT NULL DEFAULT '0' COMMENT '桶内 value 跃变次数（相邻采样不同计 1）；up→down→up 记 2',
  `breach_count` int NOT NULL DEFAULT '0' COMMENT '桶内 breached=1 的采样数',
  `worst_severity` varchar(20) DEFAULT NULL COMMENT '桶内最坏告警级别 ok/warn/crit',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次聚合时间',
  PRIMARY KEY (`device_id`,`metric_key`,`index_key`,`hour_bucket`),
  KEY `ix_dmts_hourly_bucket` (`hour_bucket`),
  CONSTRAINT `fk_dmts_hourly_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指标时序小时级预聚合（M1 分层对称化，保留90天）'
"""

_DDL_DAILY = """
CREATE TABLE `device_metric_timeseries_daily` (
  `device_id` bigint NOT NULL COMMENT '关联设备ID',
  `metric_key` varchar(64) NOT NULL COMMENT '指标 key，与明细表同名同义',
  `index_key` varchar(128) NOT NULL DEFAULT '' COMMENT '指标实例索引（端口号 ifIndex）；不可省，跨实例平均是错语义',
  `day_bucket` date NOT NULL COMMENT '日期桶（UTC，由 DATE(hour_bucket) 产出）',
  `avg_value` double DEFAULT NULL COMMENT '当天各小时桶 avg_value 的均值；非数值指标为 NULL',
  `min_value` double DEFAULT NULL COMMENT '当天各小时桶 min_value 的最小值',
  `max_value` double DEFAULT NULL COMMENT '当天各小时桶 max_value 的最大值',
  `sample_count` int NOT NULL DEFAULT '0' COMMENT '当天覆盖的小时桶数',
  `last_value` varchar(255) DEFAULT NULL COMMENT '当天最后一个小时桶的 last_value（状态词保真）',
  `state_changes` int NOT NULL DEFAULT '0' COMMENT '当天各小时桶 state_changes 之和',
  `breach_count` int NOT NULL DEFAULT '0' COMMENT '当天各小时桶 breach_count 之和',
  `worst_severity` varchar(20) DEFAULT NULL COMMENT '当天最坏告警级别 ok/warn/crit',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次聚合时间',
  PRIMARY KEY (`device_id`,`metric_key`,`index_key`,`day_bucket`),
  KEY `ix_dmts_daily_bucket` (`day_bucket`),
  CONSTRAINT `fk_dmts_daily_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='设备指标时序天级预聚合（M1 分层对称化，保留730天长期趋势）'
"""

_DDL_BY_TABLE = {
    "device_metric_timeseries_hourly": _DDL_HOURLY,
    "device_metric_timeseries_daily": _DDL_DAILY,
}

_ADD_COLUMN_ALTERS = (
    "ALTER TABLE `{table}` ADD COLUMN `{col}` double DEFAULT NULL "
    "COMMENT 'value 的数值派生列（非数值指标为 NULL），供 M1 预聚合做 AVG/MIN/MAX，"
    "避免 CAST(value) 全表扫；填充口径见 app/utils/metric_value.py::parse_metric_value_num', "
    "ALGORITHM=INSTANT",
    "ALTER TABLE `{table}` ADD COLUMN `{col}` double DEFAULT NULL "
    "COMMENT 'value 的数值派生列（非数值指标为 NULL），供 M1 预聚合做 AVG/MIN/MAX，"
    "避免 CAST(value) 全表扫；填充口径见 app/utils/metric_value.py::parse_metric_value_num', "
    "ALGORITHM=INPLACE, LOCK=NONE",
)


def _table_exists(conn, table: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(f"SHOW TABLES LIKE '{table}'")
        return bool(cur.fetchall())
    finally:
        cur.close()


def _column_exists(conn, table: str, column: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.COLUMNS "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (table, column),
        )
        return bool(cur.fetchall())
    finally:
        cur.close()


def apply(conn) -> None:
    """加 value_num 列 + 建两张聚合表（幂等；加列走 INSTANT → INPLACE 分级降级）"""
    cur = conn.cursor()
    try:
        cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")

        if _column_exists(conn, _TABLE_METRIC, _COLUMN):
            logger.info("跳过：%s.%s 已存在", _TABLE_METRIC, _COLUMN)
        else:
            last_err = None
            for i, tpl in enumerate(_ADD_COLUMN_ALTERS, start=1):
                sql = tpl.format(table=_TABLE_METRIC, col=_COLUMN)
                try:
                    cur.execute(sql)
                except Exception as exc:  # noqa: BLE001 —— 需要按算法逐个试，异常是控制流
                    last_err = exc
                    logger.warning(
                        "加列算法 %d 不可用（%s），尝试下一种", i, exc
                    )
                    continue
                logger.info("已加列 %s.%s（算法方案 %d）", _TABLE_METRIC, _COLUMN, i)
                break
            else:
                raise RuntimeError(
                    f"无法为分区表 {_TABLE_METRIC} 在线加列 {_COLUMN}："
                    f"INSTANT 与 INPLACE/LOCK=NONE 均被拒绝（最后错误：{last_err}）。"
                    "本迁移**刻意不回退到 COPY**：该表 3,744 MB 且是采集写入表，"
                    "静默 COPY 会表现为“监控采集那阵子没数据”，比失败更难归因。"
                    "请于业务低峰重跑；或先手工确认该 MySQL 版本对分区表的 "
                    "instant add column 支持情况，再决定是否改用 COPY。"
                ) from last_err

        for table in _TABLES:
            if _table_exists(conn, table):
                logger.info("跳过：表 %s 已存在", table)
                continue
            cur.execute(_DDL_BY_TABLE[table])
            logger.info("已建表 %s（M1 分层对称化）", table)
    finally:
        cur.close()
