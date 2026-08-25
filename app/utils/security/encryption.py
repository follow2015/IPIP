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
    """获取加密密钥

    从环境变量 SWITCH_SECRET_KEY 读取，支持 hex 编码（64字符）或 base64 编码。

    Returns:
        bytes: 32 字节 AES-256 密钥

    Raises:
        ValueError: 密钥未配置或格式无效
    """
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
    """使用 AES-256-GCM 加密字符串

    Args:
        plaintext: 明文字符串

    Returns:
        str: 格式为 "ENC:AES256GCM:<base64(nonce+ciphertext+tag)>"

    Raises:
        ValueError: 加密失败
    """
    if not plaintext:
        return ""

    try:
        key = _get_encryption_key()
        nonce = os.urandom(12)  # GCM 推荐 12 字节 nonce
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        encrypted = base64.b64encode(nonce + ciphertext).decode("ascii")
        return f"{_CIPHER_PREFIX}{encrypted}"
    except Exception as e:
        logger.error(f"加密失败: {e}")
        raise ValueError(f"加密失败: {e}")


def decrypt(encrypted_str: str) -> str:
    """使用 AES-256-GCM 解密字符串

    Args:
        encrypted_str: encrypt() 返回的加密字符串

    Returns:
        str: 解密后的明文

    Raises:
        ValueError: 解密失败或数据格式无效
    """
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
    """判断字符串是否为加密格式

    Args:
        value: 待判断的字符串

    Returns:
        bool: 是加密格式返回 True
    """
    if not value:
        return False
    return value.startswith(_CIPHER_PREFIX)


def is_likely_plaintext_password(value: str) -> bool:
    """启发式判断密码值是否为明文

    检测规则：
    1. 已加密格式 → False
    2. 长度 < 20 且不含 base64 字符 → 可能是明文
    3. 包含常见密码模式（纯数字、admin/root 等）→ 可能是明文
    4. 可读 ASCII 字符占比 > 80% → 可能是明文

    Args:
        value: 待判断的密码值

    Returns:
        bool: 可能是明文返回 True
    """
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
