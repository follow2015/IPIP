# -*- coding: utf-8 -*-
"""
SNMP Trap 接收 → 统一告警链路（P1-1）

把 trapd 服务收到的原始 trap 加工成与指标告警**同构**的告警行：
设备关联（源 IP → Device）→ 规则匹配 → 限流 → 统一治理门面（静默 G4.1 +
风暴抑制 G13，其 300s 节流窗口即 DoD 的「同一事件 5 分钟只认一次」）→
outbox 入箱 → SSE 发布 → 事件聚合。

**告警链路零旁路**：不新建通知通道、不另起日志表，全部复用既有
MonitorAlertOutbox / alert_ingress / incident_aggregator（与 MetricAlertService
._enqueue 同一模式），trapd 只是第 N 个告警生产者。

**fail-open 语义**：Redis 故障时治理门面自身放行（既有设计）；未知 trap 与
未知源 IP 不产生告警，只落结构化 WARNING 日志（供补规则/补设备档案）。
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Optional

from app.utils.logging import get_logger
from app.services.monitoring import if_mib
from app.services.monitoring.trap_rule_service import TrapRuleMatcher, render_text
from app.services.monitoring.trap_sanitize import sanitize_varbinds

logger = get_logger(__name__)

LEGACY_TRAP_ALERT_TYPE = "trap"

TRAP_ALERT_TYPE_PREFIX = "trap_"

TRAP_ALERT_TYPE_FALLBACK = f"{TRAP_ALERT_TYPE_PREFIX}other"

_ALERT_TYPE_MAX_LEN = 40


def trap_alert_type(rule_name: str) -> str:
    """规则名 → 细分告警类型（``link_down`` → ``trap_link_down``）。

    为什么要细分：原实现全部 trap 共用 ``"trap"`` ⇒ **类型维度无法区分**
    linkDown / linkUp / 认证失败，既不能按类型订阅过滤，也跟轮询侧
    （``device_unreachable`` / ``port_status_changed`` …）对不齐口径。用户
    反馈的"trap 告警类型和轮询出来的不一样"即此（2026-10-08）。
    """
    candidate = f"{TRAP_ALERT_TYPE_PREFIX}{rule_name}"
    if len(candidate) <= _ALERT_TYPE_MAX_LEN:
        return candidate
    return TRAP_ALERT_TYPE_FALLBACK


class TrapRateLimiter:
    """进程内滑动窗口限流（trap 风暴第一道闸，保护 DB 与告警链路）。

    窗口内超过上限直接拒收（拒收的 trap 有日志，不影响后续窗口）。
    与治理门面的按 dedup_key 抑制互补：这里按**全局速率**，那里按**事件**。

    为什么刻意保持"进程内"而不是改成 Redis 分布式限流
    --------------------------------------------------
    这类"进程内状态在大 N 下闸值放大"的缺陷在本仓出现过三次（B1/B2/M6），
    评审也据此把本处登记为待评估项。**评估结论是不该改**，理由三条：

    1. **没有多实例**。本限流只被 ``trapd`` 使用，而 ``trapd`` 在
       ``deploy/systemd/ipip-trapd.service`` 里是 ``Type=simple`` + 单条
       ``ExecStart``，既无 ``--workers`` 也无 ``num-procs`` —— 进程内状态
       就是全局状态，"N × 配置值"里的 N 恒为 1。
       ``tests/test_trapd_process_model.py`` 把这条**钉成了可判定事实**：
       若将来 trapd 改成多实例，那条门禁会先红，届时再谈分布式限流。
    2. **它的职责是保护本进程**。限流挡在收包队列之后、DB 之前，目的是
       "别让 trap 风暴把本进程的 DB 池打爆"。改用 Redis 意味着第一道闸
       依赖 Redis —— 与 trap 链路"Redis 故障时 fail-open 继续收"的既定语义
       （见模块 docstring）矛盾：Redis 一挂，风暴就没有任何闸了。
    3. **成本不成比例**：换来的是"多实例下更准的闸值"，而多实例当前不存在。

    线程安全的口径（重要）
    ----------------------
    ``allow()`` 当前**只被 ``trapd-worker`` 这一个线程调用**（收包线程只负责
    ``put`` 进队列，见 ``run_trapd_service.py``）。故这里**不使用锁**：
    保留一把"看起来在保护、实际没有并发对手"的锁，是**主动制造虚假的安全感**
    —— 真要在多线程下用它，会静默产生窗口错乱，而不是报错。

    若将来确需多线程调用，请二选一（不要只加锁就当完事）：
      * 多线程且都读同一进程状态 ⇒ 用 ``threading.Lock`` 把
        "清理过期 → 判配额 → 追加"整体包起来；
      * 多进程/多实例 ⇒ 换成 Redis 限流（``app/utils/rate_limiting``）。
    """

    def __init__(self, max_per_minute: int, window_seconds: float = 60.0):
        self._max = max(1, int(max_per_minute))
        self._window = window_seconds
        self._events: deque[float] = deque()

    def allow(self, now: Optional[float] = None) -> bool:
        """登记一次事件并返回是否放行。

        [WARN] 非线程安全（刻意，见类 docstring）。当前唯一调用方是
        ``run_trapd_service.py`` 的 ``trapd-worker`` 单线程。
        """
        ts = now if now is not None else time.monotonic()
        events = self._events
        while events and ts - events[0] >= self._window:
            events.popleft()
        if len(events) >= self._max:
            return False
        events.append(ts)
        return True


class TrapIngressService:
    """Trap 处理入口（纯加工，不含 UDP 传输层，便于单测与复用）。"""

    def __init__(self, matcher: Optional[TrapRuleMatcher] = None,
                 rate_limiter: Optional[TrapRateLimiter] = None):
        self._matcher = matcher or TrapRuleMatcher()
        self._limiter = rate_limiter


    @staticmethod
    def resolve_device(source_ip: str):
        """源 IP → Device（软删除除外）。复用 management_ip 同步口径。"""
        from app.persistence.device_repository import DeviceRepository

        return DeviceRepository().find_by_management_ip(source_ip)


    def handle_trap(
        self,
        source_ip: str,
        snmp_version: str,
        community: str,
        trap_oid: str,
        varbinds: Optional[list[tuple[str, Any]]] = None,
        received_at: Optional[float] = None,
    ) -> dict[str, Any]:
        """处理一条已解码的 trap，返回处理结论（供日志与服务统计）。

        Returns:
            dict: {"action": "alerted"|"suppressed"|"unknown_trap"|"unknown_source"
                        |"rate_limited"|"error",
                   "alert_id"?: int, "dedup_key"?: str, "reason": str}
        """
        varbinds = varbinds or []

        rule = self._matcher.match(trap_oid)
        if rule is None:
            logger.warning(
                "[trapd] 未知 trap（不产生告警，请据此补规则）: source=%s version=%s "
                "oid=%s varbinds=%s",
                source_ip, snmp_version, trap_oid,
                sanitize_varbinds(varbinds),
            )
            return {"action": "unknown_trap", "reason": f"未匹配规则的 OID {trap_oid}"}

        device = self.resolve_device(source_ip)
        if device is None:
            logger.warning(
                "[trapd] 来源 IP 未关联到设备（不产生告警）: source=%s oid=%s rule=%s",
                source_ip, trap_oid, rule["name"],
            )
            return {"action": "unknown_source", "reason": f"IP {source_ip} 无对应设备"}

        if self._limiter is not None and not self._limiter.allow():
            logger.warning(
                "[trapd] 触发全局限流，trap 被拒收: source=%s rule=%s oid=%s",
                source_ip, rule["name"], trap_oid,
            )
            return {"action": "rate_limited", "reason": "超过全局 trap 速率上限"}

        return self._raise_alert(device, rule, source_ip, snmp_version, varbinds)


    def _raise_alert(self, device, rule: dict[str, Any], source_ip: str,
                     snmp_version: str, varbinds: list[tuple[str, Any]]) -> dict[str, Any]:
        import json as _json

        from app.models.monitor_alert_outbox import MonitorAlertOutbox
        from app.services.monitoring.alert_ingress import (
            build_dedup_key,
            build_notification_key,
            governance_should_emit,
            publish_monitor_alert_event,
        )
        from app.services.monitoring.alert_suppression_service import get_throttle_seconds

        device_id = device.id
        index = self._matcher.extract_index(rule, varbinds)
        iface = (
            if_mib.extract_interface(varbinds, index)
            if if_mib.is_if_index_rule(rule.get("index_varbind"))
            else {}
        )
        stored_varbinds = sanitize_varbinds(varbinds)

        device_name = getattr(device, "device_name", None) or f"设备{device_id}"

        severity = rule["severity"]
        title_template = rule.get("title") or rule["name"]
        if iface.get("admin_down"):
            severity = "info"
            title_template = "端口 {port} 被关闭"

        render_ctx = {
            "port": iface.get("name") or (f"#{index}" if index else "未知端口"),
            "index": index or "-",
            "device": device_name,
        }
        title = f"{device_name} {render_text(title_template, render_ctx)}"
        content = self._build_content(rule, iface, index, source_ip, snmp_version)

        alert_type = trap_alert_type(rule["name"])
        idem_key = build_dedup_key(alert_type, device_id, rule["name"], index, "raise")
        notif_key = build_notification_key(
            idem_key, bucket_seconds=get_throttle_seconds()
        )

        payload = {
            "type": alert_type,
            "severity": severity,
            "title": title,
            "content": content,
            "payload": {
                "device_id": device_id,
                "device_name": device_name,
                "trap_rule": rule["name"],
                "trap_oid": rule["match_oid"],
                "index": index,
                "port_name": iface.get("name"),
                "port_alias": iface.get("alias"),
                "oper_status": iface.get("oper_status"),
                "shutdown": self._shutdown_flag(iface),
                "source_ip": source_ip,
                "snmp_version": snmp_version,
                "varbinds": stored_varbinds[:20],
            },
            "source_module": "trapd",
            "target_type": "device",
            "target_id": device_id,
            "idempotency_key": notif_key,
            "allow_broadcast": True,
        }

        should_emit, aggregated, suppressed_count = governance_should_emit(
            device_id, alert_type, idem_key, severity=severity,
        )
        if not should_emit:
            logger.info(
                "[trapd] 告警被治理门面抑制: device=%s rule=%s key=%s",
                device_id, rule["name"], idem_key,
            )
            return {"action": "suppressed", "dedup_key": idem_key,
                    "reason": "被静默/抑制窗口拦截"}
        if aggregated:
            payload = dict(payload)
            payload["suppressed_count"] = suppressed_count

        new_row = MonitorAlertOutbox(
            device_id=device_id,
            alert_type=alert_type,
            severity=severity,
            dedup_key=idem_key,
            payload_json=_json.dumps(payload, ensure_ascii=False),
        )
        from extensions import db
        db.session.add(new_row)
        db.session.flush()

        try:
            publish_monitor_alert_event(
                device_id, alert_type, severity, idem_key,
                new_row.id, payload,
            )
        except Exception:
            logger.warning("[trapd] SSE 发布失败 device_id=%s rule=%s",
                           device_id, rule["name"], exc_info=True)

        try:
            from app.services.monitoring.incident_aggregator import aggregate_alert
            aggregate_alert(device_id, alert_type, severity,
                            outbox_id=new_row.id)
        except Exception:
            logger.warning("[trapd] 事件聚合失败 device_id=%s", device_id, exc_info=True)

        alert_id = new_row.id
        db.session.commit()
        logger.info(
            "[trapd] 告警入箱: alert_id=%s device=%s(%s) type=%s port=%s index=%s key=%s",
            alert_id, device_name, source_ip, alert_type, iface.get("name"),
            index, idem_key,
        )
        return {"action": "alerted", "alert_id": alert_id, "dedup_key": idem_key}

    @staticmethod
    def _shutdown_flag(iface: dict[str, Any]) -> Optional[bool]:
        """``payload["shutdown"]`` 的取值：只在**报文真带了** ifAdminStatus 列时给布尔。

        拿不到的（非 IF-MIB 规则、或该条报文没带该列）返回 None —— 与
        ``alert_port_view`` 的同一取值口径对齐，前端据此显示"未知"而不是
        "非人为关闭"。缺列时压成 False 是在**没有证据的情况下下确诊结论**：
        False 是"确认不是运维关的"，None 才是"不知道"。
        """
        if iface.get("admin_status") is None:
            return None
        return bool(iface.get("admin_down"))

    @staticmethod
    def _build_content(rule: dict[str, Any], iface: dict[str, Any],
                       index: Optional[str], source_ip: str,
                       snmp_version: str) -> str:
        """拼告警正文：规则文案 + 端口定位 + 接口状态 + 来源。

        正文的职责是"点进详情后能定位到具体端口与现场参数"，标题只负责扫读。
        端口名拿不到时**退回显示 ifIndex**（``实例: 10``）而不是编一个名字 ——
        ifIndex 是设备上真实存在的标识，运维可以用它去设备侧查，猜的名字不能。
        """
        lines = [rule.get("content") or ""]
        port_name = iface.get("name")
        if port_name:
            locator = f"端口: {port_name}"
            if index:
                locator += f"（ifIndex={index}）"
            lines.append(locator)
        elif index:
            lines.append(f"实例: {index}")
        if iface.get("alias"):
            lines.append(f"端口备注: {iface['alias']}")
        if iface.get("admin_status") or iface.get("oper_status"):
            admin = iface.get("admin_status") or "-"
            oper = iface.get("oper_status") or "-"
            lines.append(f"接口状态: 管理={admin}, 运行={oper}")
        lines.append(f"来源: {source_ip}（{snmp_version}）")
        return "\n".join(line for line in lines if line)
