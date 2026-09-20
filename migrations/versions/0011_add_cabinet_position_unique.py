# -*- coding: utf-8 -*-
"""为 cabinets 增加 (room_id, row, col) 唯一约束 uk_cabinet_position（设计文档 §3.4）

背景：此前 cabinets 只有 `(room_id, cabinet_number)` 唯一，两台机柜可以被填成同一
坐标。前端平面图的兜底是"每格只画 id 最小的一台、其余进入「位置冲突」区并打角标"，
但那只是让问题**可见**；根因在数据层，故补唯一约束硬兜住。

**存量冲突处理（重要）**：直接加约束会因存量重复坐标而失败。本迁移先把"同一坐标中
id 较大者"（通常是后来新建的那台）的 `row` / `col` 置 NULL——即退回"未设置位置"，
**机柜本身不删除**，它会出现在平面图下方的「未设置位置的机柜」列表里等待重新分配，
同时逐条打 WARNING 日志便于人工复核。

置 NULL 而不是删除，是为了保证迁移不丢数据、并留下可追溯的痕迹。保留 id 最小者与
前端的渲染选择（每格画 id 最小的一台）保持一致，避免迁移前后"图上显示哪台"发生变化。

**幂等**：约束已存在则整体跳过；重复执行安全（第二次跑时冲突数据已被清干净）。

`row` / `col` 为 NULL 的行不参与唯一性（唯一索引允许多个 NULL），故未定位机柜不受影响。
"""
import logging

logger = logging.getLogger(__name__)

CONSTRAINT_NAME = "uk_cabinet_position"


def _constraint_exists(conn, table: str, name: str) -> bool:
    """唯一约束在 MySQL 中体现为同名索引，用 statistics 判断（与 0010 同一手法）"""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s",
            (table, name),
        )
        row = cur.fetchone()
        return bool(row and row[0])
    finally:
        cur.close()


_DUPLICATE_GROUP_SQL = """
    SELECT room_id, `row`, `col`, MIN(id) AS keep_id
    FROM cabinets
    WHERE `row` IS NOT NULL AND `col` IS NOT NULL
    GROUP BY room_id, `row`, `col`
    HAVING COUNT(*) > 1
"""

_CLEANUP_BATCH_SIZE = 200

_MDL_WAIT_TIMEOUT_SECONDS = 300


def _log_duplicates(conn) -> int:
    """先打印冲突明细（含机柜编号，便于人工核对），返回冲突行数"""
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT c.id, c.room_id, c.cabinet_number, c.`row`, c.`col`
            FROM cabinets c
            JOIN ({_DUPLICATE_GROUP_SQL}) dup
              ON c.room_id = dup.room_id AND c.`row` = dup.`row` AND c.`col` = dup.`col`
            WHERE c.id <> dup.keep_id
            """
        )
        rows = cur.fetchall()
        for cabinet_id, room_id, cabinet_number, row, col in rows:
            logger.warning(
                "机柜位置冲突：id=%s 机房=%s 编号=%s 原坐标=(%s,%s)"
                " → 已置为「未设置位置」，请在机房平面图中重新分配",
                cabinet_id,
                room_id,
                cabinet_number,
                row,
                col,
            )
        return len(rows)
    finally:
        cur.close()


def _demote_duplicates(conn) -> int:
    """分批把冲突行（同坐标中 id 较大者）的坐标置空，返回受影响行数。

    每批 `LIMIT _CLEANUP_BATCH_SIZE` 并在批间 commit：单批持锁时间极短，显著降低
    与在线业务事务互相等待（1213 死锁）的概率。见 `_CLEANUP_BATCH_SIZE` 的说明。
    """
    cur = conn.cursor()
    total = 0
    try:
        while True:
            cur.execute(
                f"""
                UPDATE cabinets c
                JOIN ({_DUPLICATE_GROUP_SQL}) dup
                  ON c.room_id = dup.room_id AND c.`row` = dup.`row` AND c.`col` = dup.`col`
                SET c.`row` = NULL, c.`col` = NULL
                WHERE c.id <> dup.keep_id
                LIMIT {_CLEANUP_BATCH_SIZE}
                """
            )
            affected = cur.rowcount
            conn.commit()
            total += affected
            if affected < _CLEANUP_BATCH_SIZE:
                return total
    finally:
        cur.close()


def _log_blocking_transactions(conn) -> None:
    """加约束失败时打印当前活跃事务，帮助运维定位是谁占着 MDL。

    典型场景：应用仍在服务（哪怕只是一条慢查询或一个未提交的事务），迁移就一直
    抢不到 `cabinets` 的元数据锁。此时最可靠的做法是**暂停应用流量后重跑迁移**。
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT trx_id, trx_state, "
            "TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS seconds, "
            "trx_mysql_thread_id, trx_query "
            "FROM information_schema.innodb_trx "
            "ORDER BY trx_started LIMIT 10"
        )
        rows = cur.fetchall()
        if not rows:
            logger.error(
                "加唯一约束失败，但当前没有活跃事务 —— 可能是别的会话在等待同一张表的 "
                "MDL（例如另一个未完成的 ALTER）。"
            )
            return
        logger.error("加唯一约束失败，当前活跃事务（越靠前越老）：")
        idle = 0
        for row in rows:
            query = (row[4] or "").strip()
            if not query:
                idle += 1
            logger.error(
                "  trx_id=%s state=%s 已持续=%ss 线程=%s query=%s",
                row[0],
                row[1],
                row[2],
                row[3],
                query[:200] if query else "（空闲事务：事务已开启但当前没有在执行语句）",
            )
        if idle:
            logger.error(
                "  注意：上面有 %s 个**空闲事务**（query 为空）。这种事务开着却不提交，"
                "持有的元数据锁会一直挡住 DDL，跟有没有流量无关——等再久也没用。"
                "通常是某个连接开了事务没结束（连接池里被进程持有的长连接最常见）。"
                "处理办法：把所有连库的进程（Web / celery worker / beat / 采集脚本）"
                "全部停掉，确认下面的查询返回空，再重跑迁移：\n"
                "    SELECT trx_id, trx_state, trx_query FROM information_schema.innodb_trx;",
                idle,
            )
    except Exception:  # noqa: BLE001 —— 诊断本身绝不能掩盖原始异常
        logger.warning("打印阻塞事务信息失败", exc_info=True)
    finally:
        cur.close()


def apply(conn) -> None:
    """置空存量冲突坐标，再建唯一约束（各自幂等）"""
    if _constraint_exists(conn, "cabinets", CONSTRAINT_NAME):
        logger.info("跳过：cabinets.%s 已存在", CONSTRAINT_NAME)
        return

    conflicts = _log_duplicates(conn)
    if conflicts:
        demoted = _demote_duplicates(conn)
        logger.warning(
            "检测到 %s 台机柜的坐标与同机房其它机柜重复，已把其中 %s 台置为「未设置位置」"
            "（机柜未删除，仅在平面图下方列表中等待重新分配）",
            conflicts,
            demoted,
        )

    conn.commit()

    cur = conn.cursor()
    try:
        cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")
        cur.execute(
            "ALTER TABLE `cabinets` "
            "ADD UNIQUE KEY `uk_cabinet_position` (`room_id`, `row`, `col`), "
            "ALGORITHM=INPLACE, LOCK=NONE"
        )
        logger.info("已加唯一约束 cabinets.%s", CONSTRAINT_NAME)
    except Exception:
        _log_blocking_transactions(conn)
        logger.error(
            "加唯一约束 cabinets.%s 失败 —— 本次迁移**未完成**。\n"
            "  · 已成功的部分不会重复执行（幂等），重跑只会重试未完成的部分；\n"
            "  · 若错误是 1205 / 1213：仍有并发事务占着 cabinets 的元数据锁，"
            "请暂停应用流量，或先处理掉上面列出的长事务，然后重跑；\n"
            "  · 确认是否已建成：SHOW INDEX FROM cabinets WHERE Key_name = '%s';",
            CONSTRAINT_NAME,
            CONSTRAINT_NAME,
        )
        raise
    finally:
        cur.close()
    conn.commit()
