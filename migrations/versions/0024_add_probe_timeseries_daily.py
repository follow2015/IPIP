# -*- coding: utf-8 -*-
"""补建 `device_monitor_timeseries_daily`（存量升级路径修复）

背景：升级路径上永远缺一张表
----------------------------
``device_monitor_timeseries_daily`` 由 ``migrations/add_timeseries_daily_table.py``
建表，但该文件**只躺在 `migrations/` 目录里**，从未进入任何迁移链：

- 它不在老式 ``migrations/migrations_runner.py`` 的 ``MIGRATIONS`` 注册表里
  （该注册表 33 条，实际目录 110 个脚本 ⇒ 78 个孤儿，本文件是其中之一）；
- 它也不在 ``migrations/versions/`` 链里（本仓 schema 变更的唯一活机制）。

后果是**不对称**的：

- **全新安装**：导入 ``0000_baseline.sql``（快照里已含本表，第 472 行）⇒ 有表；
- **存量升级**：没有任何一条路径会建它 ⇒ **永远没有 daily 表**。

而 ORM 侧 ``app/models/device_monitor_timeseries_daily.py`` 已声明该模型 ⇒
``collect_schema_drift()`` 会持续报"模型已声明但库中缺失"，``flask db-check``
在存量机上恒红。更实际的影响：``monitor-archive`` 的 ``downsample_to_daily()``
在存量机上每次都撞 1146（表不存在），天级长期趋势层**从未真正生效**。

为什么是补建而不是改注册表
--------------------------
老式 ``migrations_runner`` 在生产代码里**零调用点**（全仓仅 ``migrations.seed_rbac``
被引用，那是数据脚本不是 runner）⇒ 它是一条**已死的机制**。往死机制里补一条
条目，只会让"看起来修好了"，运行期行为不变。故本迁移进 ``versions/`` 链。

DDL 口径
--------
与 ``0000_baseline.sql`` 第 472–484 行**逐字一致**（含 ``float`` 精度、外键名
``fk_daily_device``、表 COMMENT），也与 ORM
``app/models/device_monitor_timeseries_daily.py`` 同口径（含 ``ON DELETE CASCADE``）。
三处不一致会让"全新安装"与"存量升级"两套库结构分叉，而这正是本迁移要消灭的病。

在线 DDL 纪律（与 0011/0016–0022 一致）
--------------------------------------
- 先 ``SET SESSION lock_wait_timeout = 300``，避免 MDL 等待雪崩；
- 本表是**新建空表**，无存量行，无 COPY 重写，天然在线；
- 外键随建表语句一并创建，避免二次 ALTER。

**幂等**：``SHOW TABLES LIKE`` 已存在则整体跳过（与 0022 同策略，不做逐列补齐——
表结构由本迁移一次性定义；存量表的列缺失另案处理）。

**无 downgrade**：本仓 0013–0023 全部只有 ``apply(conn)``，``def downgrade`` 零命中，
``app/__init__.py`` 也未注册 ``db-downgrade`` 命令。回滚走手工 DDL。

**不回填历史数据**：本迁移只补容器。存量 hourly 数据 → daily 的回填由
``flask monitor-archive`` 的 ``downsample_to_daily()`` 在下一个归档周期自然完成
（它按 ``hour_bucket < cutoff`` 全量扫，不依赖本迁移的执行时点）。
"""
import logging

logger = logging.getLogger(__name__)

_MDL_WAIT_TIMEOUT_SECONDS = 300

_TABLE = "device_monitor_timeseries_daily"

_DDL = """
CREATE TABLE `device_monitor_timeseries_daily` (
  `device_id` bigint NOT NULL,
  `metric` varchar(32) NOT NULL,
  `day_bucket` date NOT NULL,
  `avg_value` float NOT NULL,
  `min_value` float NOT NULL,
  `max_value` float NOT NULL,
  `sample_count` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`device_id`,`metric`,`day_bucket`),
  CONSTRAINT `fk_daily_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='监控时序天级预聚合，从 hourly 降采样，保留730天（架构3 长期趋势层）'
"""


def _table_exists(conn, table: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(f"SHOW TABLES LIKE '{table}'")
        return bool(cur.fetchall())
    finally:
        cur.close()


def apply(conn) -> None:
    """补建天级预聚合表（幂等；已存在则跳过）"""
    if _table_exists(conn, _TABLE):
        logger.info("跳过：表 %s 已存在（全新安装路径已由 0000_baseline.sql 建出）", _TABLE)
        return

    cur = conn.cursor()
    try:
        cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")
        cur.execute(_DDL)
    finally:
        cur.close()
    logger.info("已补建表 %s（存量升级路径此前无建表入口）", _TABLE)
