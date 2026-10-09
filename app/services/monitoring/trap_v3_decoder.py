# -*- coding: utf-8 -*-
"""SNMPv3 trap 报文解码主流程（设计文档 §4.1 的 ``_decode_v3``）。

纯函数为主（``decode_v3_trap`` 无 IO），凭据查询由调用方以 dict 注入 ——
这样 CI 可以**不打库**跑完整解码链路（§6.3 落点表的诉求）。

统一出口契约见设计文档 §4.1：新增 ``snmp_version`` 作为 ``version`` 的别名，
``community`` 置空（v3 无此概念）。

拒绝语义（**一律返回 None，不抛异常**）：
- 不是 v3 报文（``msgVersion != 3``）
- 安全模型不是 USM（非 3）
- 未知 username / username 不在用户表
- secLevel 与凭据档位不匹配
- HMAC 校验失败
- 解密或 ScopedPDU 解析失败

返回 None 而非抛异常的原因：``_recv_loop`` 依赖「解码失败即丢该条」的纪律
（``run_trapd_service.py:515`` 虽兜了異常，但正常失败路径应走 None），
任何单条失败都不得终止收包循环。
"""

import logging
from functools import lru_cache
from typing import Any, Callable

from pyasn1.codec.ber import decoder as ber_decoder
from pyasn1.error import PyAsn1Error

from . import trap_v3_usm as usm
from .trap_v3_spec import (
    SNMP_SEC_MODEL_USM,
    SNMP_V3_VERSION,
    ScopedPDU,
    V3Message,
    UsmSecurityParameters,
    parse_msg_flags,
)

logger = logging.getLogger(__name__)

__all__ = ["decode_v3_trap", "V3RejectReason"]

@lru_cache(maxsize=1)
def _trap_oid_keys() -> frozenset[str]:
    """``snmpTrapOID.0`` 的取值集合 —— **取自 pysnmp，不许手写**。

    [WARN] 与 ``run_trapd_service._snmp_trap_oid`` 是同一道题的两个答案：
    那边曾经把 OID 手抄成 ``1.3.6.1.6.3.1.1.6.1``（正确是 ``...1.1.4.1.0``），
    结果是**所有标准设备的 trap 都被丢弃**（见设计文档 §9.4 缺陷 1）。

    本模块初版为了"不与存量行为对立"同时认了两者 —— 那是笔误已被证实、
    且没人也不会有设备发那个错値之后的**多余设计**：留着它等于把一个笔误
    固化成 feature，还会让后来人不明白"为什么要兼容一个错 OID"。
    现已随 trapd 一并收口到**只认标准值**，两个模块口径一致。

    **惰性取值**：``pysnmp.proto.api.v2c`` 在本包由 ``trap_v3_usm`` 延迟导入
    （§9.1 的循环导入坑），顶层直接 import 会把 pysnmp 拉进所有 importing
    路径。``lru_cache`` 让后续调用退化为字典查找。
    """
    from pysnmp.proto.api import v2c as pysnmp_v2c

    return frozenset({".".join(str(x) for x in pysnmp_v2c.apiTrapPDU.snmpTrapOID)})


class V3RejectReason:
    """拒收原因常量（供日志与计数器使用，便于排障时区分是哪一道门拦下的）。

    ``NOT_V3`` 刻意**不做 reject 调用**：版本不是 3 意味着"这不是 v3 的活"，
    应当静默交还给 v1/v2c 分支（§3.4）。若在这里也记一条拒收，正常 v2c
    流量会被全部记成 v3 拒收 —— 日志里全是噪音，反而看不见真问题。
    常量保留是为了日后 usmStats 计数表对齐完整。
    """

    NOT_V3 = "not_v3"
    NOT_USM = "not_usm"
    UNKNOWN_USER = "unknown_user"
    SEC_LEVEL_MISMATCH = "sec_level_mismatch"
    AUTH_FAILED = "auth_failed"
    DECRYPT_FAILED = "decrypt_failed"
    SCOPED_PDU_ERROR = "scoped_pdu_error"
    NO_TRAP_OID = "no_trap_oid"


def decode_v3_trap(
    data: bytes,
    v3_users: dict[str, dict],
    *,
    on_reject: Callable[[str, dict], None] | None = None,
) -> dict | None:
    """解码一条 SNMPv3 trap 报文。

    Args:
        data: UDP 收到的原始字节。
        v3_users: ``{username: {auth_key, priv_key, auth_protocol, priv_protocol,
            security_level}}`` —— 通常来自 ``_v3_users_from_credentials()``。
            **已本地化前**的口令（本地化在函数内按报文 engineID 完成）。
        on_reject: 可选回调 ``(reason: str, info: dict)``，用于记录拒收原因
            （计入 usmStats 对应计数、打日志）。不传则静默。

    Returns:
        dict: 见设计文档 §4.1 出口契约；解码失败返回 ``None``。
    """

    def reject(reason: str, **info: Any) -> None:
        if on_reject is not None:
            try:
                on_reject(reason, info)
            except Exception:  # 回调失败不得影响解码主流程（此处 catch 面宽是刻意的：第三方回调的异常不得传播）
                logger.debug("[trapd-v3] on_reject 回调异常", exc_info=True)
        logger.debug("[trapd-v3] 拒收: reason=%s info=%s", reason, info)

    try:
        message, _ = ber_decoder.decode(data, asn1Spec=V3Message())
    except (PyAsn1Error, ValueError, IndexError):
        return None  # 连 v3 外层都解不开 ⇒ 不是本层的事（交给 v1/v2c 分支）

    try:
        if int(message.getComponentByPosition(0)) != SNMP_V3_VERSION:
            return None
    except (TypeError, ValueError):
        return None

    header = message.getComponentByName("msgGlobalData")
    try:
        sec_model = int(header.getComponentByName("msgSecurityModel"))
        flags = parse_msg_flags(bytes(header.getComponentByName("msgFlags")))
    except (TypeError, ValueError, AttributeError, IndexError):
        return None
    if sec_model != SNMP_SEC_MODEL_USM:
        reject(V3RejectReason.NOT_USM, security_model=sec_model)
        return None
    security_level = flags["level"]

    try:
        sec_params_octets = bytes(message.getComponentByName("msgSecurityParameters"))
        params, _ = ber_decoder.decode(sec_params_octets, asn1Spec=UsmSecurityParameters())
        engine_id = bytes(params.getComponentByName("msgAuthoritativeEngineID"))
        engine_boots = int(params.getComponentByName("msgAuthoritativeEngineBoots"))
        engine_time = int(params.getComponentByName("msgAuthoritativeEngineTime"))
        username = bytes(params.getComponentByName("msgUserName")).decode(
            "utf-8", errors="replace"
        )
        auth_params = bytes(params.getComponentByName("msgAuthenticationParameters"))
        priv_params = bytes(params.getComponentByName("msgPrivacyParameters"))
    except (PyAsn1Error, ValueError, IndexError, TypeError, AttributeError):
        return None

    cred = v3_users.get(username)
    if cred is None:
        reject(V3RejectReason.UNKNOWN_USER, username=username, engine_id=engine_id.hex())
        return None

    cred_level = str(cred.get("security_level") or "").strip().lower()
    if cred_level and cred_level != security_level.lower():
        reject(
            V3RejectReason.SEC_LEVEL_MISMATCH,
            username=username, expected=cred_level, got=security_level,
        )
        return None

    auth_protocol = str(cred.get("auth_protocol") or "")
    priv_protocol = str(cred.get("priv_protocol") or "")

    if flags["auth"]:
        try:
            auth_key = usm.localize_key(
                cred.get("auth_key") or "", engine_id, auth_protocol
            )
        except usm.AuthProtocolError:
            reject(V3RejectReason.AUTH_FAILED, username=username, cause="bad_auth_protocol")
            return None
        span_in_msg = _locate_in_message(data, sec_params_octets, auth_params)
        if not usm.verify_hmac(data, auth_key, auth_params, span_in_msg, auth_protocol):
            reject(V3RejectReason.AUTH_FAILED, username=username, engine_id=engine_id.hex())
            return None

    msg_data = message.getComponentByName("msgData")
    chosen_name = msg_data.getName()
    scoped: Any = None
    if flags["priv"]:
        if chosen_name not in ("encryptedPDU", "encryptedPDU_ctx1"):
            reject(V3RejectReason.DECRYPT_FAILED, username=username, cause="not_encrypted_choice")
            return None
        try:
            priv_key = usm.localize_key(
                cred.get("priv_key") or "", engine_id, auth_protocol
            )
            scoped_bytes, _aes_key, _iv = usm.decrypt_ciphertext(
                bytes(msg_data.getComponent()),
                priv_key, engine_boots, engine_time, priv_params,
                auth_protocol, priv_protocol,
            )
        except (usm.AuthProtocolError, usm.UnsupportedProtocolError) as exc:
            reject(V3RejectReason.DECRYPT_FAILED, username=username, cause=str(exc))
            return None
        try:
            scoped, _ = ber_decoder.decode(scoped_bytes, asn1Spec=ScopedPDU())
        except (PyAsn1Error, ValueError, IndexError):
            reject(V3RejectReason.SCOPED_PDU_ERROR, username=username, cause="not_a_scoped_pdu")
            return None
    else:
        if chosen_name != "plaintext":
            reject(V3RejectReason.DECRYPT_FAILED, username=username, cause="unexpected_choice")
            return None
        scoped = msg_data.getComponent()

    trap_oid, varbinds, context_name = _unpack_scoped_pdu(scoped)
    if not trap_oid:
        reject(V3RejectReason.NO_TRAP_OID, username=username)
        return None

    return {
        "version": "v3",                     # 沿用既有键名
        "snmp_version": "v3",                # 新增别名（下游 handle_trap 的参数名）
        "community": "",                     # v3 无 community（§4.1.1 靠此放行 community 门）
        "username": username,
        "security_level": security_level,
        "engine_id": f"0x{engine_id.hex()}",
        "engine_boots": engine_boots,
        "engine_time": engine_time,
        "context_name": context_name,
        "trap_oid": trap_oid,
        "varbinds": varbinds,
    }


def _parse_scoped_pdu(scoped_bytes: bytes, *, plaintext_tagged: bool = False
                      ) -> tuple[str, list[tuple[str, str]], str]:
    """从**字节**解 ScopedPDU —— 字节层入口（便于测试与离线解析直接投喂）。

    ``plaintext_tagged`` 决定用哪个 spec 解，两者**不可互换**：

    - ``authPriv`` 解密出来的 ScopedPDU 是**裸 SEQUENCE**（无 context tag）
      → 用 ``ScopedPDU``
    - ``msgData.plaintext`` 是 **[0] IMPLICIT ScopedPDU**（带 context tag 0）
      → 用 ``PlaintextScopedPDU``

    用错会直接 BER 解不开（``TagSet not in asn1Spec``）。这个区分是本函数
    最容易错的地方，故用显式参数而非"两个都试"。
    """
    from .trap_v3_spec import PlaintextScopedPDU

    asn1_spec = PlaintextScopedPDU() if plaintext_tagged else ScopedPDU()
    try:
        scoped, _ = ber_decoder.decode(scoped_bytes, asn1Spec=asn1_spec)
    except (PyAsn1Error, ValueError, IndexError):
        return "", [], ""
    return _unpack_scoped_pdu(scoped)


def _unpack_scoped_pdu(scoped: Any) -> tuple[str, list[tuple[str, str]], str]:
    """从**已解好的 ScopedPDU 对象**取 ``(trap_oid, varbinds, context_name)``。

    v3 的 ScopedPDU.data 里装的就是标准 SNMPv2-Trap PDU（与 v2c 同构），
    故直接复用 ``pysnmp.proto.api.v2c`` 的 ``apiTrapPDU`` 取 varbinds，
    与 ``run_trapd_service.decode_trap_message`` 的 v2c 路径保持**同口径**。

    放在对象层而非字节层的原因：明文 ScopedPDU 由 pyasn1 在解 Message 时就
    顺带解好了（``Choice.getComponent()`` 返回对象），重新 encode 回字节再
    decode 一圈是纯浪费，且多余一层编码往返。priv 分支解密出的是字节，
    由 ``_parse_scoped_pdu`` 解成对象后同样汇入这里 —— **一个解释点**。
    """
    try:
        context_name = bytes(scoped.getComponentByName("contextName")).decode(
            "utf-8", errors="replace"
        )
        pdu_any = scoped.getComponentByName("data")
    except (PyAsn1Error, AttributeError, IndexError):
        return "", [], ""

    from pysnmp.proto.api import v2c as _v2c  # 延迟导入：仅解码路径需要

    try:
        pdu, _ = ber_decoder.decode(bytes(pdu_any), asn1Spec=_v2c.SNMPv2TrapPDU())
    except (PyAsn1Error, ValueError, IndexError):
        return "", [], context_name

    trap_oid = ""
    varbinds: list[tuple[str, str]] = []
    try:
        for name, value in _v2c.apiTrapPDU.get_varbinds(pdu):
            name_s = str(name).strip(".")
            pretty = getattr(value, "prettyPrint", None)
            text = pretty() if callable(pretty) else str(value)
            varbinds.append((name_s, text))
            if name_s in _trap_oid_keys():
                trap_oid = text.strip().lstrip(".")
    except Exception:  # varbinds 解析异常只丢该条，不得终止收包（catch 面宽是刻意的：单条 varbind 损坏不得拖垮整包）
        logger.debug("[trapd-v3] varbinds 解析异常", exc_info=True)
        return "", varbinds, context_name

    return trap_oid, varbinds, context_name


def _locate_in_message(raw: bytes, sec_params: bytes, auth_params: bytes) -> tuple[int, int]:
    """把 auth_params 在 secParams 内的偏移换算成**在整条报文**内的偏移。

    HMAC 是对**整条报文**算的（authParams 字段零替换），所以偏移必须是全局的。
    这里用 TLV 框架推 secParams 内容起始位置，而不是 ``raw.find(sec_params)``
    —— 后者在报文里存在相同字节片段时会定位错（同 §6.1 TLV 定位判据的考量）。
    """
    if not auth_params:
        return (0, 0)
    inner_start = _index_of_secparams_content(raw, len(sec_params))
    if inner_start < 0:
        return (0, 0)
    span = usm.locate_auth_params_span(sec_params, auth_params)
    if span == (0, 0):
        return (0, 0)
    return (inner_start + span[0], inner_start + span[1])


def _index_of_secparams_content(raw: bytes, content_len: int) -> int:
    """返回 raw 中 secParams **内容**的起始下标（跳过 TLV 头）。

    secParams 是 Message 的第 3 个组件（OCTET STRING，tag 0x04）。
    按出现的第 3 个顶层 TLV 定位不够稳（msgID 等长度可变），这里改为：
    在 raw 中找第一个满足「tag=0x04 且长度等于 content_len 且后续能完整放下」的位置。
    """
    i, n = 0, len(raw)
    while i < n:
        if raw[i] != 0x04:
            i += 1
            continue
        if i + 1 >= n:
            break
        length_byte = raw[i + 1]
        if length_byte < 0x80:
            start, value_len = i + 2, length_byte
        else:
            num = length_byte & 0x7F
            if num == 0 or i + 2 + num > n:
                i += 1
                continue
            start = i + 2 + num
            value_len = int.from_bytes(raw[i + 2 : i + 2 + num], "big")
        if value_len == content_len and start + value_len <= n:
            return start
        i += 1
    return -1
