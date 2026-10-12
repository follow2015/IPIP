# -*- coding: utf-8 -*-
"""SNMP 策略闸门：写入期与运行期**共用一个判定真源**。

- 写入期：凭据保存 / 改密文前调用 `validate_credential` —— off/audit 放行、enforce 拒绝；
- 运行期：`snmp_adapter` 发包前调用 `check_runtime` —— enforce 拒发包（覆盖"策略收紧前
  就已存在"的存量凭据，这是写入期管不到的那一半）。

两处共用一个 `_evaluate`，是为了避免"写入期拦、运行期放"（或反之）这类只在一条路径上
出现的缺口：口径一旦分叉，页面说的和实际做的就会不一致。

与实施计划原稿的两处差异（同步登记到设计文档 §11.2）：
- logger 用 `app.utils.logging.get_logger`（原稿 `logging.getLogger`，与 D-8 同口径）；
- `_record_findings` 用 **savepoint** 而不是裸 `db.session.rollback()` —— 后者会把
  调用方（凭据保存）尚未提交的写操作一起回滚，audit 模式就变成"悄悄丢数据"。
"""
from __future__ import annotations

from app.services.monitoring.snmp_versions import resolve_snmp_version
from app.services.security.policy_service import get_value
from app.utils.logging import get_logger

logger = get_logger(__name__)

_WEAK_COMMUNITIES = {"public", "private", ""}

_SEVERITY = {"snmp.v2c_in_use": "high", "snmp.default_community": "critical",
             "snmp.unsupported_version": "medium"}

_HINTS = {
    "snmp.v2c_in_use": "策略要求 SNMP v3，禁止保存 v2c 凭据",
    "snmp.default_community": "禁止使用 public/private/空团体名",
    "snmp.unsupported_version": "SNMP 版本不在允许列表内",
}


def _evaluate(payload: dict) -> list:
    """评估一份 SNMP 凭据 payload 命中的策略规则。

    Returns:
        list[str]：规则 id 列表（空 = 无违规）。
    """
    violations = []
    version = resolve_snmp_version(payload)
    allowed = get_value("snmp.allowed_versions") or ["v2c", "v3"]
    if version not in allowed:
        violations.append("snmp.v2c_in_use" if version == "v2c" else "snmp.unsupported_version")
    if version == "v2c" and "v2c" in allowed and get_value("snmp.forbid_default_community"):
        if (payload.get("community") or "").strip() in _WEAK_COMMUNITIES:
            violations.append("snmp.default_community")
    return violations


def _record_findings(rule_ids: list, subject_id=None) -> None:
    """audit 模式：把违规记为 finding（幂等；失败不影响主流程）。

    用 `begin_nested()`（savepoint）而不是裸 `rollback()`：调用方（凭据保存）此刻
    可能已有未提交的写操作，裸回滚会连带丢弃它们 —— audit 模式的语义是"放行 + 留痕"，
    不是"顺手把用户的保存吞掉"。
    """
    from app.models.security_finding import SYSTEM_SUBJECT_ID
    from app.services.security.scanner import upsert_finding
    from extensions import db

    try:
        with db.session.begin_nested():
            for rule_id in rule_ids:
                upsert_finding(rule_id, _SEVERITY.get(rule_id, "medium"), "credential",
                               subject_id if subject_id is not None else SYSTEM_SUBJECT_ID,
                               {"source": "write_gate"})
        db.session.commit()
    except Exception:
        logger.warning("SNMP 闸门记录 finding 失败（忽略，不影响保存）", exc_info=True)


_THROTTLE_TTL = 3600


def _throttled(credential_id, rule_id) -> bool:
    """同一凭据、同一规则在 `_THROTTLE_TTL` 内是否已记过 finding。

    运行期判定跑在**监控轮询**里（分钟级、数百台设备），不做节流会把
    `security_findings` 刷爆 —— 一次全量轮询就能写出上万行同内容的记录。

    Redis 不可用时返回 False（**不节流**）：宁可多记几条，也不要因为缓存故障而
    让运行期违规彻底不留痕；finding 本身按唯一键幂等，重复只是多一次 upsert。

    Returns:
        bool：True = 本次应跳过记录。
    """
    from app.utils import redis_keys
    from app.utils.redis_client import get_redis_client

    client = get_redis_client()
    if client is None:
        return False
    try:
        key = (f"{redis_keys.SECURITY_SNMP_GATE_THROTTLE_PREFIX}"
               f"{credential_id}:{rule_id}")
        return not client.set(key, "1", nx=True, ex=_THROTTLE_TTL)
    except Exception:
        logger.warning("SNMP 闸门节流判定失败（按不节流处理）", exc_info=True)
        return False


def validate_credential(payload: dict) -> None:
    """写入期校验（凭据保存 / 改密文之前调用）。

    Raises:
        ValidationError: `snmp.mode=enforce` 且命中策略违规。
    """
    from app.exceptions import ValidationError

    mode = get_value("snmp.mode")
    if mode == "off":
        return
    rule_ids = _evaluate(payload)
    if not rule_ids:
        return
    if mode == "audit":
        _record_findings(rule_ids)
        return
    raise ValidationError("；".join(_HINTS.get(r, r) for r in rule_ids))


def check_runtime(credential: dict, version: str = None, credential_id=None) -> tuple:
    """运行期判定（发包前调用，覆盖存量凭据）。

    Args:
        credential: 用于判定的凭据 payload。
        version: 调用方已知的版本（仅作参考，判定仍以 payload 为准，避免两处解析分叉）。
        credential_id: 凭据 id，用于 audit 模式的 finding 主体与节流键；
            缺失时退化为"不节流 + 系统级主体"（enforce 分支不依赖它）。

    Returns:
        tuple[bool, str | None, str | None]：`(是否放行, 命中的规则 id, 拒绝原因)`。
        audit 模式放行但给出规则 id（供调用方留痕）；enforce 下违规返回
        `(False, rule_id, "policy_violation:<rule_id>")`。
    """
    mode = get_value("snmp.mode")
    if mode == "off":
        return True, None, None
    rule_ids = _evaluate(credential)
    if not rule_ids:
        return True, None, None
    if mode == "audit":
        if credential_id is None or not _throttled(credential_id, rule_ids[0]):
            _record_findings(rule_ids, subject_id=credential_id)
        return True, rule_ids[0], None
    return False, rule_ids[0], f"policy_violation:{rule_ids[0]}"
