# -*- coding: utf-8 -*-
"""monitor_dynamic_config 补 created_at 列（时间统一 UTC 整改 C1）。

背景：2026-09-08 的「时间口径统一到 UTC」提交同时改了模型
（app/models/monitor_dynamic_config.py 新增 created_at）与
migrations/versions/0000_baseline.sql（手工补列），但**没有配套增量迁移**。
结果：全新安装（导入 baseline）有该列，而在此之前已 stamp 过的存量库没有，
ORM SELECT 会显式列出 created_at → 存量环境报 1054 Unknown column，
动态配置读写全部 500，且两套环境的 schema 永久漂移。

本迁移补上唯一修正案：对库存缺列的表 ADD COLUMN，幂等跳过已有该列者。
新装的 baseline 已含该列 → 走幂等跳过分支，无需特判。

纪律提醒：baseline 的重导必须走 scripts/export_schema_dump.py（内含导出自检闸
与 covers 清单同步），禁止手工编辑——本次漂移正源于手改 baseline。
"""
import logging

logger = logging.getLogger(__name__)

TABLE = "monitor_dynamic_config"
COLUMN = "created_at"


def _column_exists(conn) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s "
            "AND column_name = %s",
            (TABLE, COLUMN),
        )
        row = cur.fetchone()
        return bool(row and row[0])
    finally:
        cur.close()


def apply(conn) -> None:
    if _column_exists(conn):
        logger.info("跳过：%s.%s 已存在（新装 baseline 已含该列，幂等）", TABLE, COLUMN)
        return

    cur = conn.cursor()
    try:
        cur.execute(
            f"ALTER TABLE `{TABLE}` "
            f"ADD COLUMN `{COLUMN}` datetime NOT NULL DEFAULT (now()) "
            f"COMMENT '创建时间' AFTER `description`"
        )
    finally:
        cur.close()
    conn.commit()
    logger.info("已补列 %s.%s（存量行以当前 UTC 时间填充）", TABLE, COLUMN)
