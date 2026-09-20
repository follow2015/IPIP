# -*- coding: utf-8 -*-
"""rooms 新增 room_number（房间号）并建立组合唯一 uk_room_name_number (name, room_number)

背景（实施计划《机房房间号与名称分组改造》）：
- `name` 从"记录唯一名"降级为"分组键 + 展示名"——同一物理机房拆成多条 Room 记录时
  通过相同名称天然归组（总览按名称分组）；
- `room_number` 作为记录的业务身份，在机房名称组内唯一（组合唯一）；
- 存量回填：`room_number = 归一化(name)`（"原来的机房名"就是它的房间号，语义自然）。

**回填必须做归一化（v3 复核）**：写时归一（NFKC 全半角 + Cf 不可见字符剔除 + strip）
只对新增写入生效，不清洗存量。存量 name 里可能已有 "Ａ栋机房"、零宽字符等脏字符，
直接搬进房间号会与新写入口径分裂。归一化逻辑与 `RoomService._normalize_grouping_value`
保持一致（迁移环境独立于 app，此处本地实现一份，勿两处漂移）。

**回填防撞（v3 复核）**：生产 MySQL（*_ai_ci）下名称查重不区分大小写，存量 name 天然
满足组合唯一；但 SQLite/开发库查重是精确匹配，可能存在仅大小写不同的存量 name，历史
上绕过查重的写入也可能留下重名——回填后建唯一键会直接失败。防撞：按归一化后的 name
检测重复，冲突记录追加 `-{id}` 后缀（唯一且可追溯），并在日志输出被改写清单。

**幂等**：列已存在 / 回填已无 NULL 行 / 列已 NOT NULL / 约束已存在，各步骤独立跳过。

**部署**：与 0011 同理建议低峰执行（`ADD UNIQUE KEY` 抢 rooms 的 MDL）。
降级路径（手动）：`ALTER TABLE rooms DROP INDEX uk_room_name_number;`
`ALTER TABLE rooms MODIFY COLUMN room_number VARCHAR(50) NULL;`（回填值不回删，无破坏）。
"""
import logging
import unicodedata

logger = logging.getLogger(__name__)

COLUMN_NAME = "room_number"
CONSTRAINT_NAME = "uk_room_name_number"

_MDL_WAIT_TIMEOUT_SECONDS = 300


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


def _column_is_nullable(conn, table: str, column: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (table, column),
        )
        row = cur.fetchone()
        return bool(row and row[0] == "YES")
    finally:
        cur.close()


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


def _normalize_grouping_value(value):
    """与 RoomService._normalize_grouping_value 保持一致（迁移环境独立于 app，本地实现）。

    Cf 格式字符剔除 → NFKC 全半角归一 → 去首尾空白；纯隐形输入返回 None。
    """
    cleaned = "".join(ch for ch in value if unicodedata.category(ch) != "Cf")
    normalized = unicodedata.normalize("NFKC", cleaned).strip()
    return normalized or None


def _backfill(conn) -> None:
    """为存量行回填 room_number = 归一化(name)，组内撞名时追加 -{id} 后缀。

    rooms 表为十级量级，逐行 UPDATE 可接受；撞名清单打 WARNING 供人工核对。
    """
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT id, name FROM `rooms` WHERE `{COLUMN_NAME}` IS NULL ORDER BY id"
        )
        rows = cur.fetchall()
        if not rows:
            logger.info("跳过回填：rooms.%s 无 NULL 行", COLUMN_NAME)
            return

        seen: dict = {}
        updates = []
        for room_id, name in rows:
            normalized = _normalize_grouping_value(name or "")
            if normalized is None:
                normalized = str(room_id)
            if normalized in seen:
                value = f"{normalized}-{room_id}"
                logger.warning(
                    "房间号撞名：id=%s name=%r 与 id=%s 归一化后同名，"
                    "房间号改用 %r（请人工修订为编号格式）",
                    room_id,
                    name,
                    seen[normalized],
                    value,
                )
            else:
                seen[normalized] = room_id
                value = normalized
            updates.append((value, room_id))

        for value, room_id in updates:
            cur.execute(
                f"UPDATE `rooms` SET `{COLUMN_NAME}` = %s WHERE id = %s",
                (value, room_id),
            )
        conn.commit()
        logger.info("已回填 rooms.%s：%s 行", COLUMN_NAME, len(updates))
    finally:
        cur.close()


def _log_blocking_transactions(conn) -> None:
    """加约束失败时打印当前活跃事务（与 0011 同一手法），帮助定位谁占着 MDL。"""
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
            logger.error("加唯一约束失败，但当前没有活跃事务。")
            return
        logger.error("加唯一约束失败，当前活跃事务（越靠前越老）：")
        for row in rows:
            logger.error(
                "  trx_id=%s state=%s 已持续=%ss 线程=%s query=%s",
                row[0],
                row[1],
                row[2],
                row[3],
                (row[4] or "")[:200] or "（空闲事务）",
            )
    except Exception:  # noqa: BLE001 —— 诊断本身绝不能掩盖原始异常
        logger.warning("打印阻塞事务信息失败", exc_info=True)
    finally:
        cur.close()


def apply(conn) -> None:
    """加列 → 回填 → NOT NULL → 组合唯一约束（各步骤独立幂等）"""
    if not _column_exists(conn, "rooms", COLUMN_NAME):
        cur = conn.cursor()
        try:
            cur.execute(
                f"ALTER TABLE `rooms` ADD COLUMN `{COLUMN_NAME}` VARCHAR(50) NULL "
                "COMMENT '房间号(机房名称组内唯一,记录的业务身份)'"
            )
            conn.commit()
            logger.info("已加列 rooms.%s", COLUMN_NAME)
        finally:
            cur.close()
    else:
        logger.info("跳过：rooms.%s 已存在", COLUMN_NAME)

    _backfill(conn)

    if _column_is_nullable(conn, "rooms", COLUMN_NAME):
        cur = conn.cursor()
        try:
            cur.execute(
                f"ALTER TABLE `rooms` MODIFY COLUMN `{COLUMN_NAME}` VARCHAR(50) NOT NULL "
                "COMMENT '房间号(机房名称组内唯一,记录的业务身份)'"
            )
            conn.commit()
            logger.info("已把 rooms.%s 置为 NOT NULL", COLUMN_NAME)
        finally:
            cur.close()
    else:
        logger.info("跳过：rooms.%s 已是 NOT NULL", COLUMN_NAME)

    if _constraint_exists(conn, "rooms", CONSTRAINT_NAME):
        logger.info("跳过：rooms.%s 已存在", CONSTRAINT_NAME)
        return

    conn.commit()
    cur = conn.cursor()
    try:
        cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")
        cur.execute(
            f"ALTER TABLE `rooms` "
            f"ADD UNIQUE KEY `{CONSTRAINT_NAME}` (`name`, `{COLUMN_NAME}`), "
            "ALGORITHM=INPLACE, LOCK=NONE"
        )
        logger.info("已加唯一约束 rooms.%s", CONSTRAINT_NAME)
    except Exception:
        _log_blocking_transactions(conn)
        logger.error(
            "加唯一约束 rooms.%s 失败 —— 本次迁移**未完成**。\n"
            "  · 已成功的部分不会重复执行（幂等），重跑只会重试未完成的部分；\n"
            "  · 若错误是 1205 / 1213：仍有并发事务占着 rooms 的元数据锁，"
            "请暂停应用流量后重跑；\n"
            "  · 确认是否已建成：SHOW INDEX FROM rooms WHERE Key_name = '%s';",
            CONSTRAINT_NAME,
            CONSTRAINT_NAME,
        )
        raise
    finally:
        cur.close()
    conn.commit()
