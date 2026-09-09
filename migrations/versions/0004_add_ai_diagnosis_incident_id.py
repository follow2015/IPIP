# -*- coding: utf-8 -*-
"""ai_diagnosis_sessions 补 incident_id 外键（AI 诊断 × 告警集成 ①）。

背景：告警侧已有三级事件聚合（L1 规则 / L2 拓扑 / L3 变更，落 monitor_incident），
但 AI 深度诊断会话只按 device_id 归属——「这次诊断是为哪个事件做的」无处记录。
后果：一次根因故障（上游炸 + N 条下游关联告警）会触发多条重复诊断，且诊断结论
无法回到事件上供运维在告警页直接看到。

本迁移补 incident_id 列 + (incident_id, status) 索引 + 外键，为「按事件去重」
与「结论写回事件」铺路。列可为 NULL：手工发起的诊断本就不属于任何事件。

纪律：
- monitor_incident.id 为 BIGINT（项目 FK 铁律），此处必须 BIGINT，用 INT 会 3780。
- 三步均幂等（列/索引/外键分别探测），存量库重复执行安全；新装 baseline 不含
  本列，故全新安装也会执行本迁移（不写进 covers）。
"""
import logging

logger = logging.getLogger(__name__)

TABLE = "ai_diagnosis_sessions"
COLUMN = "incident_id"
INDEX = "idx_ai_diag_incident_status"
FK = "fk_ai_diag_incident"


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


def _index_exists(conn, name: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = %s "
            "AND index_name = %s",
            (TABLE, name),
        )
        row = cur.fetchone()
        return bool(row and row[0])
    finally:
        cur.close()


def _fk_exists(conn, name: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.table_constraints "
            "WHERE constraint_schema = DATABASE() AND table_name = %s "
            "AND constraint_name = %s AND constraint_type = 'FOREIGN KEY'",
            (TABLE, name),
        )
        row = cur.fetchone()
        return bool(row and row[0])
    finally:
        cur.close()


def apply(conn) -> None:
    cur = conn.cursor()
    try:
        if not _column_exists(conn):
            cur.execute(
                f"ALTER TABLE `{TABLE}` "
                f"ADD COLUMN `{COLUMN}` bigint NULL "
                f"COMMENT '关联监控事件ID（incident 级诊断；事件删除后保留会话供回溯）' "
                f"AFTER `user_id`"
            )
            logger.info("已补列 %s.%s", TABLE, COLUMN)
        else:
            logger.info("跳过：%s.%s 已存在", TABLE, COLUMN)

        if not _index_exists(conn, INDEX):
            cur.execute(
                f"ALTER TABLE `{TABLE}` ADD INDEX `{INDEX}` (`{COLUMN}`, `status`)"
            )
            logger.info("已补索引 %s", INDEX)

        if not _fk_exists(conn, FK):
            cur.execute(
                f"UPDATE `{TABLE}` SET `{COLUMN}` = NULL "
                f"WHERE `{COLUMN}` IS NOT NULL "
                f"AND `{COLUMN}` NOT IN (SELECT `id` FROM `monitor_incident`)"
            )
            cur.execute(
                f"ALTER TABLE `{TABLE}` ADD CONSTRAINT `{FK}` "
                f"FOREIGN KEY (`{COLUMN}`) REFERENCES `monitor_incident` (`id`) "
                f"ON DELETE SET NULL"
            )
            logger.info("已补外键 %s", FK)
    finally:
        cur.close()
    conn.commit()
