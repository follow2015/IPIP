# -*- coding: utf-8 -*-
"""留痕三表新增设备名快照列（设备删除后仍能自证是哪台设备）。

背景（2026-09-18 拍板：留痕不随设备删除而删除，三条路径统一，含机房强删）：
`monitor_incident.root_device_id` / `monitor_suppressed_alert_log.device_id` /
`ai_diagnosis_sessions.device_id` 的外键都是 ``ondelete="SET NULL"`` 且可空，
**但只把 device_id 置空会得到"不可解读的孤儿行"** —— 行还在、事件还在，
却无法回答"这是哪台设备出的事"。而 `devices` 行在机房/机柜/设备三条强删路径上
都会被物理删除，置空后没有任何列能回溯设备身份。

因此本迁移为三表加设备名快照列，配合删除路径上的
「**先写快照、再置空 device_id**」：
  - `monitor_incident.root_device_name`            根因设备名
  - `monitor_suppressed_alert_log.device_name`     被抑制设备名
  - `monitor_suppressed_alert_log.upstream_device_name` 上游设备名
    （该列对应 `upstream_device_id`，**无外键**，DB 既不置空也不报 1451，
      只能由应用层显式处置，故同样需要快照）
  - `ai_diagnosis_sessions.device_name`            诊断目标设备名

存量回填：迁移时设备行大多仍在，按 device_id 关联 `devices` 回填一次，
使历史行也具备自证能力（真库三表合计仅 349 行，逐表 UPDATE 可接受）。

**幂等**：每条 列存在检查 / 回填 各自独立跳过；重跑安全。
**降级（手动）**：`ALTER TABLE <t> DROP COLUMN <c>;`（快照列可丢弃，不破坏主数据）。
**为何不加外键**：快照列是**历史值**，不允许随设备变化而联动，故意保持无约束的纯文本。
"""
import logging

logger = logging.getLogger(__name__)

COLUMNS = [
    (
        "monitor_incident",
        "root_device_name",
        "根因设备名快照(设备删除后置空 root_device_id,靠此列自证)",
        "root_device_id",
    ),
    (
        "monitor_suppressed_alert_log",
        "device_name",
        "被抑制设备名快照(设备删除后置空 device_id,靠此列自证)",
        "device_id",
    ),
    (
        "monitor_suppressed_alert_log",
        "upstream_device_name",
        "上游设备名快照(upstream_device_id 无外键,只能显式处置)",
        "upstream_device_id",
    ),
    (
        "ai_diagnosis_sessions",
        "device_name",
        "诊断目标设备名快照(设备删除后置空 device_id,靠此列自证)",
        "device_id",
    ),
]

COLUMN_LENGTH = 100


def _column_exists(conn, table: str, column: str) -> bool:
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


def _add_column(conn, table: str, column: str, comment: str) -> bool:
    """加列；已存在则跳过。返回是否真的加过。"""
    if _column_exists(conn, table, column):
        logger.info("跳过：%s.%s 已存在", table, column)
        return False
    cur = conn.cursor()
    try:
        cur.execute(
            f"ALTER TABLE `{table}` ADD COLUMN `{column}` "
            f"VARCHAR({COLUMN_LENGTH}) NULL COMMENT %s",
            (comment,),
        )
        conn.commit()
        logger.info("已加列 %s.%s", table, column)
        return True
    finally:
        cur.close()


def _backfill(conn, table: str, column: str, source: str) -> None:
    """按 source 列关联 devices 回填设备名；只填 NULL 行，重跑安全。

    只回填 `device_name`/`root_device_name` 里仍为空、且 source 列非空的行。
    设备行已不存在（source 指向已物理删除的设备）时保持 NULL —— 无源可回填，
    下一次同类删除也不会再产出这种行。
    """
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT COUNT(*) FROM `{table}` WHERE `{column}` IS NULL "
            f"AND `{source}` IS NOT NULL"
        )
        pending = int(cur.fetchone()[0])
        if not pending:
            logger.info("跳过回填：%s.%s 无待回填行", table, column)
            return
        cur.execute(
            f"UPDATE `{table}` t JOIN `devices` d ON d.id = t.`{source}` "
            f"SET t.`{column}` = d.device_name "
            f"WHERE t.`{column}` IS NULL AND t.`{source}` IS NOT NULL"
        )
        conn.commit()
        logger.info("已回填 %s.%s：%s 行（待回填 %s）", table, column, cur.rowcount, pending)
    finally:
        cur.close()


def apply(conn) -> None:
    """逐列加列 → 回填（各步独立幂等）"""
    for table, column, comment, source in COLUMNS:
        _add_column(conn, table, column, comment)
        _backfill(conn, table, column, source)
