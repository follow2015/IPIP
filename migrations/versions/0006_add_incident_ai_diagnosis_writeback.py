# -*- coding: utf-8 -*-
"""monitor_incident 加 AI 诊断结论写回列（AI 诊断 × 告警集成 ⑤）。

与 0004（ai_diagnosis_sessions.incident_id）互为表里：
- 0004 让「诊断知道属于哪个事件」——按事件去重、避免重复诊断；
- 本迁移让「事件知道最新诊断结论」——运维在告警页直接看到根因摘要，
  不必点进诊断会话去翻 rounds_json。

两表互相持有对方的外键是刻意的（都是 SET NULL、都可空），MySQL 允许，
且不影响插入顺序。

幂等：列存在即跳过。
"""
import logging

logger = logging.getLogger(__name__)

TABLE = "monitor_incident"
FK = "fk_incident_ai_diagnosis_session"


def _column_exists(conn, column: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s "
            "AND column_name = %s",
            (TABLE, column),
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
        if not _column_exists(conn, "ai_diagnosis_session_id"):
            cur.execute(
                f"ALTER TABLE `{TABLE}` "
                f"ADD COLUMN `ai_diagnosis_session_id` bigint NULL "
                f"COMMENT '最新一次 AI 诊断会话ID（诊断会话删除后置空）' "
                f"AFTER `closed_at`"
            )
            logger.info("已补列 %s.ai_diagnosis_session_id", TABLE)
        else:
            logger.info("跳过：%s.ai_diagnosis_session_id 已存在", TABLE)

        if not _column_exists(conn, "ai_diagnosis_summary"):
            cur.execute(
                f"ALTER TABLE `{TABLE}` "
                f"ADD COLUMN `ai_diagnosis_summary` text NULL "
                f"COMMENT '最新一次 AI 诊断结论摘要（供告警页直接展示）' "
                f"AFTER `ai_diagnosis_session_id`"
            )
            logger.info("已补列 %s.ai_diagnosis_summary", TABLE)
        else:
            logger.info("跳过：%s.ai_diagnosis_summary 已存在", TABLE)

        if not _fk_exists(conn, FK):
            cur.execute(
                f"UPDATE `{TABLE}` SET `ai_diagnosis_session_id` = NULL "
                f"WHERE `ai_diagnosis_session_id` IS NOT NULL "
                f"AND `ai_diagnosis_session_id` NOT IN "
                f"(SELECT `id` FROM `ai_diagnosis_sessions`)"
            )
            cur.execute(
                f"ALTER TABLE `{TABLE}` ADD CONSTRAINT `{FK}` "
                f"FOREIGN KEY (`ai_diagnosis_session_id`) "
                f"REFERENCES `ai_diagnosis_sessions` (`id`) ON DELETE SET NULL"
            )
            logger.info("已补外键 %s", FK)
    finally:
        cur.close()
    conn.commit()
