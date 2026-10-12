# -*- coding: utf-8 -*-
"""SNMP 版本凭据字段映射（纯数据模块，无适配器依赖）。

将 SNMP 版本 → 必填字段的映射从此模块导出，供 schema 校验层
（`schemas/monitor.py`）和适配器层（`adapters/snmp_adapter.py`）共同引用，
避免 dual source of truth。

此模块不 import 任何适配器类，因此不会与 `protocol_registry.py` 或
`snmp_adapter.py` 形成循环依赖。
"""
from typing import Any, Dict, List

SNMP_REQUIRED_BY_VERSION: Dict[str, List[str]] = {
    "v2c": ["community"],
    "v3": ["username", "auth_key", "priv_key"],
}


def resolve_snmp_version(payload: dict) -> Any:
    """从凭据 payload 解析 SNMP 版本键 —— **单一真源**。

    兼容两种键名：``snmp_version``（现行）与 ``version``（历史，键名漂移期残留）。

    判据是「**值是否为 None**」，不是「键是否存在」：

    - ``{"version": None, "snmp_version": "v3", ...}`` 这样的行**在库里真实存在**
      （见 ``SnmpCredential.from_payload`` 的兼容注释）。按键存在即返回，会让它
      解析出 ``None`` ⇒ ``unsupported_version:None`` ⇒ 采集全失败；
      而校验层当时用的是按值判（``or`` 链）⇒ **放行入库**。
      两处口径不一致 ⇒ 「校验通过、运行必失败」，本函数即为消灭该分歧而存在。
    - ★ 空串**不**视为缺省：``{"version": ""}`` 原样返回 ``""``，交由调用方的
      白名单校验判非法。这是**故意**的 —— ``""`` 代表调用方明确给了一个非法值，
      回退 v2c 就成了「静默降级」，正是 ``snmp_credential`` 那三道闸要拦的事。
      修复本缺陷**不得**顺手把这道闸放开。
    - 两个键都不存在（或值均为 None）才回退 ``"v2c"``。

    返回值不对类型做强制转换（原样透出），以便非法类型/取值落到白名单校验处报错，
    错误信息里能看见**原始值**（如 ``unsupported_version:None`` 曾是排障线索）。
    """
    version = payload.get("version")
    if version is None:
        version = payload.get("snmp_version")
    if version is None:
        return "v2c"
    return version

