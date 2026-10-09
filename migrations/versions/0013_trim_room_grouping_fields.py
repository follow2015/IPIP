# -*- coding: utf-8 -*-
"""订正 rooms.building / rooms.floor 的首尾空白

背景：这两个字段是跨机房总览的**分组键**，但此前写入路径没有做 trim（本轮已在
`RoomService` 补齐）。存量数据里已出现 `'A '`（尾随空格）。

后果不是"显示难看"那么轻：`GET /rooms/buildings` 的去重是按原始值做的，`'A'` 与
`'A '` 会被当成两个楼栋，于是表单联想里出现两个几乎一样的选项，总览里同一栋楼
裂成两组——正是设计文档 §2.4 担心的"同一栋楼被打成两个分组"，只是成因从"用词
不一致"变成了"手滑空格"。

**为什么用 SQL 的 TRIM 而不是逐行读改写**：逻辑完全可以在库内表达，逐行读改写
需要拉全表进内存再逐条 UPDATE，在机房表上没有必要。且 `UPDATE ... WHERE 值 <> TRIM(值)`
只命中真正需要改的行，正常库上影响面极小。

**幂等**：第二次执行时条件已不匹配任何行，影响 0 行。

**空串归一**：trim 后变成空串的值统一置 NULL——空串与 NULL 在分组时都表示"未填"
（`get_overview` 用 `room.building or ""` 归桶），但空串会让 `isnot(None) AND != ""`
这类既有过滤条件多绕一层，统一为 NULL 更省心。

**⚠️ 可逆性（2026-10-05 评审 X-1）**：本迁移是**数据改写**，且本仓只有 `db-upgrade`
没有 `db-downgrade`（`app/__init__.py`），一旦执行无法用框架回退。补救三道：
1. **备份**：改写前把受影响行的原值写进 `_rooms_trim_backup_0013`（幂等，可重复执行）；
2. **规模预检**：受影响行数超过 :data:`_LARGE_CHANGE_THRESHOLD` 时**拒绝执行**，
   除非显式设置 `IPIP_MIGRATION_FORCE=1` —— "误执行的不可逆迁移"代价远高于"多一次确认"；
3. **回滚路径**：`restore(conn)` 从备份表把原值写回（见其 docstring），
   人工调用即可，不需要框架支持 downgrade。

**`'A '` 与 `'A'` 会被合并**：若尾随空格在业务上是有意区分（当前没有任何地方依赖它），
执行前请先用备份表确认口径。
"""
import logging
import os
from typing import Mapping

logger = logging.getLogger(__name__)

_FIELDS = ("building", "floor")

_BACKUP_TABLE = "_rooms_trim_backup_0013"

_LARGE_CHANGE_THRESHOLD = 1000

_FORCE_ENV = "IPIP_MIGRATION_FORCE"


def _force_confirmed(env: Mapping[str, str] | None = None) -> bool:
    """是否已显式确认大规模改写（纯函数，便于单测）。"""
    source = os.environ if env is None else env
    return str(source.get(_FORCE_ENV, "")).strip().lower() in ("1", "true", "yes")


def _should_abort(total: int, threshold: int,
                  env: Mapping[str, str] | None = None) -> bool:
    """规模预检判据：超过阈值且未显式确认 → 拒绝执行（纯函数，便于单测）。"""
    return total > threshold and not _force_confirmed(env)


def _count_affected(cur, field: str) -> int:
    """统计该字段真正需要改写的行数（只读，先算清楚再动手）。"""
    cur.execute(
        f"SELECT COUNT(*) FROM `rooms` "  # noqa: S608 -- 迁移脚本自身硬编码标识符，无法参数化列名
        f"WHERE `{field}` IS NOT NULL "
        f"AND (`{field}` <> TRIM(`{field}`) OR `{field}` = '')"
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _backup(cur) -> int:
    """把受影响行的原值备份到 ``_BACKUP_TABLE``（幂等）。返回备份总行数。"""
    cur.execute(
        f"CREATE TABLE IF NOT EXISTS `{_BACKUP_TABLE}` ("
        "`id` BIGINT NOT NULL, "
        "`building` VARCHAR(255) NULL, "
        "`floor` VARCHAR(255) NULL, "
        "`backed_up_at` DATETIME NOT NULL, "
        "PRIMARY KEY (`id`)"
        ")"
    )
    cur.execute(
        f"INSERT IGNORE INTO `{_BACKUP_TABLE}` (id, building, floor, backed_up_at) "  # noqa: S608 -- 同上
        "SELECT id, building, floor, NOW() FROM `rooms` WHERE "
        + " OR ".join(
            f"(`{f}` IS NOT NULL AND (`{f}` <> TRIM(`{f}`) OR `{f}` = ''))"
            for f in _FIELDS
        )
    )
    return int(cur.rowcount or 0)


def restore(conn) -> int:
    """回滚：从备份表把 ``building`` / ``floor`` 的原值写回。返回恢复行数。

    用法（手工，本仓无 db-downgrade）::

        python -c "import pymysql, importlib.util as u; ..."   # 或用部署脚本的运维入口

    更直接的方式（DBA 常用）::

        UPDATE rooms r JOIN _rooms_trim_backup_0013 b ON b.id = r.id
           SET r.building = b.building, r.floor = b.floor;

    ⚠️ 只恢复**被本迁移改写过的行**；备份表在迁移中的行数与改写行数一一对应。
    """
    cur = conn.cursor()
    try:
        cur.execute(f"SHOW TABLES LIKE '{_BACKUP_TABLE}'")
        if not cur.fetchone():
            logger.warning("未找到备份表 %s，无法回滚", _BACKUP_TABLE)
            return 0
        cur.execute(
            f"UPDATE `rooms` r JOIN `{_BACKUP_TABLE}` b ON b.id = r.id "  # noqa: S608 -- 同上
            "SET r.building = b.building, r.floor = b.floor"
        )
        restored = int(cur.rowcount or 0)
        logger.info("已从 %s 恢复 %s 行", _BACKUP_TABLE, restored)
    finally:
        cur.close()
    conn.commit()
    return restored


def apply(conn) -> None:
    """去除首尾空白，并把空串归一为 NULL（各自幂等）"""
    cur = conn.cursor()
    try:
        affected = {field: _count_affected(cur, field) for field in _FIELDS}
        total = sum(affected.values())
        logger.info("预检：rooms 待订正 %s（合计 %s 行）", affected, total)
        if _should_abort(total, _LARGE_CHANGE_THRESHOLD):
            raise RuntimeError(
                f"本次迁移将改写 {total} 行（>{_LARGE_CHANGE_THRESHOLD}），已拒绝执行。"
                f"确认口径后设置 {_FORCE_ENV}=1 重跑；原值会先备份到 {_BACKUP_TABLE}。"
            )

        backed = _backup(cur)
        if backed:
            logger.info("已备份 %s 行原值到 %s（回滚用）", backed, _BACKUP_TABLE)

        for field in _FIELDS:
            cur.execute(
                f"UPDATE `rooms` SET `{field}` = TRIM(`{field}`) "  # noqa: S608 -- alembic 迁移的 DDL 无法参数化表/列名，标识符由迁移脚本自身硬编码
                f"WHERE `{field}` IS NOT NULL AND `{field}` <> TRIM(`{field}`)"
            )
            trimmed = cur.rowcount
            if trimmed:
                logger.info("已去除 rooms.%s 的首尾空白：%s 行", field, trimmed)
            else:
                logger.info("跳过：rooms.%s 无需订正", field)

            cur.execute(
                f"UPDATE `rooms` SET `{field}` = NULL "  # noqa: S608 -- alembic 迁移的 DDL 无法参数化表/列名，标识符由迁移脚本自身硬编码
                f"WHERE `{field}` IS NOT NULL AND `{field}` = ''"
            )
            blanked = cur.rowcount
            if blanked:
                logger.info("已把 rooms.%s 的空串归一为 NULL：%s 行", field, blanked)
    finally:
        cur.close()
    conn.commit()
