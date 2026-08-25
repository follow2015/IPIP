# -*- coding: utf-8 -*-
"""SNMP 版本凭据字段映射（纯数据模块，无适配器依赖）。

将 SNMP 版本 → 必填字段的映射从此模块导出，供 schema 校验层
（`schemas/monitor.py`）和适配器层（`adapters/snmp_adapter.py`）共同引用，
避免 dual source of truth。

此模块不 import 任何适配器类，因此不会与 `protocol_registry.py` 或
`snmp_adapter.py` 形成循环依赖。
"""
from typing import Dict, List

SNMP_REQUIRED_BY_VERSION: Dict[str, List[str]] = {
    "v2c": ["community"],
    "v3": ["username", "auth_key", "priv_key"],
}
