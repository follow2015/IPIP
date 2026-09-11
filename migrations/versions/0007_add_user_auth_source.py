# -*- coding: utf-8 -*-
"""users 加外部身份字段（企业身份集成 T3）。

新增两列：
- ``auth_source``：``local``（默认）/ ``ldap``。存量行一律 ``local``，登录行为不变。
- ``external_dn``：外部目录中的唯一标识（AD/LDAP DN），本地账号为 NULL；
  配 ``idx_user_external_dn`` 供登录时按 DN 反查本地账号。

幂等：列 / 索引存在即跳过；可重复执行（DDL 在 MySQL 逐条隐式提交，中断后重跑安全）。

回滚（runner 无 down，需手工执行；顺序与建表相反）::

    ALTER TABLE `users` DROP INDEX `idx_user_external_dn`;
    ALTER TABLE `users` DROP COLUMN `external_dn`;
    ALTER TABLE `users` DROP COLUMN `auth_source`;

注意：回滚会丢弃 LDAP 账号与本地账号的绑定关系，重新开启外部认证后需重新绑定。
"""
import logging

logger = logging.getLogger(__name__)

TABLE = "users"
INDEX = "idx_user_external_dn"


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


def apply(conn) -> None:
    cur = conn.cursor()
    try:
        if not _column_exists(conn, "auth_source"):
            cur.execute(
                f"ALTER TABLE `{TABLE}` ADD COLUMN `auth_source` varchar(16) "
                f"NOT NULL DEFAULT 'local' COMMENT '认证来源：local/ldap' "
                f"AFTER `contact_phone`"
            )
            logger.info("已补列 %s.auth_source", TABLE)
        else:
            logger.info("跳过：%s.auth_source 已存在", TABLE)

        if not _column_exists(conn, "external_dn"):
            cur.execute(
                f"ALTER TABLE `{TABLE}` ADD COLUMN `external_dn` varchar(255) NULL "
                f"COMMENT '外部身份唯一标识（LDAP DN）' AFTER `auth_source`"
            )
            logger.info("已补列 %s.external_dn", TABLE)
        else:
            logger.info("跳过：%s.external_dn 已存在", TABLE)

        if not _index_exists(conn, INDEX):
            cur.execute(f"ALTER TABLE `{TABLE}` ADD INDEX `{INDEX}` (`external_dn`)")
            logger.info("已补索引 %s", INDEX)
        else:
            logger.info("跳过：索引 %s 已存在", INDEX)
    finally:
        cur.close()
    conn.commit()
