# -*- coding: utf-8 -*-
"""SNMPv3 (USM authPriv) 报文 ASN.1 规格 —— 纯规格，无 IO、无状态。

设计文档：``docs/design/trapd-SNMPv3支持-设计文档-20261006.md`` §3.1 / §3.4。

为什么自己写 ASN.1 规格而不用 pysnmp 的 ``hlapi`` / ``SnmpEngine``：
与本仓 trapd 既有取向一致（``run_trapd_service.py`` docstring 已说明）。
但 **密码学原语**（密钥本地化 / HMAC / AES）改为引用 ``pysnmp.proto.secmod``
层 —— 该层是纯计算模块，不涉及传输与事件循环（决策见设计文档 §9.1）。

[WARN]️ 三个实测坑位（均已在现场报文上撞过，改动前请先读）：

1. **加密 ScopedPDU 的 BER tag 是裸 ``0x04``（OCTET STRING）**，不是 RFC 3412
   图上画的 ``[1]``。pysnmp 7.1.27 实现如此。只按 ``[1]`` 定义 asn1Spec 会报
   ``TagSet object, tags 0:0:4 not in asn1Spec``。故 ``ScopedPduData`` 同时
   接受三种形态。
2. **engineID 有两套**：trap 报文里的 ``msgAuthoritativeEngineID``（实测华为
   ``0x800007db03845b125ab2f1``）与 SNMP ``get_cmd`` 查到的**不同**。
   解密/校验必须用报文里的，取错则静默解不开。
3. **``msgVersion`` 必须按位置索引 0 取 INTEGER 值**（0=v1 / 1=v2c / 3=v3），
   不依赖字段名。
"""

from pyasn1.type import namedtype, tag, univ

__all__ = [
    "HeaderData",
    "PlaintextScopedPDU",
    "ScopedPDU",
    "ScopedPduData",
    "UsmSecurityParameters",
    "V3Message",
    "SNMP_V3_VERSION",
    "SNMP_SEC_MODEL_USM",
    "MSG_FLAG_AUTH",
    "MSG_FLAG_PRIV",
    "MSG_FLAG_REPORTABLE",
    "parse_msg_flags",
]

SNMP_V3_VERSION = 3

SNMP_SEC_MODEL_USM = 3

MSG_FLAG_AUTH = 0x01
MSG_FLAG_PRIV = 0x02
MSG_FLAG_REPORTABLE = 0x04


class HeaderData(univ.Sequence):
    """``msgGlobalData``：报文的全局头（RFC 3412 §6）。"""

    componentType = namedtype.NamedTypes(
        namedtype.NamedType("msgID", univ.Integer()),
        namedtype.NamedType("msgMaxSize", univ.Integer()),
        namedtype.NamedType("msgFlags", univ.OctetString()),
        namedtype.NamedType("msgSecurityModel", univ.Integer()),
    )


class ScopedPDU(univ.Sequence):
    """解密后的 ScopedPDU 结构（RFC 3412 §5.5）。

    实测现场样本：``contextName`` 为空串（华为 CE6850HI）。
    ``data`` 用 ``Any`` 承载 —— v3 的 ScopedPDU.data 里装的是标准
    SNMPv2-Trap PDU（与 v2c 同构），解析时交给 ``v2c.SNMPv2TrapPDU``。
    """

    componentType = namedtype.NamedTypes(
        namedtype.NamedType("contextEngineID", univ.OctetString()),
        namedtype.NamedType("contextName", univ.OctetString()),
        namedtype.NamedType("data", univ.Any()),
    )


class PlaintextScopedPDU(ScopedPDU):
    """``msgData.plaintext`` 用的形态：**带 [0] IMPLICIT tag** 的 ScopedPDU。

    RFC 3412 的 ScopedPduData 定义为 ``plaintext [0] IMPLICIT ScopedPDU``，
    所以明文路径传给 Choice 的值**必须**带上 context tag 0，否则 pyasn1 报
    ``Component value is tag-incompatible``（构造 Message 时才会炸，而非运行期
    才暴露 —— 这是本分支最容易卡住的地方）。

    与之相对，``authPriv`` 解密出来的 ScopedPDU 是**无 tag** 的，用父类解。
    两个类刻意分开，避免"解出来 tag 对不上"的静默失败。
    """

    tagSet = ScopedPDU.tagSet.tagImplicitly(
        tag.Tag(tag.tagClassContext, tag.tagFormatConstructed, 0)
    )


class ScopedPduData(univ.Choice):
    """``msgData`` 的 Choice：明文 ScopedPDU 或加密后的字节串。

    [WARN]️ ``encryptedPDU`` 的**第一个**定义（裸 ``OctetString()``）才是
    pysnmp 7.1.27 实际产生的形态。``encryptedPDU_ctx1`` 是为了兼容严格按
    RFC 3412 图定义 ``[1]`` 的实现（华为设备实测走裸 ``0x04``）。
    两个名字必须都保留 —— 删掉任一都会在某些实现上解码失败。
    """

    componentType = namedtype.NamedTypes(
        namedtype.NamedType("plaintext", PlaintextScopedPDU()),
        namedtype.NamedType("encryptedPDU", univ.OctetString()),
        namedtype.NamedType(
            "encryptedPDU_ctx1",
            univ.OctetString().subtype(
                implicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple, 1)
            ),
        ),
    )


class UsmSecurityParameters(univ.Sequence):
    """``msgSecurityParameters`` 内部 BER 解码后的 USM 安全参数（RFC 3414 §2.4）。

    注意：在 ``V3Message`` 里它是一个 **OCTET STRING**（装着 BER 字节）；
    本类用于对该 OCTET STRING **二次解码**后的结构。
    """

    componentType = namedtype.NamedTypes(
        namedtype.NamedType("msgAuthoritativeEngineID", univ.OctetString()),
        namedtype.NamedType("msgAuthoritativeEngineBoots", univ.Integer()),
        namedtype.NamedType("msgAuthoritativeEngineTime", univ.Integer()),
        namedtype.NamedType("msgUserName", univ.OctetString()),
        namedtype.NamedType("msgAuthenticationParameters", univ.OctetString()),
        namedtype.NamedType("msgPrivacyParameters", univ.OctetString()),
    )


class V3Message(univ.Sequence):
    """SNMPv3 Message（RFC 3412 §6）顶层结构。

    组件顺序即线序：``msgVersion`` / ``msgGlobalData`` /
    ``msgSecurityParameters``(OCTET STRING) / ``msgData``(Choice)。
    """

    componentType = namedtype.NamedTypes(
        namedtype.NamedType("msgVersion", univ.Integer()),
        namedtype.NamedType("msgGlobalData", HeaderData()),
        namedtype.NamedType("msgSecurityParameters", univ.OctetString()),
        namedtype.NamedType("msgData", ScopedPduData()),
    )


def parse_msg_flags(msg_flags: bytes) -> dict:
    """把 ``msgFlags`` 单字节解成三个布尔位 + 安全级别字符串。

    Args:
        msg_flags: ``msgFlags`` 的原始字节（实测华为设备为 ``b"\\x03"``）。

    Returns:
        dict: ``{"auth": bool, "priv": bool, "reportable": bool, "level": str}``

        ``level`` 取值：``"noAuthNoPriv"`` / ``"authNoPriv"`` / ``"authPriv"``。
        ``auth=False, priv=True`` 是非法的（RFC 3412：priv 隐含 auth），
        此处按 ``"authPriv"`` 之外的最低档处理为 ``"noAuthNoPriv"`` 并在
        ``level`` 上体现为无法满足的档位 —— 调用方（``_decode_v3``）负责拒绝。

    Examples:
        >>> parse_msg_flags(b"\\x03")
        {'auth': True, 'priv': True, 'reportable': False, 'level': 'authPriv'}
    """
    value = msg_flags[0] if msg_flags else 0
    auth = bool(value & MSG_FLAG_AUTH)
    priv = bool(value & MSG_FLAG_PRIV)
    reportable = bool(value & MSG_FLAG_REPORTABLE)
    if auth and priv:
        level = "authPriv"
    elif auth:
        level = "authNoPriv"
    else:
        level = "noAuthNoPriv"
    return {"auth": auth, "priv": priv, "reportable": reportable, "level": level}
