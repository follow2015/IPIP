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
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = get_logger(__name__)

_KEY_LENGTH = 32

_CIPHER_PREFIX = "ENC:AES256GCM:"


def _looks_like_hex(s: str) -> bool:
    """是否是纯 hex 字符集（不校验长度）。

    [WARN] 这个判据替代了原来"``len(s) == 64`` 就当 hex 试"的写法。
    后者的病因：**长度 64 是 hex 的必要不充分条件** —— base64 也能是 64 字符
    （解出 48 字节）。真发生过：64 字符 base64 串落进 ``bytes.fromhex``
    抛错后被静默吞掉，最终报出一句「当前长度: 64」，读起来像"64 明明符合要求"
    ⇒ 把排查方向引向"校验逻辑有 bug"，而真实原因是密钥本身形状不对。
    """
    return bool(re.fullmatch(r"[0-9a-fA-F]+", s))


def _decode_key_b64(key_str: str) -> Optional[bytes]:
    """解码 base64 密钥，**同时容忍标准表与 URL-safe 表**。

    为什么必须两种表都试：``secrets.token_urlsafe()``（本仓安装器历史上生成
    密钥用的就是它，见 ``scripts/installer/act/envfile.py``）产出的是
    **URL-safe** 字母表（含 ``-``/``_``）。只用标准 ``b64decode`` 拿它没办法。

    两个 decoder 的**签名不同**（这里踩过一次，值得记）
    ---------------------------------------------------
    ``urlsafe_b64decode`` **不接受** ``validate`` 关键字 —— 传了直接
    ``TypeError``，而 ``TypeError`` 会被下面的 ``except Exception`` 吞掉，
    表现为"URL-safe 密钥认不出来"，报错却指向"格式无效"。
    故这里用两个形态一致的 lambda 把参数在**构造时**就绑好，
    而不是在循环里给两者传同一份 kwargs。

    ``validate=True`` 的作用（**实测必需，不是洁癖**）
    ------------------------------------------------
    ``b64decode`` 默认非严格：遇到非字母表字符**静默丢弃**再解码。
    于是对含 ``-``/``_`` 的 URL-safe 串，标准表那条**不会抛错**，
    而是"成功"返回一个**字节数偏小**的结果，循环里第一个 decoder 就这么
    抢答成功，**永远走不到 url-safe 分支** ⇒ 表现为"URL-safe 密钥认不出来"。

    实测证据（变异验证）：把 ``validate=True`` 去掉，
    ``test_urlsafe_base64_key_of_right_length_is_accepted`` **立即转红**。
    故它是这条 fallback 逻辑成立的前提，不是可选的严格性偏好。

    标准表优先：44 字符带 ``+``/``/`` 的写法是本仓文档一直宣传的形状。
    """
    padded = key_str + "=" * (-len(key_str) % 4)
    decoders = (
        lambda s: base64.b64decode(s, validate=True),
        lambda s: base64.urlsafe_b64decode(s),
    )
    for decoder in decoders:
        try:
            return decoder(padded)
        except Exception:  # noqa: BLE001, S112 —— 换另一种字母表继续试，非错误路径
            continue
    return None


def _describe_key_shape(key_str: str) -> str:
    """把密钥形状描述成人能立刻定位问题的一句话。

    刻意**同时**给出「字符串长度」与「解码后字节数」：这两者不同量纲，
    混在一起说就是上面那次的误导来源。并显式指出该形态下"应该多长"。
    """
    if _looks_like_hex(key_str):
        return (
            f"需要 32 字节密钥（hex: 64 字符 / base64: 44 字符），"
            f"实际是 {len(key_str)} 个 hex 字符，即 {len(key_str) // 2} 字节。"
            f"生成命令：python -c \"import os;print(os.urandom(32).hex())\""
        )
    decoded = _decode_key_b64(key_str)
    if decoded is not None:
        actual = len(decoded)
        hint = ""
        if actual > _KEY_LENGTH:
            hint = (
                "；若来自安装器自动生成，说明生成侧用了过长的随机串"
                "（token_urlsafe(48) 解出 48 字节）"
            )
        return (
            f"需要 32 字节密钥（hex: 64 字符 / base64: 44 字符），"
            f"实际是 base64 形态的 {len(key_str)} 字符，解码后 {actual} 字节"
            f"{hint}。注意字符串长度不等于字节数："
            f"64 字符的 base64 串解出的是 48 字节，不是 32 字节"
        )
    return (
        f"需要 32 字节密钥（hex: 64 字符 / base64: 44 字符），"
        f"实际是 {len(key_str)} 个字符，既不是纯 hex 也无法 base64 解码"
    )


def _get_encryption_key() -> bytes:
    """获取加密密钥

    从环境变量 SWITCH_SECRET_KEY 读取，支持：
    - **hex**：64 字符 ⇒ 32 字节；
    - **base64**：44 字符 ⇒ 32 字节（**不是** 64 字符）。

    [WARN] 判定一律以**解码后字节数**为准，不以字符串长度为准。长度只能当
    "值不值得试一下"的提示，不能当合法性的证据（见 ``_looks_like_hex``）。

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

    if _looks_like_hex(key_str):
        try:
            key = bytes.fromhex(key_str)
        except ValueError:  # 奇数长度等
            key = b""
        if len(key) == _KEY_LENGTH:
            return key

    key = _decode_key_b64(key_str)
    if key is not None and len(key) == _KEY_LENGTH:
        return key
    if key is None:
        logger.debug("base64解码密钥失败: key_str长度=%d", len(key_str), exc_info=True)

    raise ValueError(
        f"SWITCH_SECRET_KEY 格式无效：{_describe_key_shape(key_str)}"
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
        raise ValueError(f"加密失败: {e}") from e


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
        raise ValueError(f"解密失败: {e}") from e


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
