# -*- coding: utf-8 -*-
"""
AES-256-GCM 加密工具

提供对称加密/解密功能，用于 IPMI 密码、交换机凭据等敏感字段的加密存储。
密钥从环境变量 SWITCH_SECRET_KEY 获取（与交换机凭据加密共用同一密钥）。
"""
import base64
from app.utils.logging import get_logger
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = get_logger(__name__)

_KEY_LENGTH = 32

_CIPHER_PREFIX = "ENC:AES256GCM:"


def _get_encryption_key() -> bytes:
    key_str = os.environ.get("SWITCH_SECRET_KEY", "")
    if not key_str:
        raise ValueError(
            "SWITCH_SECRET_KEY 环境变量未设置，无法执行加密操作。"
            "请设置 32 字节密钥（hex 编码 64 字符或 base64 编码 44 字符）"
        )

    if len(key_str) == 64:
        try:
            key = bytes.fromhex(key_str)
            if len(key) == _KEY_LENGTH:
                return key
        except ValueError:
            pass

    try:
        key = base64.b64decode(key_str)
        if len(key) == _KEY_LENGTH:
            return key
    except Exception:
        logger.debug("base64解码密钥失败: key_str长度=%d", len(key_str), exc_info=True)

    raise ValueError(
        f"SWITCH_SECRET_KEY 格式无效：需要 32 字节密钥"
        f"（hex: 64字符, base64: 44字符），当前长度: {len(key_str)}"
    )


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""

    try:
        key = _get_encryption_key()
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        encrypted = base64.b64encode(nonce + ciphertext).decode("ascii")
        return f"{_CIPHER_PREFIX}{encrypted}"
    except Exception as e:
        logger.error(f"加密失败: {e}")
        raise ValueError(f"加密失败: {e}")


def decrypt(encrypted_str: str) -> str:
    if not encrypted_str:
        return ""

    if not encrypted_str.startswith(_CIPHER_PREFIX):
        raise ValueError("数据不是 AES-256-GCM 加密格式")

    try:
        key = _get_encryption_key()
        encrypted = base64.b64decode(encrypted_str[len(_CIPHER_PREFIX):])
        nonce = encrypted[:12]
        ciphertext = encrypted[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception as e:
        logger.error(f"解密失败: {e}")
        raise ValueError(f"解密失败: {e}")


def is_encrypted(value: str) -> bool:
    if not value:
        return False
    return value.startswith(_CIPHER_PREFIX)


def is_likely_plaintext_password(value: str) -> bool:
    if not value:
        return False

    if is_encrypted(value):
        return False

    if len(value) < 20:
        return True

    weak_patterns = re.compile(
        r'^(admin|root|password|123456|changeme|default)',
        re.IGNORECASE
    )
    if weak_patterns.match(value):
        return True

    printable_count = sum(1 for c in value if c.isascii() and (c.isalnum() or c in '!@#$%^&*'))
    if len(value) > 0 and printable_count / len(value) > 0.8:
        return True

    return False
