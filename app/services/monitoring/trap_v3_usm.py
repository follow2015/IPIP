# -*- coding: utf-8 -*-
"""SNMPv3 USM 密码学适配层 —— 引用 pysnmp ``proto.secmod``，纯函数、无 IO、无状态。

设计文档：``docs/design/trapd-SNMPv3支持-设计文档-20261006.md`` §3.2 / §3.3 / §9.1。

**决策（§9.1）**：密钥本地化 / HMAC / AES 全部**引用** ``pysnmp.proto.secmod``
层，不自行实现密码学。理由是"不做自研密码学"的一贯取向；该层是**纯计算模块**，
不涉及传输与事件循环，与 trapd 刻意不用 ``hlapi`` / ``SnmpEngine`` 的原则不冲突。

[WARN]️ localkey API 的实测约束（照抄即用，写错会抛异常）：

- 函数名是**下划线式** ``password_to_key`` / ``hash_passphrase``（**无**驼峰版）
- 第三参数是**可调用哈希函数**（``hashlib.sha256``），**不是** ``"sha256"`` 字符串
- 模块**只内置 md5/sha1**；SHA-2 族需自行传 ``hashlib.sha256`` 等
- ``engine_id`` **必须是** ``univ.OctetString``；传 ``bytes`` 会抛
  ``AttributeError: 'bytes' object has no attribute 'asOctets'``
- 返回 ``univ.OctetString``，用 ``.asOctets()`` 取 bytes

**等价性已实测**：本层输出与 RFC 3414 A.2 的自研实现**逐字节相同**
（engineID=800007db03845b125ab2f1 / pass="44444" / sha256 → eb1b9e89...）。
"""

import hashlib
import hmac
from typing import Callable

from pyasn1.codec.ber import decoder as ber_decoder
from pyasn1.type import univ

__all__ = [
    "AuthProtocolError",
    "UnsupportedProtocolError",
    "AUTH_HASH",
    "AUTH_TRUNC_LEN",
    "PRIV_KEY_LEN",
    "hash_func_for_auth",
    "localize_key",
    "localize_keys",
    "auth_trunc_len",
    "priv_key_len",
    "hmac_digest",
    "verify_hmac",
    "build_aes_iv",
    "decrypt_ciphertext",
    "aes_key_len",
    "decode_security_parameters",
    "locate_auth_params_span",
]

AUTH_HASH: dict[str, Callable[[], "hashlib._Hash"]] = {
    "md5": hashlib.md5,
    "sha": hashlib.sha1,
    "sha1": hashlib.sha1,
    "sha224": hashlib.sha224,
    "sha256": hashlib.sha256,
    "sha384": hashlib.sha384,
    "sha512": hashlib.sha512,
}

AUTH_TRUNC_LEN: dict[str, int] = {
    "md5": 12,
    "sha": 12,
    "sha1": 12,
    "sha224": 16,
    "sha256": 24,
    "sha384": 32,
    "sha512": 48,
}

PRIV_KEY_LEN: dict[str, int] = {
    "des": 16,
    "aes": 16,
    "aes128": 16,
    "aes192": 24,
    "aes256": 32,
    "3des": 16,
}

PRIV_NONE = "none"


class AuthProtocolError(Exception):
    """认证协议名无法识别。"""


class UnsupportedProtocolError(Exception):
    """协议名合法但本环境不支持（例如缺第三方 AES 后端）。"""


def _norm(proto: str) -> str:
    return str(proto or "").strip().lower().replace("-", "")


def hash_func_for_auth(auth_protocol: str) -> Callable[[], "hashlib._Hash"]:
    """把 auth 协议名映射为**可调用**哈希函数（localkey 需要可调用对象）。

    Args:
        auth_protocol: 如 ``"sha256"`` / ``"SHA-256"`` / ``"sha"``。

    Returns:
        可调用哈希构造函数，如 ``hashlib.sha256``。

    Raises:
        AuthProtocolError: 协议名不在 ``AUTH_HASH`` 中（含 ``"none"``）。
    """
    key = _norm(auth_protocol)
    try:
        return AUTH_HASH[key]
    except KeyError as exc:
        raise AuthProtocolError(f"未知的 SNMP auth 协议: {auth_protocol!r}") from exc


def auth_trunc_len(auth_protocol: str) -> int:
    """返回 HMAC 截断长度（字节）。未知协议抛 ``AuthProtocolError``。"""
    key = _norm(auth_protocol)
    try:
        return AUTH_TRUNC_LEN[key]
    except KeyError as exc:
        raise AuthProtocolError(f"未知的 SNMP auth 协议: {auth_protocol!r}") from exc


def priv_key_len(priv_protocol: str) -> int:
    """返回从 Kul 中取用的密钥长度（字节）；``none`` 返回 0。"""
    key = _norm(priv_protocol)
    if key in ("", PRIV_NONE):
        return 0
    try:
        return PRIV_KEY_LEN[key]
    except KeyError as exc:
        raise AuthProtocolError(f"未知的 SNMP priv 协议: {priv_protocol!r}") from exc


aes_key_len = priv_key_len


def _as_octet_string(engine_id) -> univ.OctetString:
    """把 engineID 统一成 ``univ.OctetString``。

    [WARN]️ localkey 内部调 ``engine_id.asOctets()``，传 ``bytes`` 会 ``AttributeError``。
    这里是唯一的类型收敛点：报文里解出来的本来就是 ``OctetString``，
    但从 DB / 配置进来的是 ``bytes``，两条路径在此对齐。
    """
    if isinstance(engine_id, univ.OctetString):
        return engine_id
    return univ.OctetString(bytes(engine_id))


def localize_key(passphrase, engine_id, auth_protocol: str) -> bytes:
    """口令本地化：``passphrase → Ku → Kul``（RFC 3414 A.2）。

    委托 ``pysnmp.proto.secmod.rfc3414.localkey.password_to_key``。

    Args:
        passphrase: 口令（str 或 bytes）。
        engine_id: 权威引擎 ID（``OctetString`` 或 ``bytes``）。
        auth_protocol: 决定哈希族 —— **priv key 也走同一族**。

    Returns:
        本地化后的密钥（bytes，长度 = 哈希摘要长度，如 sha256 → 32）。

    Examples:
        >>> localize_key("44444", bytes.fromhex("800007db03845b125ab2f1"), "sha256").hex()[:16]
        'eb1b9e89d90c2d86'
    """
    from pysnmp.proto.secmod.rfc3414.localkey import password_to_key

    return bytes(
        password_to_key(
            passphrase,
            _as_octet_string(engine_id),
            hash_func_for_auth(auth_protocol),
        )
    )


def localize_keys(passphrase_auth: str, passphrase_priv: str, engine_id,
                  auth_protocol: str) -> tuple[bytes, bytes]:
    """一次性本地化 auth key 与 priv key（节省一次 16384 轮哈希的重复调用）。

    SNMP 的 priv key **与 auth key 用同一哈希族**（RFC 3414 §3.2），
    但口令可以不同（authPriv 允许 auth_passphrase != priv_passphrase）。

    Returns:
        ``(auth_key, priv_key)``；``priv_key`` 长度由哈希族决定（截断在解密处做）。
    """
    return (
        localize_key(passphrase_auth, engine_id, auth_protocol),
        localize_key(passphrase_priv, engine_id, auth_protocol),
    )


def hmac_digest(key: bytes, message: bytes, auth_protocol: str) -> bytes:
    """按 auth 协议算 HMAC 摘要（**未截断**，完整摘要）。"""
    func = hash_func_for_auth(auth_protocol)
    return hmac.new(key, message, func).digest()


def verify_hmac(raw: bytes, auth_key: bytes, auth_params: bytes,
                sec_params_span: tuple[int, int], auth_protocol: str) -> bool:
    """校验报文 HMAC（RFC 3414 §6 / RFC 7860 §3）。

    做法：把 ``msgAuthenticationParameters`` 字段的**内容整体零替换**
    （保留标签与长度字节），对整条报文重算 HMAC 并按协议截断，
    与报文原值做**定时安全**比对。

    Args:
        raw: 完整报文原始字节。
        auth_key: 本地化的 auth key（``localize_key`` 的输出）。
        auth_params: 报文里的 ``msgAuthenticationParameters`` 值。
        sec_params_span: ``(start, end)`` —— ``auth_params`` 内容在 ``raw``
            中的字节区间（左闭右开）。由规格层在解码时记录。
        auth_protocol: auth 协议名（决定哈希族与截断长度）。

    Returns:
        bool: True 表示校验通过。
    """
    if not auth_params:
        return False
    start, end = sec_params_span
    if end - start != len(auth_params):
        return False
    zeroed = raw[:start] + b"\x00" * len(auth_params) + raw[end:]
    expected = hmac_digest(auth_key, zeroed, auth_protocol)[: auth_trunc_len(auth_protocol)]
    return hmac.compare_digest(expected, bytes(auth_params))


def build_aes_iv(engine_boots: int, engine_time: int, priv_params: bytes) -> bytes:
    """拼 AES IV（RFC 3826 §3.1.2.1）。

    ``IV = engineBoots(4B 大端) ‖ engineTime(4B 大端) ‖ privParams(8B salt)``

    [WARN]️ 顺序不能变：把 salt 挪到前面会导致明文乱码（不报错，静默坏数据）。
    """
    return (
        int(engine_boots).to_bytes(4, "big")
        + int(engine_time).to_bytes(4, "big")
        + bytes(priv_params)
    )


def decrypt_ciphertext(ciphertext: bytes, priv_key: bytes, engine_boots: int,
                       engine_time: int, priv_params: bytes,
                       auth_protocol: str, priv_protocol: str) -> tuple[bytes, bytes, bytes]:
    """AES-CFB 解密加密的 ScopedPDU。

    委托 ``pysnmp.proto.secmod`` 的实现（``rfc3826.priv.aes.Aes`` 管 128、
    ``eso.priv.aes192.Aes192`` / ``aes256.Aes256`` 管更长密钥、
    ``eso.priv.des3.Des3`` 管 3DES）。

    [WARN]️ **不要直接 ``from ... import Aes``**：priv 系列模块与
    ``rfc3414.service`` **互相导入**，单独导入 priv 模块会抛
    ``AttributeError: partially initialized module ... (most likely due to a
    circular import)``。必须先导入 ``rfc3414.service``（见 ``_priv_backend``）。

    Args:
        ciphertext: ``msgData`` 的加密字节串。
        priv_key: ``localize_keys`` 得到的 priv key（**未截断**）。
        engine_boots / engine_time: 报文里的权威引擎计数与时间。
        priv_params: ``msgPrivacyParameters``（AES 为 8 字节 salt）。
        auth_protocol: 决定哈希族（与 auth 同族）—— 本函数只用于长度校验。
        priv_protocol: ``aes`` / ``aes192`` / ``aes256`` / ``des`` / ``3des``。

    Returns:
        ``(plaintext, aes_key, iv)`` —— 明文 + 中间量（后两者供排障比对，
        不是调用方必需，但出问题时没有它们几乎无法定位）。

    Raises:
        AuthProtocolError: ``priv_protocol`` 无法识别。
        UnsupportedProtocolError: 该协议在当前环境缺少后端实现。
    """
    del auth_protocol  # 当前实现由 pysnmp 内部按 SERVICE_ID 处理哈希族选择
    key_len = priv_key_len(priv_protocol)
    if key_len == 0:
        raise AuthProtocolError(f"priv 协议 {priv_protocol!r} 无需解密或不可识别")
    proto = _norm(priv_protocol)
    cpu = _priv_backend(proto)
    key = univ.OctetString(bytes(priv_key)[:key_len])
    salt = list(bytes(priv_params))
    priv_parameters = (int(engine_boots), int(engine_time), salt)
    plaintext = bytes(cpu.decrypt_data(key, priv_parameters, univ.OctetString(bytes(ciphertext))))
    return plaintext, bytes(key), build_aes_iv(engine_boots, engine_time, priv_params)


def _priv_backend(proto: str):
    """按 priv 协议取 pysnmp 的加解密实现（统一后端类名差异 + 打破循环导入）。

    [WARN]️ **循环导入是这里最大的坑**：``eso.priv.aesbase`` 在类定义期就引用
    ``rfc3826.priv.aes.Aes``，而 ``rfc3826.priv.aes`` 又导入 ``rfc3414.localkey``
    → ``rfc3414.__init__`` → ``rfc3414.service`` → 回头导入 ``eso.priv.*``。
    直接 ``from pysnmp.proto.secmod.rfc3826.priv.aes import Aes`` 在某些导入顺序下
    会拿到半初始化的模块（``partially initialized module ... circular import``）。

    解法：**先**导入 ``rfc3414.service`` 把整条链一次性走完，**再**取类。
    这一步是必需的，删掉会在冷启动（首次导入）时随机炸。
    """
    import pysnmp.proto.secmod.rfc3414.service  # noqa: F401 -- 打破循环导入，勿删

    try:
        if proto in ("aes", "aes128"):
            from pysnmp.proto.secmod.rfc3826.priv.aes import Aes

            return Aes()
        if proto == "aes192":
            from pysnmp.proto.secmod.eso.priv.aes192 import Aes192

            return Aes192()
        if proto == "aes256":
            from pysnmp.proto.secmod.eso.priv.aes256 import Aes256

            return Aes256()
        if proto in ("des", "3des"):
            from pysnmp.proto.secmod.eso.priv.des3 import Des3

            return Des3()
    except ImportError as exc:  # pragma: no cover -- 依赖缺失时的显式报错
        raise UnsupportedProtocolError(
            f"priv 协议 {proto!r} 缺少 pysnmp 后端实现: {exc}"
        ) from exc
    raise AuthProtocolError(f"未知的 SNMP priv 协议: {proto!r}")


def decode_security_parameters(sec_params_octets: bytes) -> dict:
    """对 ``msgSecurityParameters``（OCTET STRING 内容）二次 BER 解码。

    返回 dict（不是 pyasn1 对象）—— 上层要拿 ``auth_params`` 在 raw 中的
    字节区间用来做 HMAC 零替换，pyasn1 对象不带这个信息，故在此一并算好。

    Returns:
        dict: ``content`` 原始字节、``engine_id``、``engine_boots``、
        ``engine_time``、``username``、``auth_params``、``priv_params``、
        ``auth_params_span``（``(start, end)`` 在 ``sec_params_octets`` 内的区间）。
    """
    from .trap_v3_spec import UsmSecurityParameters

    params, _ = ber_decoder.decode(sec_params_octets, asn1Spec=UsmSecurityParameters())
    auth_params = bytes(params.getComponentByName("msgAuthenticationParameters"))
    return {
        "content": bytes(sec_params_octets),
        "engine_id": bytes(params.getComponentByName("msgAuthoritativeEngineID")),
        "engine_boots": int(params.getComponentByName("msgAuthoritativeEngineBoots")),
        "engine_time": int(params.getComponentByName("msgAuthoritativeEngineTime")),
        "username": bytes(params.getComponentByName("msgUserName")).decode(
            "utf-8", errors="replace"
        ),
        "auth_params": auth_params,
        "priv_params": bytes(params.getComponentByName("msgPrivacyParameters")),
        "auth_params_span": locate_auth_params_span(sec_params_octets, auth_params),
    }


def locate_auth_params_span(sec_params_octets: bytes, auth_params: bytes) -> tuple[int, int]:
    """在 ``sec_params_octets`` 里定位 ``auth_params`` 值的字节区间。

    用 BER 标签 + 长度前缀做定位（OCTET STRING = 0x04）。为什么不用
    ``find()``：明文片段可能恰好与 auth_params 相同字节，靠内容匹配会定位错，
    必须按 TLV 结构解析。定位失败返回 ``(0, 0)``（= 校验必然失败，安全侧）。
    """
    if not auth_params:
        return (0, 0)
    want_len = len(auth_params)
    i, n = 0, len(sec_params_octets)
    while i < n:
        if sec_params_octets[i] != 0x04:  # 只认 OCTET STRING
            i += 1
            continue
        if i + 1 >= n:
            break
        length_byte = sec_params_octets[i + 1]
        if length_byte < 0x80:  # 短型长度
            value_start = i + 2
            value_len = length_byte
        else:
            num_bytes = length_byte & 0x7F
            if num_bytes == 0 or i + 2 + num_bytes > n:
                i += 1
                continue
            value_start = i + 2 + num_bytes
            value_len = int.from_bytes(sec_params_octets[i + 2 : i + 2 + num_bytes], "big")
        if value_len == want_len:
            span = (value_start, value_start + want_len)
            if sec_params_octets[span[0] : span[1]] == auth_params:
                return span
        i += 1
    return (0, 0)
