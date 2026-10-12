# -*- coding: utf-8 -*-
"""安全巡检引擎：跑全部已注册检测器 → upsert findings → 告警。

设计依据：一期文档 §5/§8。纪律：
- 每条 rule 对每个 subject 只产生一条 finding（`uq_rule_subject`），重复命中只刷
  `last_seen`；本轮不再违规则把旧行转 `resolved`；
- **只读被扫描对象、只写 findings，绝不自动修复**；
- Redis 锁防定时与手动触发重入，**扫描结束即释放**（TTL 600s 只兜底进程被杀）；
  `dry_run` 不落库（供 enforce 前影响预览）。

与实施计划原稿的三处差异（都在本节登记，并同步到设计文档 §11.2）：
- 查询走 `SecurityFindingRepository`，不在 service 层直查模型 ——
  `tests/test_service_layer_session_budget.py` 的 C 类台账预算为 **0** 且只减不增；
- logger 用 `get_logger`，不用裸 `logging.getLogger` ——
  `tests/test_logger_convergence_guard.py` 已上提到全 app 树（SNMP 评审 N16）；
- 扫描锁改为**结束后释放自己持有的那把**（原稿只靠 600s TTL 过期）：只靠 TTL 会让
  "手动触发巡检"在 10 分钟内静默返回 `skipped`，且计划自带的
  `test_resolved_when_no_longer_violating` 正因此拿不到第二次执行。
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from app.models.security_finding import SYSTEM_SUBJECT_ID, SecurityFinding
from app.persistence.security_finding_repository import SecurityFindingRepository
from app.utils import redis_keys
from app.utils.logging import get_logger
from app.utils.redis_client import get_redis_client
from app.utils.time_utils import now_utc_naive
from extensions import db

logger = get_logger(__name__)

_SCAN_LOCK_TTL = 600


@dataclass
class Violation:
    """一条违规：主体 + 摘要（`detail` 禁含明文口令 / SNMP community）。"""

    subject_id: int | None
    detail: dict


@dataclass
class CheckSpec:
    """检测器声明：规则身份 + 严重级 + 主体类型 + 执行函数。"""

    rule_id: str
    severity: str
    subject_type: str
    fn: object


_CHECKS: dict[str, CheckSpec] = {}


def register_check(rule_id: str, severity: str, subject_type: str):
    """注册检测器（被装饰的函数应返回 `list[Violation]`）。

    重复注册**直接报错**而不是静默覆盖：两个模块抢同一个 rule_id 时，覆盖会让
    "谁在跑"变得不可知，且 findings 的 severity/subject_type 会跟着漂移。
    """

    def _wrap(fn):
        if rule_id in _CHECKS:
            raise RuntimeError(f"检测器重复注册: {rule_id}")
        _CHECKS[rule_id] = CheckSpec(rule_id, severity, subject_type, fn)
        return fn

    return _wrap


def iter_checks() -> list:
    """全部已注册检测器（顺序稳定，便于测试与排查）。"""
    return list(_CHECKS.values())


def _normalize_subject_id(value) -> int:
    """系统级主体一律归到哨兵 `0`（禁止 NULL，见评审 P1）。"""
    return SYSTEM_SUBJECT_ID if value in (None, "") else int(value)


def upsert_finding(rule_id: str, severity: str, subject_type: str, subject_id, detail: dict) -> SecurityFinding:
    """插入或刷新一条 finding（唯一键 `(rule_id, subject_type, subject_id)`）。

    已存在时：刷 severity/detail/last_seen；若此前是 `resolved`（本行为已消除但重新
    违规），置回 `open` 并清空 `resolved_at` —— 否则"消除又复发"会被永久记为已解决。
    """
    sid = _normalize_subject_id(subject_id)
    now = now_utc_naive()
    row = SecurityFindingRepository().find_by_subject(rule_id, subject_type, sid)
    if row is None:
        row = SecurityFinding(rule_id=rule_id, severity=severity, subject_type=subject_type,
                              subject_id=sid, status="open", detail=detail,
                              first_seen=now, last_seen=now)
        db.session.add(row)
    else:
        row.severity = severity
        row.detail = detail
        row.last_seen = now
        if row.status != "open":
            row.status = "open"
            row.resolved_at = None
    db.session.flush()
    return row


def resolve_missing(rule_id: str, keep_subject_ids: set) -> int:
    """把本轮未再违规的旧 finding 置 `resolved`；返回处理条数。"""
    now = now_utc_naive()
    rows = SecurityFindingRepository().find_open_excluding(rule_id, keep_subject_ids)
    for row in rows:
        row.status = "resolved"
        row.resolved_at = now
    db.session.flush()
    return len(rows)


def run_scan(dry_run: bool = False) -> dict:
    """跑一轮全量巡检。

    Args:
        dry_run: 为真时**不写库、不告警**（也**不受扫描锁限制** —— 它是只读预览，
            挡下来只会让"切 enforce 前先看看会命中什么"这个用途失效），
            返回本轮"将产生"的发现项。

    Returns:
        `{"ok", "skipped", "dry_run", "summary", "findings"}`；被锁挡下时
        `skipped=True`。单个检测器抛异常只跳过该项（其余照跑），整体异常回滚后上抛。
    """
    client = get_redis_client()
    lock_acquired = False
    if client is not None and not dry_run:
        try:
            lock_acquired = bool(
                client.set(redis_keys.SECURITY_SCAN_LOCK_KEY, "1", nx=True, ex=_SCAN_LOCK_TTL)
            )
            if not lock_acquired:
                return {"ok": True, "skipped": True, "reason": "locked"}
        except Exception:
            logger.warning("扫描锁不可用，继续执行（fail-open）", exc_info=True)

    summary, collected = {}, []
    try:
        for spec in iter_checks():
            try:
                violations = spec.fn() or []
            except Exception:
                logger.warning("检测器执行失败，跳过本轮该项: %s", spec.rule_id, exc_info=True)
                continue
            summary[spec.rule_id] = len(violations)
            keep = set()
            for v in violations:
                sid = _normalize_subject_id(v.subject_id)
                keep.add(sid)
                collected.append({"rule_id": spec.rule_id, "severity": spec.severity,
                                  "subject_type": spec.subject_type, "subject_id": sid,
                                  "detail": v.detail})
                if not dry_run:
                    upsert_finding(spec.rule_id, spec.severity, spec.subject_type, sid, v.detail)
            if not dry_run:
                resolve_missing(spec.rule_id, keep)
        if not dry_run:
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    finally:
        if lock_acquired:
            try:
                client.delete(redis_keys.SECURITY_SCAN_LOCK_KEY)
            except Exception:
                logger.warning("释放扫描锁失败（等 TTL 自动过期）", exc_info=True)
    return {"ok": True, "skipped": False, "dry_run": dry_run,
            "summary": summary, "findings": collected}


def notify_violations(result: dict) -> int:
    """对违规项发告警（按天幂等，防重复轰炸）。返回发送条数。

    用 `notify_strict` 而非 `notify`：`notify` 把投递失败吞成 `None`，与幂等去重
    无法区分，安全告警会静默丢失。
    """
    from app.services.notification_service import notification_service

    today = _dt.date.today().isoformat()
    sent = 0
    for rule_id, count in (result.get("summary") or {}).items():
        if count <= 0:
            continue
        spec = _CHECKS[rule_id]
        severity = "critical" if spec.severity in ("critical", "high") else "warning"
        try:
            notification_service.notify_strict(
                type="security.finding", severity=severity,
                title=f"安全巡检发现：{rule_id}",
                content=f"本轮发现 {count} 项违规，请在安全中心查看明细",
                payload={"rule_id": rule_id, "count": count},
                source_module="security_center",
                idempotency_key=f"security:{rule_id}:{today}",
                ack_required=True,
            )
            sent += 1
        except Exception:
            logger.warning("安全告警投递失败（不影响巡检）: %s", rule_id, exc_info=True)
    return sent


from app.services.security import checks as _registered_checks  # noqa: E402,F401
