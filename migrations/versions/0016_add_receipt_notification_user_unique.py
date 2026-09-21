# -*- coding: utf-8 -*-
"""为 notification_receipts 增加 (notification_id, user_id) 唯一约束
uk_receipt_notification_user（B-36）

背景：模型 docstring 一直写着"每用户一条"，但模型与迁移层都没有唯一键——
"每用户一条"只是文档约定，DB 不拦。重复行的危害：
① 读侧 `.first()` / 投递 worker 的 `setdefault`（A-P1-2）语义不确定——
   "取哪条"全凭行序运气；
② 未读数 / 已读标记按 user_id 聚合，重复行会多计；
③ 它是"投递写入幂等"的前提。

**存量冲突处理（重要）**：直接加约束会因存量重复而失败。本迁移先删除每组
重复行中 id 较大者——**保留 id 最小者**，与读侧既有语义（`.first()` /
`setdefault` 都是"首条胜出"）一致，迁移前后"读到哪条"不变化。与 0011
（cabinet 置 NULL 降级）不同，回执没有"未设置"态可退，重复行本身就是错误
数据；被删行的 id / delivered_channels / channel_status **逐条记 WARNING**
（信息不丢，只是不进库）。清理逻辑在 `NotificationReceipt.repair_duplicates`
（模型层，方言中立），本迁移调它。

**幂等**：约束已存在则整体跳过；清理本身幂等（无重复 no-op）。

**写入侧已核实（B-36 施工勘查）**：无双创建源——`notify()` 的 user 分支单值、
role/broadcast 分支经 DB 查询（`User.id.in_()` / 全表）天然去重、user_roles 有
`uk_user_role`；voice_settings_routes 的回执挂在每次新建的 notification 上。
约束只兜数据层底，不会让正常投递路径抛 IntegrityError。
"""
import logging

logger = logging.getLogger(__name__)

CONSTRAINT_NAME = "uk_receipt_notification_user"

_MDL_WAIT_TIMEOUT_SECONDS = 300


def _constraint_exists(conn, table: str, name: str) -> bool:
    """唯一约束在 MySQL 中体现为同名索引，用 statistics 判断（与 0011 同一手法）"""
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


def _log_blocking_transactions(conn) -> None:
    """加约束失败时打印当前活跃事务，帮助运维定位是谁占着 MDL（0011 同款）。"""
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
        for row in rows:
            query = (row[4] or "").strip()
            logger.error(
                "  trx_id=%s state=%s 已持续=%ss 线程=%s query=%s",
                row[0], row[1], row[2], row[3],
                query[:200] if query else "（空闲事务：事务已开启但当前没有在执行语句）",
            )
    except Exception:  # noqa: BLE001 —— 诊断本身绝不能掩盖原始异常
        logger.warning("打印阻塞事务信息失败", exc_info=True)
    finally:
        cur.close()


def apply(conn) -> None:
    """清理存量重复回执（保 MIN(id)），再建唯一约束（各自幂等）"""
    if _constraint_exists(conn, "notification_receipts", CONSTRAINT_NAME):
        logger.info("跳过：notification_receipts.%s 已存在", CONSTRAINT_NAME)
        return

    from app.models.notification import NotificationReceipt

    removed = NotificationReceipt.repair_duplicates(conn)
    if removed:
        logger.warning(
            "检测到 notification_receipts 存在重复回执（同通知同用户多行），"
            "已删除其中 %s 条（每组保留 id 最小者，被删行 payload 已逐条记 WARNING）",
            removed,
        )

    conn.commit()

    cur = conn.cursor()
    try:
        cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")
        cur.execute(
            "ALTER TABLE `notification_receipts` "
            "ADD UNIQUE KEY `uk_receipt_notification_user` "
            "(`notification_id`, `user_id`), "
            "ALGORITHM=INPLACE, LOCK=NONE"
        )
        logger.info("已加唯一约束 notification_receipts.%s", CONSTRAINT_NAME)
    except Exception:
        _log_blocking_transactions(conn)
        logger.error(
            "加唯一约束 notification_receipts.%s 失败 —— 本次迁移**未完成**。\n"
            "  · 已成功的部分不会重复执行（幂等），重跑只会重试未完成的部分；\n"
            "  · 若错误是 1205 / 1213：仍有并发事务占着表的元数据锁，"
            "请暂停应用流量，或先处理掉上面列出的长事务，然后重跑；\n"
            "  · 确认是否已建成：SHOW INDEX FROM notification_receipts "
            "WHERE Key_name = '%s';",
            CONSTRAINT_NAME,
            CONSTRAINT_NAME,
        )
        raise
    finally:
        cur.close()
    conn.commit()
