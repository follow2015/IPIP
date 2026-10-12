# -*- coding: utf-8 -*-
"""SNMP 类检测器：v2c 在用 / 弱默认团体名。

**凭据解密约束**（总纲 §7.3）：进程内**逐条解密、逐条丢弃**；finding 的 `detail`
只留布尔/枚举结论，**不落盘、不入日志、不回传任何原值** —— `community` 是口令级
敏感值，一旦进 findings（会流向 API、前端、可能被复制进工单）就等于把凭据明文
扩散到另一张表。故命中时只写 `{"issue": "default_community"}`。

**为什么不直接 `MonitorCredential.query.filter_by(...)`**（与 WBS 示例不同，
同 Task 7）：`tests/test_service_layer_session_budget.py` 的 C 类台账
（`Model.query` / `cls.query`）预算为 **0** 且只减不增。查询收进
`MonitorCredentialRepository.list_enabled_by_protocol`，**密文跨层传递**
（解密只在安全中心这一侧发生）。

**版本判定引用单一真源**：`snmp_versions.resolve_snmp_version(payload)` ——
它兼容 `snmp_version` / `version` 两个键名且按"值是否为 None"判定；检测器若自造
判断就会与采集侧再次漂移（历史上正是这种漂移导致"校验通过、运行必失败"）。
"""
import json

from app.persistence.monitor_credential_repository import MonitorCredentialRepository
from app.services.monitoring.snmp_versions import resolve_snmp_version
from app.services.security.policy_service import get_value
from app.services.security.scanner import Violation, register_check
from app.utils.logging import get_logger
from app.utils.security.encryption import decrypt

logger = get_logger(__name__)

_WEAK_COMMUNITIES = {"public", "private", ""}


def _iter_snmp_payloads():
    """逐条解密 SNMP 凭据，产出 `(credential_id, payload)`；解不开则跳过该条。

    单条解不开**只跳过它自己**，不让整轮扫描空手而归：否则一条坏密文就能让
    "本轮无发现"成立，而**巡检静默失效**是安全中心最危险的形态 —— 页面一直绿，
    没人知道它什么都没扫。
    """
    for cred in MonitorCredentialRepository().list_enabled_by_protocol("snmp"):
        try:
            payload = json.loads(decrypt(cred.encrypted_payload))
        except Exception:  # 单条解密失败不影响其他凭据，仅告警跳过（不写 noqa：此处未触发 BLE001）
            logger.warning("凭据解密失败，安全巡检跳过该条: credential_id=%s",
                           cred.id, exc_info=True)
            continue
        if not isinstance(payload, dict):
            continue
        yield cred.id, payload


@register_check("snmp.v2c_in_use", severity="high", subject_type="credential")
def check_v2c_in_use() -> list:
    """`snmp.allowed_versions` 不含 v2c 后，仍在用 v2c 的凭据逐条报出。

    默认 `["v2c", "v3"]` ⇒ 直接返回空（升级零行为变化，见模块 docstring）。
    """
    allowed = get_value("snmp.allowed_versions") or ["v2c", "v3"]
    if "v2c" in allowed:
        return []
    return [
        Violation(subject_id=cred_id, detail={"version": "v2c"})
        for cred_id, payload in _iter_snmp_payloads()
        if resolve_snmp_version(payload) == "v2c"
    ]


@register_check("snmp.default_community", severity="critical", subject_type="credential")
def check_default_community() -> list:
    """开启 `forbid_default_community` 后，弱/默认团体名的 **v2c** 凭据告警。

    为什么限定 v2c：v3 根本没有 community 概念，不限定就会对 v3 凭据误报。
    为什么 v2c 被全面禁止时本条让位：`snmp.v2c_in_use` 已经覆盖了"还在用 v2c"
    这一更严重的事实，两条同时报同一条凭据只会重复计数（G2 跨项一致性）。
    """
    if not get_value("snmp.forbid_default_community"):
        return []
    allowed = get_value("snmp.allowed_versions") or ["v2c", "v3"]
    if "v2c" not in allowed:
        return []
    out = []
    for cred_id, payload in _iter_snmp_payloads():
        if resolve_snmp_version(payload) != "v2c":
            continue
        community = (payload.get("community") or "").strip()
        if community in _WEAK_COMMUNITIES:
            out.append(Violation(subject_id=cred_id,
                                 detail={"issue": "default_community"}))
    return out
