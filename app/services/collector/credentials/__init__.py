# -*- coding: utf-8 -*-
"""多通道采集 · 通道层凭据子包（T0.6 / G9）。

规格：``docs/spec/多通道采集-契约层规格-T0.3.md`` 决策 4、§3.5。
"""
from app.services.collector.credentials.snmp_credential import (
    SNMP_AUTH_PROTOCOLS,
    SNMP_PRIV_PROTOCOLS,
    SnmpCredential,
    SnmpCredentialError,
    SnmpCredentialProvider,
)

__all__ = [
    "SNMP_AUTH_PROTOCOLS",
    "SNMP_PRIV_PROTOCOLS",
    "SnmpCredential",
    "SnmpCredentialError",
    "SnmpCredentialProvider",
]
