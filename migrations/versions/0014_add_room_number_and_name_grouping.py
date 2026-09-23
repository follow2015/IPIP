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

**防撞判据必须用"唯一键的口径"，而不是"存储的口径"（v4 复核，2026-09-22）**：
`uk_room_name_number(name, room_number)` 建在 `utf8mb4_0900_ai_ci` 列上 ⇒ 比较时
**大小写与重音都不敏感**（`'A栋'` ≡ `'a栋'`、`'cafe'` ≡ `'café'`）。`_normalize_grouping_value`
只做 NFKC/Cf/strip（存储口径，**写出值不得被折叠污染**），拿它当判撞键会漏判这两类：
两行各自拿到"看起来不重复"的房间号，`ADD UNIQUE KEY` 随即 1062 —— 而此时列已加、值已写，
迁移**在半途中断**。故判据分两层：
  ① `_collation_key()`：在存储口径上再加 casefold + 去组合符，作为 Python 侧判撞键；
  ② `_assert_no_collation_conflicts()`：加约束前**问一次库自己**（`GROUP BY name, room_number
     HAVING COUNT(*) > 1`，与 ALTER 同一套比较规则），修完再验，验不过带真因抛错。
②不可省：①只是 UCA 的近似 —— `'ø'`/`'o'`、`'ł'`/`'l'` 这类字符 NFKD **不分解**却同主权重，
折不出来；且库的排序规则本身可能被环境改过。

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

_CONFLICT_QUERY_TEMPLATE = (
    "SELECT name, `{column}`, COUNT(*) AS cnt, MIN(id) AS keep_id FROM `rooms` "
    "GROUP BY name, `{column}` HAVING COUNT(*) > 1 ORDER BY keep_id"
)

_CONFLICT_MAX_ROUNDS = 3


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


def _collation_key(value: str) -> str:
    """判撞键：与最终唯一键的比较口径（`utf8mb4_0900_ai_ci`）对齐。

    ⚠️ **只用于判撞，绝不用于写出值** —— 写出值走 `_normalize_grouping_value`
    （小写化/去重音会破坏"房间号 = 原来的机房名"这一语义）。

    折叠顺序：NFKD 分解 → `casefold`（含 ß→ss、大小写）→ 丢空白/组合符/格式字符
    ⇒ 大小写、重音、全半角、零宽差异都收敛到同一个键。

    ⚠️ 两条实测踩过的顺序/覆盖要求（都由 `test_collation_key_is_at_least_as_wide_as_
    the_storage_normalizer` 钉住）：
      · **分解必须在 casefold 之前**：`'𝔸'`（U+1D538）casefold 不动它，NFKD 才折成
        `'A'`，若先 casefold 就会得到 `'A'` 与 `'a'` 两个键；
      · **Cf/空白也要丢**：否则对"原始输入"用时判据比存储口径**更窄**
        （`'A栋'` 与 `'A\\u200b栋'` 存储判等、判据判不等）。

    仍是 UCA 的**近似**：`'ø'`/`'o'`、`'ł'`/`'l'`、`'đ'`/`'d'` 这类字符 NFKD 不分解，
    折不出来（而库视为同主权重）。兜底见 `_assert_no_collation_conflicts()`。
    """
    folded = unicodedata.normalize("NFKD", value).casefold()
    stripped = "".join(
        ch for ch in folded
        if unicodedata.category(ch) not in ("Mn", "Mc", "Me", "Cf")
    )
    return stripped.strip()


def _backfill(conn) -> None:
    """为存量行回填 room_number = 归一化(name)，组内撞名时追加 -{id} 后缀。

    rooms 表为十级量级，逐行 UPDATE 可接受；撞名清单打 WARNING 供人工核对。
    判撞用 `_collation_key`（唯一键口径，大小写/重音不敏感），写出仍用存储口径。
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
            value = normalized
            key = _collation_key(value)
            if key in seen:
                first_id = seen[key]
                value = f"{normalized}-{room_id}"
                key = _collation_key(value)
                logger.warning(
                    "房间号撞名：id=%s name=%r 与 id=%s 在唯一键口径（大小写/重音不敏感）"
                    "下同名，房间号改用 %r（请人工修订为编号格式）",
                    room_id,
                    name,
                    first_id,
                    value,
                )
            seen[key] = room_id
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


def _find_collation_conflicts(conn) -> list:
    """库侧判撞：返回 `[(name, room_number, 行数, 保留的 id), ...]`，空 = 可安全加唯一键。"""
    cur = conn.cursor()
    try:
        cur.execute(_CONFLICT_QUERY_TEMPLATE.format(column=COLUMN_NAME))
        return [tuple(row) for row in (cur.fetchall() or [])]
    finally:
        cur.close()


def _repair_collation_conflicts(conn, conflicts: list) -> int:
    """把冲突组里**非最小 id** 的行追加 `-{id}` 后缀（与 Python 侧同一规则），返回改写行数。"""
    cur = conn.cursor()
    repaired = 0
    try:
        for name, room_number, _cnt, keep_id in conflicts:
            cur.execute(
                f"UPDATE `rooms` SET `{COLUMN_NAME}` = CONCAT(`{COLUMN_NAME}`, '-', id) "
                f"WHERE name = %s AND `{COLUMN_NAME}` = %s AND id <> %s",
                (name, room_number, keep_id),
            )
            repaired += cur.rowcount or 0
        conn.commit()
        return repaired
    finally:
        cur.close()


def _assert_no_collation_conflicts(conn, max_rounds: int = _CONFLICT_MAX_ROUNDS) -> int:
    """加唯一键**之前**的库侧闸门：冲突必须清零，否则带真因抛错。

    为什么不能只靠 Python 侧 `_collation_key`：
      · 它是 UCA(_0900_ai_ci) 的近似（'ø'/'o' 等 NFKD 不分解却同主权重，折不出来）；
      · 库的排序规则可能被环境改过（迁库/改 collation/换 MariaDB）；
      · 而 `ADD UNIQUE KEY` 用的是**库自己的**比较规则。
    ⇒ 只有"用同一套规则再问一次库"，才能保证 ALTER 不 1062。修满 max_rounds 轮仍不干净
    就抛 RuntimeError（附冲突组清单）：比让 ALTER 报一个查不到出处的 1062 好定位。

    Returns:
        实际执行的修复轮数（0 = 一次就干净，无需改写）。
    """
    for round_no in range(1, max_rounds + 1):
        conflicts = _find_collation_conflicts(conn)
        if not conflicts:
            if round_no > 1:
                logger.info("库侧判撞复核通过（第 %s 轮）：冲突已清零", round_no)
            return round_no - 1
        repaired = _repair_collation_conflicts(conn, conflicts)
        logger.warning(
            "库侧判撞：发现 %s 组 (name, room_number) 在库比较口径下重复"
            "（Python 侧折叠不出的形态），已改写 %s 行，准备复核（第 %s/%s 轮）",
            len(conflicts),
            repaired,
            round_no,
            max_rounds,
        )

    stuck = _find_collation_conflicts(conn)
    details = "\n".join(
        f"  · name={name!r} room_number={room_number!r} 行数={cnt} 保留 id={keep_id}"
        for name, room_number, cnt, keep_id in stuck
    )
    logger.error(
        "库侧判撞修复 %s 轮后仍有 %s 组重复 —— 本次迁移**未完成**，且**未尝试加唯一键**"
        "（避免 1062 中断在半途）。\n%s",
        max_rounds,
        len(stuck),
        details,
    )
    raise RuntimeError(
        f"回填后仍存在 {len(stuck)} 组 (name, room_number) 在库比较口径下重复"
        f"（uk 用的是 *_ai_ci：大小写与重音均不敏感）⇒ 若继续执行，"
        f"ADD UNIQUE KEY `{CONSTRAINT_NAME}` 会以 1062 中断：\n{details}\n"
        f"请按上面的清单把重复行改成编号格式后再重跑（迁移幂等）。"
    )


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

    _assert_no_collation_conflicts(conn)

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
