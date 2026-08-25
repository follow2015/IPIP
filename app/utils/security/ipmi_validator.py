# -*- coding: utf-8 -*-
"""
IPMI 密码安全验证器

提供启动时扫描和运行时校验功能，确保 device_hardware.ipmi_password 字段
始终以 AES-256-GCM 加密格式存储，防止明文写入。
"""
from app.utils.logging import get_logger
from typing import Dict, List, Tuple

from app.utils.security.encryption import encrypt, is_likely_plaintext_password, is_encrypted

logger = get_logger(__name__)


def scan_plaintext_passwords(session) -> Dict[str, List[Dict]]:
    """扫描数据库中所有 IPMI 密码，检测明文存储

    Args:
        session: SQLAlchemy 数据库会话

    Returns:
        Dict: {
            "plaintext": [{"id": int, "device_id": int, "ipmi_address": str}, ...],
            "encrypted": [{"id": int, "device_id": int}, ...],
            "empty": [{"id": int, "device_id": int}, ...],
            "total_scanned": int,
        }
    """
    from app.models.device_hardware import DeviceHardware

    result = {"plaintext": [], "encrypted": [], "empty": [], "total_scanned": 0}

    try:
        records = session.query(DeviceHardware).filter(
            DeviceHardware.ipmi_password.isnot(None),
            DeviceHardware.ipmi_password != "",
        ).all()

        for record in records:
            info = {
                "id": record.id,
                "device_id": record.device_id,
                "ipmi_address": record.ipmi_address,
            }

            if is_likely_plaintext_password(record.ipmi_password):
                result["plaintext"].append(info)
                logger.warning(
                    f"发现明文 IPMI 密码: device_hardware.id={record.id}, "
                    f"device_id={record.device_id}, ipmi_address={record.ipmi_address}"
                )
            elif is_encrypted(record.ipmi_password):
                result["encrypted"].append({"id": record.id, "device_id": record.device_id})
            else:
                result["plaintext"].append(info)

        empty_count = session.query(DeviceHardware).filter(
            (DeviceHardware.ipmi_password.is_(None)) | (DeviceHardware.ipmi_password == "")
        ).count()
        result["empty_count"] = empty_count
        result["total_scanned"] = len(records) + empty_count

    except Exception as e:
        logger.error(f"扫描 IPMI 密码失败: {e}")
        result["error"] = str(e)

    return result


def migrate_plaintext_to_encrypted(session, dry_run: bool = True) -> Tuple[int, List[Dict]]:
    """将明文 IPMI 密码批量加密

    Args:
        session: SQLAlchemy 数据库会话
        dry_run: True 仅检测不修改，False 执行加密

    Returns:
        Tuple[int, List[Dict]]: (迁移数量, 迁移详情列表)
    """
    from app.models.device_hardware import DeviceHardware

    migrated = 0
    details = []

    try:
        records = session.query(DeviceHardware).filter(
            DeviceHardware.ipmi_password.isnot(None),
            DeviceHardware.ipmi_password != "",
        ).all()

        for record in records:
            if is_likely_plaintext_password(record.ipmi_password):
                detail = {
                    "id": record.id,
                    "device_id": record.device_id,
                    "ipmi_address": record.ipmi_address,
                    "action": "encrypt" if not dry_run else "would_encrypt",
                }

                if not dry_run:
                    try:
                        record.ipmi_password = encrypt(record.ipmi_password)
                        migrated += 1
                    except ValueError as e:
                        detail["action"] = "failed"
                        detail["error"] = str(e)
                        logger.error(
                            f"加密 IPMI 密码失败: device_hardware.id={record.id}: {e}"
                        )
                else:
                    migrated += 1

                details.append(detail)

        if not dry_run and migrated > 0:
            session.commit()
            logger.info(f"已加密 {migrated} 条明文 IPMI 密码")

    except Exception as e:
        logger.error(f"批量加密 IPMI 密码失败: {e}")
        if not dry_run:
            session.rollback()

    return migrated, details


def validate_ipmi_password_on_write(password: str) -> str:
    """写入前校验并自动加密 IPMI 密码

    如果传入明文密码，自动加密后返回。
    如果已是加密格式，直接返回。
    如果为空，直接返回。

    Args:
        password: 待写入的密码值

    Returns:
        str: 加密后的密码（或原值如果已加密/为空）

    Raises:
        ValueError: 加密失败
    """
    if not password:
        return password

    if is_encrypted(password):
        return password

    logger.info("检测到明文 IPMI 密码写入，自动加密")
    return encrypt(password)


def run_startup_check(session) -> None:
    """应用启动时执行 IPMI 密码安全检查

    扫描所有 IPMI 密码，如果发现明文则记录 WARNING 日志。
    在生产环境中，建议配合告警系统使用。

    Args:
        session: SQLAlchemy 数据库会话
    """
    logger.info("执行 IPMI 密码安全启动检查...")
    scan_result = scan_plaintext_passwords(session)

    plaintext_count = len(scan_result.get("plaintext", []))
    encrypted_count = len(scan_result.get("encrypted", []))
    total = scan_result.get("total_scanned", 0)

    logger.info(
        f"IPMI 密码扫描结果: 总计 {total} 条, "
        f"已加密 {encrypted_count} 条, "
        f"明文 {plaintext_count} 条"
    )

    if plaintext_count > 0:
        logger.warning(
            f"⚠ 发现 {plaintext_count} 条明文 IPMI 密码！"
            f"请运行 migrate_plaintext_to_encrypted(session, dry_run=False) 进行加密迁移"
        )
