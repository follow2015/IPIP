# -*- coding: utf-8 -*-
"""交换机凭据（switch_credentials.password）存量明文迁移。

与 IPMI 凭据迁移同范式（`app/utils/security/ipmi_validator.py`）：
把历史明文密码就地加密为 AES-256-GCM 密文（`ENC:AES256GCM:` 前缀）。

背景（审计 P0#3）：`SwitchCredentials.password` 的列注释声明密文存储，
但模型 `@validates` 加密 hook 是后补的 —— 此前写入的记录是明文，
需要用本模块做一次性迁移。

用法（脚本/CLI，不要在 `@transactional` 事务内调用）：:

    from extensions import db
    from app.utils.security.switch_credential_crypto import (
        migrate_plaintext_switch_passwords,
    )
    migrated, details = migrate_plaintext_switch_passwords(db.session, dry_run=True)
"""
from app.utils.logging import get_logger
from app.utils.security.encryption import encrypt, is_encrypted

logger = get_logger(__name__)


def migrate_plaintext_switch_passwords(session, dry_run: bool = False):
    """把 `switch_credentials` 中的明文密码就地加密。

    幂等：已加密（`is_encrypted`）的记录直接跳过，可重复执行。

    Args:
        session: SQLAlchemy Session
        dry_run: True 时只统计与列出，不写库

    Returns:
        Tuple[int, List[Dict]]: (迁移条数, 逐条详情)

    Note:
        成功时调用 `session.commit()`（与 IPMI 迁移一致）。因此本函数面向
        运维脚本/CLI，**不可**在 `@transactional` 包裹的用例边界内调用
        （真实 commit 会破坏外层事务原子性，`transaction_checkpoint` 亦有同样约束）。
    """
    from app.models.switch_credentials import SwitchCredentials

    migrated = 0
    details = []

    try:
        records = (
            session.query(SwitchCredentials)
            .filter(
                SwitchCredentials.password.isnot(None),
                SwitchCredentials.password != "",
            )
            .all()
        )

        for record in records:
            if is_encrypted(record.password):
                continue

            detail = {"id": record.id, "device_id": record.device_id}
            if dry_run:
                detail["action"] = "would_encrypt"
                migrated += 1
            else:
                try:
                    record.password = encrypt(record.password)
                    migrated += 1
                    detail["action"] = "encrypt"
                except ValueError as e:
                    detail["action"] = "failed"
                    detail["error"] = str(e)
                    logger.error(
                        "加密交换机凭据失败: switch_credentials.id=%s: %s", record.id, e
                    )
            details.append(detail)

        if not dry_run and migrated > 0:
            session.commit()
            logger.info("已加密 %d 条明文交换机凭据", migrated)

    except Exception as e:  # noqa: BLE001 - 脚本顶层：记录并回滚，向上抛出由调用方决定
        logger.error("批量加密交换机凭据失败: %s", e, exc_info=True)
        if not dry_run:
            session.rollback()
        raise

    return migrated, details
