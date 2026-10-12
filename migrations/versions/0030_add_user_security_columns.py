# -*- coding: utf-8 -*-
"""安全中心一期：users 补密码有效期与账号锁定列

设计依据：`docs/design/2026-10-10-安全中心一期-检测与强制-设计与实施方案.md` §4.2。


NULL 的语义被定义为"策略启用前从未记录过改密时间"。两种回填方案都更差：

1. 回填为**迁移执行时间** ⇒ 替全部历史密码背书为"刚改过"，把真正的过期账号
   洗白（安全项反而看不见了）；
2. 回填为 `users.created_at` ⇒ 用一个与密码无关的时间冒充改密时间，同样是伪造事实。

因此保持 NULL，由检测器产出低危 finding（`user.password_never_changed`，
**不拒绝登录**），管理员收紧策略时再以"策略启用时刻"为基线起算。


`status=1` 是**管理动作**（禁用，不可登录），`locked_at` 非空是**安全处置**
（异地登录等场景下手动锁定，解锁后恢复正常）。两者语义不同、恢复路径不同，
混用会让"解锁"变成"启用账号"。


`locked_at` / `lock_reason` / `locked_by` / `password_changed_at` 只能由安全中心
服务层写：若进入通用用户更新白名单，就能绕过锁定端点的对象级校验（禁自锁、
禁锁死最后一个可用 admin）直接改库。


**纯增量 DDL**（`ADD COLUMN`，幂等：INFORMATION_SCHEMA 预检 + 跳过已存在列），
不读不改任何既有数据，无不可逆风险。


```sql
ALTER TABLE `users`
  DROP COLUMN `password_changed_at`,
  DROP COLUMN `must_change_password`,
  DROP COLUMN `locked_at`,
  DROP COLUMN `lock_reason`,
  DROP COLUMN `locked_by`;
```
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_TABLE = "users"

_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("password_changed_at", "datetime NULL",
     "上次改密时间（NULL=策略启用前从未记录；不回填，见迁移文档）"),
    ("must_change_password", "tinyint NOT NULL DEFAULT 0", "1=下次登录须改密"),
    ("locked_at", "datetime NULL", "锁定时间（非空=锁定态，与 status=1 禁用解耦）"),
    ("lock_reason", "varchar(255) NULL", "锁定原因"),
    ("locked_by", "bigint NULL", "锁定操作人 users.id"),
)


def _column_exists(cur, column: str) -> bool:
    """列是否已存在（INFORMATION_SCHEMA 预检，保证幂等）。"""
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (_TABLE, column),
    )
    row = cur.fetchone()
    return bool(row and row[0])


def apply(conn) -> None:
    """逐列幂等追加（不写任何数据）。"""
    cur = conn.cursor()
    try:
        for column, coltype, comment in _COLUMNS:
            if _column_exists(cur, column):
                logger.info("跳过：%s.%s 已存在", _TABLE, column)
                continue
            cur.execute(
                f"ALTER TABLE `{_TABLE}` ADD COLUMN `{column}` {coltype} COMMENT %s",
                (comment,),
            )
            logger.info("已新增 %s.%s（%s，纯增量）", _TABLE, column, coltype)
    finally:
        cur.close()
    conn.commit()


def rollback(conn) -> None:
    """删列（仅用于开发/回滚演练；会丢掉锁定态与改密时间戳）。"""
    cur = conn.cursor()
    try:
        for column, _coltype, _comment in _COLUMNS:
            if not _column_exists(cur, column):
                continue
            cur.execute(f"ALTER TABLE `{_TABLE}` DROP COLUMN `{column}`")
            logger.info("已删除 %s.%s", _TABLE, column)
    finally:
        cur.close()
    conn.commit()
