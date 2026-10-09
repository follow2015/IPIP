# -*- coding: utf-8 -*-
"""`device_config_backups.backup_type` 枚举 3 值 → 4 值（末尾追加 `pre_remedial`）

背景（评审 2026-09-25 · 工单系统代码对齐核查 N-1）
------------------------------------------------
WP-2 修 P0「AI remedial 的变更备份从未真正写入」时，为**零迁移**把写入值从非法值
`pre_remedial` 改成了语义等价的 `pre_change`。副作用是：AI 自动修复与人工变更
在 `backup_type` 这一个维度上**不可区分** —— 审计时无法回答"这份变更前备份是
AI 自动打的还是人打的"，回滚时也无法按来源筛选。

本迁移把当初省掉的那一步补上：枚举扩到 4 值，`pre_remedial` 归 AI 自动修复，
`pre_change` 归还给"人工变更前"（变更审批 / 人工下发的基准备份）。

为什么必须**末尾追加**
----------------------
MySQL 8.0 只有"在合法值列表末尾追加、且不改变枚举存储字节数"才支持 INPLACE；
在中间插入会退化成 COPY + 锁表。本表 `config_content` 是 MEDIUMTEXT，
COPY 要重写整表，代价不可接受 ⇒ 追加位置是硬要求，不是风格问题。

在线 DDL 纪律（与 0011/0016/0017/0018/0019/0020 一致）
-----------------------------------------------------
- 先 `SET SESSION lock_wait_timeout = 300`，避免 MDL 等待雪崩；
- 优先 `ALGORITHM=INPLACE, LOCK=NONE`；
- ⚠️ 例外处理：若目标实例判定无法 INPLACE（低版本 / 分支版本差异），
  MySQL 会直接报 1846 而不是自动降级 —— 此时**不带算法提示重试一次**
  （让优化器自选，最坏是 COPY），并在日志里显式记一条。
  这与"写 ALGORITHM 只为好看"不同：这里真的处理了失败分支。

**幂等**：解析 `information_schema.columns.COLUMN_TYPE`，已含 `pre_remedial` 即跳过。
"""
import logging

logger = logging.getLogger(__name__)

TABLE = "device_config_backups"
COLUMN = "backup_type"
NEW_ENUM = "enum('manual','scheduled','pre_change','pre_remedial')"
_MDL_WAIT_TIMEOUT_SECONDS = 300


def _column_type(conn) -> str:
    """返回列的当前类型串（如 ``enum('manual','scheduled')``），列不存在则返回空串。"""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COLUMN_TYPE FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (TABLE, COLUMN),
        )
        row = cur.fetchone()
        return (row[0] or "") if row else ""
    finally:
        cur.close()


def apply(conn) -> None:
    """把 backup_type 扩到 4 值（幂等）"""
    current = _column_type(conn)
    if not current:
        logger.warning("跳过：表 %s.%s 不存在（未安装基线？）", TABLE, COLUMN)
        return
    if "pre_remedial" in current:
        logger.info("跳过：%s.%s 已含 pre_remedial（当前 %s）", TABLE, COLUMN, current)
        return

    conn.commit()  # 结束此前语句开启的事务，避免 DDL 与活跃事务互拖
    stmt = (
        f"ALTER TABLE `{TABLE}` "
        f"MODIFY COLUMN `{COLUMN}` {NEW_ENUM} "
        f"NOT NULL DEFAULT 'manual' COMMENT '备份类型'"
    )
    cur = conn.cursor()
    try:
        cur.execute(f"SET SESSION lock_wait_timeout = {_MDL_WAIT_TIMEOUT_SECONDS}")
        try:
            cur.execute(f"{stmt}, ALGORITHM=INPLACE, LOCK=NONE")
            logger.info("已扩枚举 %s.%s（INPLACE）：%s", TABLE, COLUMN, NEW_ENUM)
        except Exception as exc:  # noqa: BLE001 —— 1846 等：该实例无法 INPLACE
            logger.warning(
                "%s.%s 无法按 INPLACE 扩枚举（%s），不带算法提示重试（最坏退化为 COPY）",
                TABLE, COLUMN, exc,
            )
            cur.execute(stmt)
            logger.info("已扩枚举 %s.%s（COPY/自选算法）：%s", TABLE, COLUMN, NEW_ENUM)
    finally:
        cur.close()
