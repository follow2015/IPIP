# -*- coding: utf-8 -*-
"""加密 switch_credentials.password 的历史明文（审计 P0#3 配套数据回填）。

背景：`switch_credentials.password` 的列注释自始声明「AES-256-GCM加密后密码」，
但模型层加密 hook（`@validates("password")`，审计 P0#3 才补上）此前不存在 ——
所有历史写入路径（`SwitchCredentials(**data)` / `setattr`）落库的都是**明文**。
本迁移做一次性就地加密（不改 schema，只改数据）。

为什么是迁移而不是一次性运维脚本：`app/services/schema_migration_service.py`
的纪律 ——「数据回填也走迁移链（.py 内批处理）」。只有进迁移链才有
`schema_migrations` 记账（谁跑没跑一目了然）与 `flask db-upgrade` 的升级即执行；
放脚本里靠人记得跑，就是「迁移没执行」的成因。

与 IPMI 凭据同一范式（`app/utils/security/ipmi_validator.py`）：同一密钥
（SWITCH_SECRET_KEY）、同一密文前缀（ENC:AES256GCM:）。

幂等：只处理 `password NOT LIKE 'ENC:AES256GCM:%'`，已加密行天然跳过，可重复执行。
fail-close：SWITCH_SECRET_KEY 缺失/非法时 `encrypt()` 抛 ValueError → 中止迁移，
绝不落明文。
容量防御：密文 = 13 字节前缀 + base64(12 字节 nonce + 明文 + 16 字节 tag)，
明文过长会超出列宽 512；此时明确报错中止，**不做截断**（截断即永久损坏凭据）。

上线动作（先只读预检，再执行）::

    flask db-check              # 确认无模型↔库漂移
    flask db-upgrade --dry-run  # 只读预检：打印将应用的迁移
    flask db-upgrade            # 执行

回滚：纯数据变更，无 DDL；密文不可逆，如需还原请用备份。
"""
import logging

logger = logging.getLogger(__name__)

TABLE = "switch_credentials"
CIPHER_PREFIX = "ENC:AES256GCM:"
COLUMN_MAX_LEN = 512


def apply(conn) -> None:
    """就地加密历史明文凭据（幂等；契约见本模块 docstring 与
    `app/services/schema_migration_service.py`）。

    Args:
        conn: 由 runner 注入的 DBAPI 连接（pymysql，autocommit=False）。
            迁移内自行 `commit()`；异常传播即整体回滚（runner 不提交版本记录）。
    """
    from app.utils.security.encryption import encrypt

    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT id, device_id, password FROM `{TABLE}` "
            "WHERE password IS NOT NULL AND password <> '' "
            f"AND password NOT LIKE '{CIPHER_PREFIX}%'"
        )
        rows = cur.fetchall()
    finally:
        cur.close()

    if not rows:
        logger.info("无明文交换机凭据待迁移（已全部为密文）")
        return

    logger.info("发现 %d 条明文交换机凭据，开始加密", len(rows))

    migrated = 0
    cur = conn.cursor()
    try:
        for row_id, device_id, plaintext in rows:
            cipher = encrypt(plaintext)
            if len(cipher) > COLUMN_MAX_LEN:
                raise RuntimeError(
                    f"{TABLE}.id={row_id}（device_id={device_id}）密文长度 "
                    f"{len(cipher)} 超出列宽 {COLUMN_MAX_LEN}：请先扩列再迁移，"
                    "禁止截断"
                )
            cur.execute(
                f"UPDATE `{TABLE}` SET password = %s WHERE id = %s",
                (cipher, row_id),
            )
            migrated += 1
    finally:
        cur.close()

    conn.commit()
    logger.info("已加密 %d 条明文交换机凭据（重跑将跳过）", migrated)
