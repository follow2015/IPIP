# -*- coding: utf-8 -*-
"""设备健康监控状态机

显式状态机 + 适配器分流 + 告警目标解析。

核心职责：
- 根据 device_type 选择监控协议（SNMP / Redfish / IPMI），按凭据可用情况分流；
- 消费适配器探测结果（ProbeResult），维护「可达性状态机」快照并落库；
- 基于连续失败阈值做抖动抑制 + 去重告警（episode 递增使幂等键不撞）；
- 解析告警目标（责任人 user / 兜底角色 role）并投递通知。
"""
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import threading
import time
from typing import Optional, Tuple

from flask import current_app

from app.utils.logging import get_logger
from app.core.enums import MonitorProtocolCode, NotificationTypeCode, ProbeErrorCode
from app.services.monitoring.adapters.base_adapter import (
    MonitorAdapter,
    ProbeResult,
    resolve_host_with_timeout,
    _is_ip_address,
    monitor_timeout_seconds,
)
from app.services.monitoring.protocol_registry import (
    device_type_to_protocols,
    protocol_requires_credential,
)
from app.services.notification_service import notification_service
from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository
from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
from app.persistence.monitor_timeseries_repository import MonitorTimeseriesRepository
from app.utils.transactional import transactional


logger = get_logger(__name__)


_BATCH_EXECUTORS: set = set()
_BATCH_EXECUTORS_LOCK = threading.Lock()
_atexit_registered = False


def _register_batch_executor(executor):
    """登记线程池并（首次）注册 atexit 统一 shutdown。"""
    global _atexit_registered
    with _BATCH_EXECUTORS_LOCK:
        _BATCH_EXECUTORS.add(executor)
        if not _atexit_registered:
            import atexit

            atexit.register(shutdown_batch_executors)
            _atexit_registered = True


def shutdown_batch_executors():
    """关闭全部已登记的批量探测线程池（幂等）。

    进程退出由 atexit 调用；测试亦可显式调用以回收常驻线程。
    """
    with _BATCH_EXECUTORS_LOCK:
        executors = list(_BATCH_EXECUTORS)
        _BATCH_EXECUTORS.clear()
    for ex in executors:
        try:
            ex.shutdown(wait=False)
        except Exception:  # noqa: BLE001 - 退出路径不应抛出
            pass

_ROLE_ACTIVE_USER_CACHE: dict = {}
_ROLE_ACTIVE_USER_TTL = 300  # 5 分钟
_ROLE_ACTIVE_USER_CACHE_LOCK = threading.Lock()

CONFIG_ERROR_CODES = frozenset({
    "no_host_ref",
    "no_api_url",
    "host_not_in_zabbix",
    "zabbix_empty_host_list",
})


@dataclass(frozen=True)
class AlertTarget:
    """告警目标解析结果（替代 5-tuple，消除魔数索引访问）。"""
    target_type: str        # "user" 或 "role"
    target_id: object      # User 对象或角色名 str
    channels: tuple        # 通知渠道，如 ("inbox", "wechat_work", "feishu")
    allow_broadcast: bool  # 是否允许外部广播渠道
    has_recipient: bool    # 是否存在有效接收人（False = 告警盲区）


@dataclass(frozen=True)
class _MonitorTransition:
    """可达性状态机的纯计算结果（无副作用，便于单测聚焦状态机本身）。

    由 ``_compute_monitor_transition`` 产出，``apply_result`` 据此落库 + 告警。
    """

    reachable: bool
    failures: int
    ever_reachable: bool
    became_down: bool
    recovered: bool
    re_alert_due: bool
    down_alerted: bool
    episode: int
    alert_action: str  # "unreachable" / "recovered" / ""（无告警）


def _compute_monitor_transition(
    *,
    reachable: bool,
    threshold: int,
    re_alert_interval: timedelta,
    now: datetime,
    old_failures: int,
    old_ever: bool,
    old_down_alerted: bool,
    old_episode: int,
    last_alerted_at: Optional[str],
) -> _MonitorTransition:
    """根据旧快照 + 本轮探测，计算可达性状态机的下一步（S1：状态机显式化）。

    基于持久化的 flag（不做 DB 列迁移）推导：
    - failures：可达归零，不可达则 +1；
    - became_down：不可达且达阈值且此前未告警 → 新不可达周期（episode+1）；
    - recovered：恢复可达且此前处于已告警周期 → 关闭周期；
    - re_alert_due：已告警的不可达周期内持续失败、距上次告警超阈值 → 周期重告警
      （同 episode，含盲区场景避免永久沉默）；last_alerted_at 缺失/非法也判为到期。
    返回 alert_action 供 apply_result 分支投递，避免重复判定。
    """
    failures = 0 if reachable else old_failures + 1
    ever_reachable = old_ever or reachable

    became_down = (not reachable) and (failures >= threshold) and (not old_down_alerted)
    recovered = reachable and old_down_alerted

    re_alert_due = False
    if (not reachable) and (failures >= threshold) and old_down_alerted:
        if last_alerted_at is None:
            re_alert_due = True
        else:
            try:
                if isinstance(last_alerted_at, datetime):
                    ts = last_alerted_at
                else:
                    ts = datetime.fromisoformat(str(last_alerted_at))
                if ts.tzinfo is None and now.tzinfo is not None:
                    ts = ts.replace(tzinfo=now.tzinfo)
                re_alert_due = (now - ts) >= re_alert_interval
            except (ValueError, TypeError):
                re_alert_due = True

    if became_down:
        down_alerted = True
        episode = old_episode + 1
    elif recovered:
        down_alerted = False
        episode = old_episode
    else:
        down_alerted = old_down_alerted
        episode = old_episode

    if became_down or re_alert_due:
        alert_action = "unreachable"
    elif recovered:
        alert_action = "recovered"
    else:
        alert_action = ""

    return _MonitorTransition(
        reachable=reachable,
        failures=failures,
        ever_reachable=ever_reachable,
        became_down=became_down,
        recovered=recovered,
        re_alert_due=re_alert_due,
        down_alerted=down_alerted,
        episode=episode,
        alert_action=alert_action,
    )


class MonitorService:
    """设备健康监控服务（状态机 + 告警投递）"""

    def __init__(
        self,
        snmp_adapter,
        ipmi_adapter,
        zabbix_adapter,
        ping_adapter,
        credential_service,
        status_repo: DeviceMonitorStatusRepository,
        credential_repo=None,
        device_repo=None,
        notify=None,
        template_repo=None,
    ):
        self.snmp_adapter = snmp_adapter
        self.ipmi_adapter = ipmi_adapter
        self.zabbix_adapter = zabbix_adapter
        self.ping_adapter = ping_adapter
        self.credential_service = credential_service
        self.status_repo = status_repo
        if credential_repo is None:
            from app.persistence.monitor_credential_repository import MonitorCredentialRepository
            credential_repo = MonitorCredentialRepository()
        if device_repo is None:
            from app.persistence.device_repository import DeviceRepository
            device_repo = DeviceRepository()
        if template_repo is None:
            from app.persistence.monitor_metric_template_repository import (
                MonitorMetricTemplateRepository,
            )
            template_repo = MonitorMetricTemplateRepository()
        self._credential_repo = credential_repo
        self._device_repo = device_repo
        self._template_repo = template_repo
        self._tpl_cache: dict = {}
        self.notify = notify or notification_service
        self._adapters = {
            MonitorProtocolCode.SNMP.value: snmp_adapter,
            MonitorProtocolCode.IPMI.value: ipmi_adapter,
            MonitorProtocolCode.ZABBIX.value: zabbix_adapter,
            MonitorProtocolCode.PING.value: ping_adapter,
        }


    def _cfg(self, name: str, default, session=None):
        """运行时配置读取：优先动态配置（Redis/DB），miss 则回退 current_app.config。

        动态配置经 MonitorDynamicConfig 在线修改并热重载，无需重启即可生效。
        `session`：可选注入 Session（每任务独立 Session 场景），透传给动态配置 DB
        回退读，避免与调用方独立事务争用 StaticPool 单连接。
        """
        from app.services.monitoring.dynamic_config import MonitorDynamicConfig

        val = MonitorDynamicConfig.get(name, session=session)
        if val is not None:
            return val
        return current_app.config.get(name, default)

    def _now(self) -> datetime:
        """统一时间戳，apply_result 内只算一次，复用到三个时间字段。"""
        return datetime.now(timezone.utc)

    _CFG_KEYS = (
        "MONITOR_CONSECUTIVE_FAILURES_THRESHOLD",
        "MONITOR_REALERT_INTERVAL_MINUTES",
        "MONITOR_FALLBACK_ROLE",
        "MONITOR_BLINDSPOT_ROLE",
    )
    _CFG_DEFAULTS = {
        "MONITOR_CONSECUTIVE_FAILURES_THRESHOLD": 2,
        "MONITOR_REALERT_INTERVAL_MINUTES": 360,
        "MONITOR_FALLBACK_ROLE": "admin",
        "MONITOR_BLINDSPOT_ROLE": "admin",
    }

    def _batch_cfg(self, session=None) -> tuple:
        """批量预读 4 个监控配置项（单次 HGETALL 替代 4 次 HGET）。

        返回 (threshold, re_alert, fallback_role, blindspot_role)。
        """
        from app.services.monitoring.dynamic_config import MonitorDynamicConfig
        batch = MonitorDynamicConfig.get_batch(list(self._CFG_KEYS), session=session)
        vals = []
        for k in self._CFG_KEYS:
            v = batch.get(k)
            if v is None:
                v = current_app.config.get(k, self._CFG_DEFAULTS[k])
            vals.append(v)
        return tuple(vals)


    def _candidate_protocols(self, device) -> list:
        """按设备类型给出候选协议顺序（由协议注册表驱动，OCP）。

        注册表 `device_type_to_protocols` 维护 device_type → 协议顺序映射，
        新增协议只需在注册表加一条 `ProtocolSpec`，此处无需改动。
        """
        device_type = getattr(device, "device_type", None)
        return device_type_to_protocols(device_type)

    def get_monitored_device_ids(self, protocols: list) -> list:
        """返回启用且协议匹配的去重 device_id 列表（供 worker 轮询）。

        - 协议全为需凭据协议（snmp/ipmi/zabbix）：经关联表查持有对应协议凭据的设备；
        - 含无凭据协议（ping）：查所有开启设备级监控开关的设备（不依赖凭据关联表）。
        monitor_enabled_only=True：只纳入「设备级开关开启」或「尚未首探（无状态行
        视为默认启用）」的设备，跳过被用户暂停监控的设备。
        """
        if protocols and all(not protocol_requires_credential(p) for p in protocols):
            return self._credential_repo.find_enabled_device_ids_all(
                monitor_enabled_only=True
            )
        return self._credential_repo.find_enabled_device_ids(
            protocols, monitor_enabled_only=True
        )

    def _select_adapter(self, device):
        """按 device_type 分流，并依据凭据可用情况选定真正可用的适配器。

        返回 (adapter, cred)；若所有候选协议均不可用，返回 None
        （check_device 应直接 return，不落库、不告警）。

        - 需凭据协议（snmp/ipmi/zabbix）：须设备持有该协议凭据才可用；
        - 无凭据协议（ping）：始终可用（复用 ip_status_service），cred=None。
        """
        for protocol in self._candidate_protocols(device):
            adapter = self._adapters.get(protocol)
            if adapter is None:
                continue
            if not protocol_requires_credential(protocol):
                return adapter, None
            cred = self.credential_service.get_decrypted(device.id, protocol)
            if cred is not None:
                return adapter, cred
        return None


    def check_device(self, device) -> None:
        """探测单个设备并落库 + 告警。

        探测在事务外执行（避免网络 I/O 占用 DB 连接），
        仅落库 + 告警阶段在 @transactional 内完成。
        """
        selected = self.probe_device(device)
        if selected is None:
            return
        result, protocol = selected
        if getattr(result, "skipped", False):
            return
        threshold, re_alert, fallback_role, blindspot_role = self._batch_cfg()
        self._persist(
            device, result, protocol,
            threshold=threshold, re_alert_interval_minutes=re_alert,
            fallback_role=fallback_role, blindspot_role=blindspot_role,
        )

    def check_device_in_session(self, device, session) -> None:
        """每任务独立 Session 变体（供独立 async 微服务使用）。

        **本方法负责调用方传入 session 的最终 commit**（见方法末尾 `session.commit()`，
        P18）：落库 + 入箱均在本方法内以未提交状态写入，统一在末尾提交，保证状态快照与
        待发告警原子提交。调用方只需提供 session 并负责其关闭，无需自行 commit。

        与 `check_device` 的区别：
        - 探测（网络 I/O）同样在事务/session 之外执行，绝不持有 DB 连接跨网络 I/O；
        - 读旧快照 / 写新状态 / 告警全部走**调用方传入的独立 Session**，
          本方法内部不提交，仅执行落库写操作，由调用方显式 `session.commit()`，
          从而解耦 Flask scoped session，避免跨线程 / 跨协程污染，并修掉 Zabbix
          会放大的「在 @transactional 内占用 DB 连接」问题。
        - 告警路径（`notification_service.notify`）仍走其自身独立 session，自行提交。

        一致性窗口（已由 outbox 模式消除）：
        apply_result 内部顺序为 upsert(未提交) → 入箱(未提交) → 返回 →
        session.commit()（状态快照 + 待发告警原子提交）。告警投递由独立进程内
        MonitorOutboxSender 轮询完成，不再在事务内同步直发，故不再存在「告警已发
        但状态回滚」或「状态已提交但告警丢失」的窗口。发件器提供至少一次投递，
        notify 的 idempotency_key 幂等去重保证不会重复通知。

        调用契约（由 `StandaloneMonitorService.check_one` 保证）：
        1. 必须在 **Flask 应用上下文内** 调用——`apply_result` 经 `_cfg()` 读取
           `current_app.config`（如 `MONITOR_CONSECUTIVE_FAILURES_THRESHOLD`），
           离开 app context 会抛 `RuntimeError`；
        2. `session` 须为调用方创建的独立 Session（非 Flask scoped session），调用方
           负责其 `commit()` 与最终关闭；
        3. 适配 asyncio 的 `run_in_executor` 线程执行模型——网络 I/O 阶段不持有任何
           DB 连接，仅落库 / 告警阶段短暂使用传入 session。
        """
        selected = self.probe_device(device)
        if selected is None:
            return
        result, protocol = selected
        if getattr(result, "skipped", False):
            return
        threshold, re_alert, fallback_role, blindspot_role = self._batch_cfg(session=session)
        per_task_repo = DeviceMonitorStatusRepository(session=session)
        self.apply_result(
            device, result, protocol, status_repo=per_task_repo,
            threshold=threshold, re_alert_interval_minutes=re_alert,
            fallback_role=fallback_role, blindspot_role=blindspot_role,
        )
        session.commit()

    @transactional
    def _persist(self, device, result, protocol, threshold=None,
                 re_alert_interval_minutes=None, fallback_role=None,
                 blindspot_role=None) -> None:
        """落库 + 入箱（在 @transactional 内执行）。

        后台 worker 线程不在 API 请求上下文内，没有 API 层 @transactional 收口，
        必须在 Service 层自行管理事务提交。告警投递由进程内发件轮询器异步完成。
        threshold/re_alert/fallback/blindspot 由事务外预读后传入，避免事务内
        触发动态配置 Redis I/O。
        """
        self.apply_result(
            device, result, protocol,
            threshold=threshold, re_alert_interval_minutes=re_alert_interval_minutes,
            fallback_role=fallback_role, blindspot_role=blindspot_role,
        )

    def probe_device(self, device) -> Optional[tuple[ProbeResult, str]]:
        """仅探测、不落库、不告警。

        供 Task 8 的手动 POST /check 在【事务外】调用：
        - 复用 `_select_adapter(device)` 分流选适配器 + 取凭据；
        - 若设备无可用凭据（`_select_adapter` 返回 None）则直接返回 None；
        - 否则 `result = adapter.probe(device, cred)`，返回 `(result, protocol.value)`。

        与 `check_device` 的区别：本方法不做 apply_result（落库 + 告警），
        把落库动作交给调用方在 @transactional 内完成。

        H2 防泄漏：对非 IP 的连接目标先做带超时 DNS 预解析；若解析
        超时/失败，返回 ``skipped=True`` 的 ProbeResult，交由上层跳过本轮探测，
        避免 hostname 场景 DNS 挂死进入协议适配器线程后 daemon 线程被遗弃造成泄漏。
        IPMI 协议优先使用 ipmi_address（真正的 BMC 地址），其余协议使用 management_ip。
        """
        selected = self._select_adapter(device)
        if selected is None:
            return None
        adapter, cred = selected
        host = MonitorAdapter.resolve_target_ip(device)
        if host and not _is_ip_address(host):
            resolved = resolve_host_with_timeout(host, monitor_timeout_seconds())
            if resolved is None:
                logger.warning(
                    "设备 %s 的连接目标 %s DNS 预解析失败（超时/不可解析），"
                    "跳过本轮探测，不视为设备不可达",
                    getattr(device, "id", None), host,
                )
                return ProbeResult(
                    reachable=False, error=ProbeErrorCode.DNS_RESOLVE_TIMEOUT.value, skipped=True
                ), adapter.protocol.value
        result = adapter.probe(device, cred)
        return result, adapter.protocol.value

    def probe_and_persist(self, device) -> Optional[tuple[ProbeResult, str]]:
        """手动探测 + 落库 + 告警的统一入口（I2：route handler 不再调 _cfg 私有方法）。

        在事务外调用：先 probe_device（网络 I/O），再读取运行时配置并 apply_result。
        返回 (result, protocol) 或 None（设备未配置凭据）。
        """
        probed = self.probe_device(device)
        if probed is None:
            return None
        result, protocol = probed
        if getattr(result, "skipped", False):
            return result, protocol
        threshold = self._cfg("MONITOR_CONSECUTIVE_FAILURES_THRESHOLD", 2)
        re_alert = self._cfg("MONITOR_REALERT_INTERVAL_MINUTES", 360)
        fallback_role = self._cfg("MONITOR_FALLBACK_ROLE", "admin")
        blindspot_role = self._cfg("MONITOR_BLINDSPOT_ROLE", "admin")
        self.apply_result(
            device, result, protocol,
            threshold=threshold, re_alert_interval_minutes=re_alert,
            fallback_role=fallback_role, blindspot_role=blindspot_role,
        )
        return result, protocol

    def check_probe_cooldown(self, device_id: int) -> bool:
        """per-device 探测冷却限流（Redis SET NX EX）。

        I1：route handler 不再直接访问 Redis / 调 service 私有方法。
        返回 True 表示可探测，False 表示冷却中。Redis 不可用时 fail-open。
        """
        try:
            from flask import current_app
            from app.services.monitoring.dynamic_config import MonitorDynamicConfig
            r = MonitorDynamicConfig._redis(current_app)
            if r is None:
                return True
            cooldown = current_app.config.get("MONITOR_PROBE_COOLDOWN_SECONDS", 30)
            key = f"monitor:probe:cooldown:{device_id}"
            return bool(r.set(key, "1", nx=True, ex=int(cooldown)))
        except Exception:
            logger.warning("探测冷却限流检查失败（降级为不限流） device_id=%s", device_id, exc_info=True)
            return True

    def check_batch(self, device_ids: list[int]) -> dict:
        """批量手动探测（C3：route handler 不再管理 session 生命周期 / ThreadPoolExecutor）。

        返回 {"results": list[dict], "skipped": list[int]}。
        每台设备独立 Session（避免并发污染 scoped_session），线程池复用实例级 _batch_executor。
        """
        from concurrent.futures import ThreadPoolExecutor
        from flask import current_app
        from sqlalchemy.orm import sessionmaker
        from extensions import db
        from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository

        targets, skipped = [], []
        for did in device_ids:
            if not self.check_probe_cooldown(did):
                skipped.append(did)
                continue
            device = self._device_repo.find_by_id(did)
            if not device:
                skipped.append(did)
                continue
            _ = device.hardware  # 触发 lazy load（请求线程内，安全）
            _ = getattr(device.hardware, "ipmi_address", None) if device.hardware else None
            targets.append(device)

        if not targets:
            return {"results": [], "skipped": skipped}

        for d in targets:
            db.session.expunge(d)

        app = current_app._get_current_object()
        Session = sessionmaker(bind=db.engine, expire_on_commit=False)

        def _check_one(device):
            with app.app_context():
                with Session() as session:
                    per_task_status_repo = DeviceMonitorStatusRepository(session=session)
                    selected = self.probe_device(device)
                    if selected is None:
                        return {
                            "device_id": device.id,
                            "reachable": None,
                            "latency_ms": None,
                            "extra": None,
                            "error": "no_credential",
                        }
                    result, protocol = selected
                    if getattr(result, "skipped", False):
                        return {
                            "device_id": device.id,
                            "reachable": None,
                            "latency_ms": None,
                            "extra": result.extra,
                            "error": result.error,
                        }
                    self.apply_result(
                        device, result, protocol, status_repo=per_task_status_repo,
                    )
                    session.commit()
                    return {
                        "device_id": device.id,
                        "reachable": result.reachable,
                        "latency_ms": result.latency_ms,
                        "extra": result.extra,
                        "error": result.error,
                    }

        pool_size = current_app.config.get("MONITOR_BATCH_POOL_SIZE", 10)
        if not hasattr(self, "_batch_executor") or self._batch_executor is None:
            self._batch_executor = ThreadPoolExecutor(
                max_workers=pool_size, thread_name_prefix="monitor-batch"
            )
            _register_batch_executor(self._batch_executor)
        results = list(self._batch_executor.map(_check_one, targets))
        return {"results": results, "skipped": skipped}

    def collect_device_metrics(self, device) -> dict:
        """对设备做业务指标采集（连通性之外的指标，供 worker 探测后调用）。

        复用 ``_select_adapter`` 选适配器 + 凭据，经 ``MetricCollector`` 按启用
        指标模板采集并做阈值评估。返回 ``{metric_key: {index: {...}}}``；
        适配器无 ``collect_metrics`` 能力（如 Zabbix/Ping）或无可采集指标时返回空。

        不抛异常：采集失败以空结果静默降级，避免影响主探测流程。
        """
        selected = self._select_adapter(device)
        if selected is None:
            return {}
        adapter, cred = selected
        if not hasattr(adapter, "collect_metrics"):
            return {}
        try:
            from app.services.monitoring.metric_collector import MetricCollector

            collector = MetricCollector(self._template_repo, _tpl_cache=self._tpl_cache)
            return collector.collect(device, adapter, cred)
        except Exception:  # noqa: BLE001 - 采集失败静默降级，不中断主探测
            logger.warning(
                "设备 %s 指标采集失败（已降级跳过）",
                getattr(device, "id", None),
                exc_info=True,
            )
            return {}

    def get_device_status(self, device_id: int) -> dict:
        """查询设备监控状态（供 API 层调用，避免路由层直接访问 Repository）。

        Returns:
            dict: {"monitored": bool, "configured_protocols": [str], "status": dict|None}
        """
        self._device_repo.find_by_id_or_404(device_id)  # 设备缺失即 404
        creds = self._credential_repo.find_enabled_protocols(device_id)
        status = self.status_repo.find_by_device(device_id)

        credential_links = []
        for protocol in creds:
            linked = self._credential_repo.find_enabled(device_id, protocol)
            if linked is not None:
                credential_links.append(
                    {"protocol": protocol, "credential_id": linked.id, "name": linked.name}
                )

        return {
            "monitored": bool(creds),
            "configured_protocols": creds,
            "credentials": credential_links,
            "status": status.to_dict() if status else None,
        }

    def get_device_status_with_alerts(self, device_id: int) -> dict:
        """查询设备监控状态 + 指标告警聚合（I13：route handler 不再做业务聚合）。

        返回 get_device_status 的字段 + active_metric_alerts / max_alert_severity /
        monitor_interrupted。
        """
        from app.persistence.device_metric_alert_state_repository import (
            DeviceMetricAlertStateRepository,
        )
        data = self.get_device_status(device_id)
        alert_state_repo = DeviceMetricAlertStateRepository()
        alert_agg = alert_state_repo.active_alerts_by_device().get(device_id, {})
        data["active_metric_alerts"] = alert_agg.get("alert_count", 0)
        data["max_alert_severity"] = alert_agg.get("max_severity", 0)
        data["monitor_interrupted"] = device_id in alert_state_repo.interrupted_device_ids()
        return data

    def get_devices_monitor_summary(self, device_ids: list) -> dict:
        """批量查询设备监控摘要（供设备列表 API 注入，避免 N+1）。

        分两类信号：
        - ping_reachable：ping 轮询的管理 IP 连通性（从 extra.ping_reachable 读，
          None=未 ping 过）。ping 无需凭据，对所有启用设备兜底探测。
        - monitor_*：snmp/zabbix/ipmi 凭据协议的探测结果 + 指标告警。
          仅当设备持有这些凭据且状态行 protocol 为其中之一时才有值。

        Args:
            device_ids: 设备 ID 列表

        Returns:
            {device_id: {
                ping_reachable: bool | null,
                has_monitor_credential: bool,
                monitor_reachable: bool | null,
                monitor_protocol: str | null,
                active_metric_alerts: int,
                max_alert_severity: int,
                monitor_interrupted: bool,
            }}
            完全无监控数据（无状态行 + 无凭据 + 无告警）的设备不在返回字典中。
        """
        if not device_ids:
            return {}
        from app.persistence.device_metric_alert_state_repository import (
            DeviceMetricAlertStateRepository,
        )

        status_map = self.status_repo.find_by_device_ids(device_ids)
        monitor_cred_ids = set(
            self._credential_repo.find_enabled_device_ids(
                protocols=["snmp", "zabbix", "ipmi"]
            )
        )
        alert_state_repo = DeviceMetricAlertStateRepository()
        alert_agg = alert_state_repo.active_alerts_by_device()
        interrupted_ids = alert_state_repo.interrupted_device_ids()

        monitor_protocols = {"snmp", "zabbix", "ipmi"}
        result: Dict[int, dict] = {}
        for did in device_ids:
            status = status_map.get(did)
            has_cred = did in monitor_cred_ids
            agg = alert_agg.get(did, {})
            interrupted = did in interrupted_ids

            ping_reachable = None
            if status and status.extra:
                ping_reachable = status.extra.get("ping_reachable")

            monitor_reachable = None
            monitor_protocol = None
            if status and status.protocol in monitor_protocols:
                monitor_reachable = bool(status.reachable)
                monitor_protocol = status.protocol

            if (
                status is None
                and not has_cred
                and not agg
                and not interrupted
            ):
                continue

            result[did] = {
                "ping_reachable": ping_reachable,
                "has_monitor_credential": has_cred,
                "monitor_reachable": monitor_reachable,
                "monitor_protocol": monitor_protocol,
                "active_metric_alerts": agg.get("alert_count", 0),
                "max_alert_severity": agg.get("max_severity", 0),
                "monitor_interrupted": interrupted,
            }
        return result

    def get_device_metric_dashboard(self, device_id: int) -> dict:
        """设备监控数据聚合（GET /monitor/devices/<id>/metric-dashboard）。

        供前端「监控数据」卡片的下半部分展示设备监控指标状态。

        指标内容来源（优先级，KISS）：
        1. 设备显式关联的模板组（``device.metric_template_group_id``）中的模板指标；
        2. 未显式关联时，按 ``device_type + brand + 已配置协议`` 自动匹配启用模板组；
        3. 未命中模板组或组内无模板 → ``grouped=False``，前端沿用默认 METRIC_GROUPS。

        状态判定（前端据此渲染灰色卡片 + 状态标签）：
        - ``has_credential=False``：无凭据，前端整体提示「需要关联凭据」；
        - ``status is None``：已配置凭据但尚未首探 → ``not_probed``；
        - ``not reachable``：不可达 → ``unreachable``；
        - ``not reachable and last_error in CONFIG_ERROR_CODES``：凭据/配置错误 →
          ``credential_error``（区分于设备真实宕机）；
        - 命中模板组但 ``metric_status`` 为空 → ``no_data``；
        - 存在超阈值指标 → ``breached``；
        - 其余 → ``normal``。

        重要：当 overall_status 为 ``unreachable`` / ``credential_error`` / ``no_data``
        / ``not_probed`` / ``no_credential`` 时，``metric_status`` 返回空 list，
        前端在指标区域直接展示对应状态，不渲染历史 latest 值（避免误导）。

        Returns:
            dict: 包含 has_credential / has_zabbix / template_group / grouped /
                  metric_status / overall_status / status_reason / reachable /
                  last_error / last_checked_at。
        """
        device = self._device_repo.find_by_id_or_404(device_id)
        creds = self._credential_repo.find_enabled_protocols(device_id)
        has_credential = bool(creds)
        has_zabbix = "zabbix" in creds

        from app.services.monitoring.metric_template_group_service import (
            MetricTemplateGroupService,
        )
        group_service = MetricTemplateGroupService()
        template_group = None
        grouped = False
        group_templates = []
        if device.metric_template_group_id:
            template_group = group_service.get_group_detail(device.metric_template_group_id)
            if template_group and template_group.get("templates"):
                group_templates = template_group["templates"]
                grouped = True
        if not grouped:
            candidates = [p for p in creds if p != "ping"]
            for source in candidates:
                matched = self._find_matched_template_group(
                    device.device_type, source, device.brand
                )
                if matched:
                    detail = group_service.get_group_detail(matched["id"])
                    if detail and detail.get("templates"):
                        template_group = detail
                        group_templates = detail["templates"]
                        grouped = True
                    break

        status = self.status_repo.find_by_device(device_id)
        reachable = status.reachable if status else None
        last_error = status.last_error if status else None
        last_checked_at = status.last_checked_at.isoformat() if status and status.last_checked_at else None
        overall_status, status_reason = self._dashboard_overall_status(
            has_credential, status, grouped
        )

        actual_source = next(
            (p for p in ("snmp", "ipmi", "zabbix") if p in creds), None
        )
        metric_status = []
        if overall_status in ("normal", "breached"):
            from app.persistence.device_metric_latest_repository import (
                DeviceMetricLatestRepository,
            )
            latest_rows = DeviceMetricLatestRepository().find_by_device(device_id)
            latest_map: dict = {}  # metric_key -> 首个实例
            for row in latest_rows:
                if row.metric_key not in latest_map:
                    latest_map[row.metric_key] = row

            if grouped:
                seen_keys = {t.get("metric_key") for t in group_templates}
                display_templates = list(group_templates)
                try:
                    generic_tpls = self._template_repo.find_enabled_by_device_type(
                        getattr(device, "device_type", None) or "other", vendor=None
                    )
                    for t in generic_tpls:
                        if t.metric_key not in seen_keys and t.metric_key.startswith("if_"):
                            display_templates.append({
                                "metric_key": t.metric_key,
                                "display_name": t.display_name,
                                "source": t.source,
                            })
                            seen_keys.add(t.metric_key)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "dashboard 合并通用 if_* 模板失败 device_id=%s", device_id, exc_info=True
                    )
                for t in display_templates:
                    key = t.get("metric_key")
                    latest = latest_map.get(key)
                    metric_status.append(
                        {
                            "metric_key": key,
                            "metric_name": t.get("display_name") or key,
                            "source": actual_source or t.get("source"),
                            "value": latest.value if latest else None,
                            "severity": latest.severity if latest else None,
                            "breached": bool(latest.breached) if latest else False,
                            "collected_at": latest.collected_at.isoformat() if latest and latest.collected_at else None,
                        }
                    )
                if not metric_status:
                    overall_status, status_reason = "no_data", "模板组已命中但尚未采集到指标数据"
                elif any(m["breached"] for m in metric_status):
                    overall_status, status_reason = "breached", "存在超阈值指标，请关注"
            else:
                tpl_map: dict = {}
                try:
                    for t in self._template_repo.find_enabled_by_device_type(
                        getattr(device, "device_type", None) or "other"
                    ):
                        tpl_map[t.metric_key] = {
                            "display_name": t.display_name,
                        }
                except Exception:  # noqa: BLE001 - 模板查询失败降级为空映射
                    logger.warning(
                        "metric_status 模板映射查询失败 device_id=%s", device_id, exc_info=True
                    )
                for key, latest in latest_map.items():
                    tpl_meta = tpl_map.get(key, {})
                    metric_status.append(
                        {
                            "metric_key": key,
                            "metric_name": tpl_meta.get("display_name") or key,
                            "source": actual_source,
                            "value": latest.value,
                            "severity": latest.severity,
                            "breached": bool(latest.breached),
                            "collected_at": latest.collected_at.isoformat() if latest.collected_at else None,
                        }
                    )
                if any(m["breached"] for m in metric_status):
                    overall_status, status_reason = "breached", "存在超阈值指标，请关注"
                elif not metric_status:
                    overall_status, status_reason = "no_data", "尚未采集到指标数据"

        return {
            "device_id": device_id,
            "has_credential": has_credential,
            "has_zabbix": has_zabbix,
            "configured_protocols": creds,
            "template_group": template_group,
            "grouped": grouped,
            "metric_status": metric_status,
            "overall_status": overall_status,
            "status_reason": status_reason,
            "reachable": reachable,
            "last_error": last_error,
            "last_checked_at": last_checked_at,
        }

    def _find_matched_template_group(self, device_type: str, source: str, brand: str | None) -> dict | None:
        """按 device_type + brand + source 匹配启用模板组（自动匹配路径）。

        Returns:
            dict: 组信息（id/name）或 None。
        """
        from app.persistence.monitor_metric_template_group_repository import (
            MonitorMetricTemplateGroupRepository,
        )
        groups = MonitorMetricTemplateGroupRepository().find_enabled_by_device_type(
            device_type, source, vendor=brand
        )
        if not groups:
            return None
        group = groups[0]
        return {"id": group.id, "name": group.name}

    def _dashboard_overall_status(self, has_credential: bool, status, grouped: bool) -> tuple[str, str]:
        """聚合判定「监控数据」卡片整体状态。

        Returns:
            tuple: (overall_status, status_reason)
            overall_status: no_credential / not_probed / unreachable / credential_error
                            / no_data / breached / normal
            status_reason: 供前端展示的中文说明
        """
        if not has_credential:
            return "no_credential", "设备未关联任何监控凭据"
        if status is None:
            return "not_probed", "已配置凭据，等待首次探测"
        if not status.reachable:
            if status.last_error in CONFIG_ERROR_CODES:
                return "credential_error", "监控凭据或配置异常，指标无法采集"
            return "unreachable", "设备当前不可达，暂无指标数据"
        if not grouped:
            return "normal", "未命中模板组，按默认规则采集指标"
        return "normal", "指标采集正常"

    def set_device_monitor_enabled(self, device_id: int, enabled: bool) -> dict:
        """设备级监控启停（PATCH /monitor/devices/<id>/monitor-enabled）。

        - 设备不存在 → find_by_id_or_404 抛 404（由 @transactional 路由回滚后上浮）；
        - 已有状态行 → 原地更新 monitor_enabled；
        - 无状态行（尚未首探）→ 预置一行，仅记录用户偏好，其余非 NULL 必填项
          （protocol/reachable/last_checked_at）取合理默认值。首次真实探测的 upsert
          不触碰 monitor_enabled，故偏好被保留。

        返回 {"device_id": int, "monitor_enabled": bool}。
        事务边界由调用方（路由 @transactional）收口。
        """
        device = self._device_repo.find_by_id_or_404(device_id)  # 设备缺失即 404
        existing = self.status_repo.find_by_device(device_id)
        if existing is not None:
            existing.monitor_enabled = enabled
            self.status_repo.session.flush()
        else:
            candidates = self._candidate_protocols(device)
            protocol = candidates[0] if candidates else MonitorProtocolCode.SNMP
            self.status_repo.upsert(
                device_id=device_id,
                protocol=protocol,
                reachable=False,
                last_checked_at=datetime.now(timezone.utc),
                monitor_enabled=enabled,
            )
        return {"device_id": device_id, "monitor_enabled": enabled}

    def batch_set_monitor_enabled(self, device_ids: list[int], enabled: bool) -> dict:
        """批量设备级监控启停（PATCH /monitor/batch-monitor-enabled）。

        对每台设备调用 set_device_monitor_enabled 逻辑，跳过不存在的设备。
        返回 {"updated": int, "skipped": int}。
        事务边界由调用方（路由 @transactional）收口。
        """
        updated = 0
        skipped = 0
        device_map = self._device_repo.find_by_ids(list(device_ids))
        status_map = self.status_repo.find_by_device_ids(list(device_ids))
        for did in device_ids:
            device = device_map.get(did)
            if device is None:
                skipped += 1
                continue
            existing = status_map.get(did)
            if existing is not None:
                existing.monitor_enabled = enabled
                self.status_repo.session.flush()
            else:
                candidates = self._candidate_protocols(device)
                protocol = candidates[0] if candidates else MonitorProtocolCode.SNMP
                self.status_repo.upsert(
                    device_id=did,
                    protocol=protocol,
                    reachable=False,
                    last_checked_at=datetime.now(timezone.utc),
                    monitor_enabled=enabled,
                )
            updated += 1
        return {"updated": updated, "skipped": skipped}

    def _apply_config_error(self, device, result: ProbeResult, protocol: str,
                            repo, old, now) -> None:
        """L3：配置错误轻量落库——只更新 last_checked_at + last_error，冻结状态机。

        - 保留 consecutive_failures / down_alerted / ever_reachable / down_episode /
          各时间戳不变，避免「配置错误」污染设备不可达判定；
        - reachable 字段：有旧快照则保留旧值；新设备因 NOT NULL 约束回落到
          result.reachable（配置错误恒为 False），但不触发任何告警；
        - 不调用 _enqueue_alert（配置错误不是设备宕机，不该产生 critical 告警）。
        """
        repo.upsert(
            device_id=device.id,
            protocol=protocol,
            reachable=(old.reachable if old else bool(result.reachable)),
            ever_reachable=(old.ever_reachable if old else False),
            down_alerted=(old.down_alerted if old else False),
            down_episode=(old.down_episode if old else 0),
            consecutive_failures=(old.consecutive_failures if old else 0),
            latency_ms=result.latency_ms,
            extra={**((old.extra or {}) if old else {}), **(result.extra or {})},
            last_error=result.error,
            last_checked_at=now,
            last_reachable_at=(old.last_reachable_at if old else None),
            last_unreachable_at=(old.last_unreachable_at if old else None),
        )

    def apply_result(self, device, result: ProbeResult, protocol: str,
                     status_repo=None, threshold=None,
                     re_alert_interval_minutes=None, fallback_role=None,
                     blindspot_role=None) -> None:
        """读旧快照 → 算状态机 → upsert → 入箱。落库 + 入箱的唯一入口。

        告警不再同步直发：待发告警写入 monitor_alert_outbox（与状态 upsert 同一
        事务），由 MonitorOutboxSender 轮询投递，消除一致性窗口。

        Task 8 的手动探测路径会直接调用本方法，故签名必须稳定：
        (device, result, protocol)。`status_repo` 为可选注入（每任务独立 Session
        场景），缺省回落到 `self.status_repo`（@transactional 全局 scoped session）。
        threshold/re_alert/fallback/blindspot 由事务外预读后传入，避免事务内
        触发动态配置 Redis I/O；未传时向后兼容 fallback 到 _cfg()。
        """
        if getattr(result, "skipped", False):
            logger.warning(
                "探测被跳过（%s），不更新状态、不告警 device_id=%s",
                result.error, device.id,
            )
            return

        repo = status_repo or self.status_repo

        now = self._now()
        if threshold is None:
            threshold = self._cfg(
                "MONITOR_CONSECUTIVE_FAILURES_THRESHOLD", 2, session=repo.session
            )
        if re_alert_interval_minutes is None:
            re_alert_interval_minutes = self._cfg(
                "MONITOR_REALERT_INTERVAL_MINUTES", 360, session=repo.session
            )
        re_alert_interval = timedelta(minutes=re_alert_interval_minutes)

        old = repo.find_by_device(device.id)
        old_failures = old.consecutive_failures if old else 0
        old_ever = old.ever_reachable if old else False
        old_down_alerted = old.down_alerted if old else False
        old_episode = old.down_episode if old else 0
        old_extra = (old.extra or {}) if old else {}
        old_reachable_at = old.last_reachable_at if old else None
        old_unreachable_at = old.last_unreachable_at if old else None

        reachable = bool(result.reachable)

        if (not reachable) and result.error in CONFIG_ERROR_CODES:
            self._apply_config_error(device, result, protocol, repo, old, now)
            return

        tr = _compute_monitor_transition(
            reachable=reachable,
            threshold=threshold,
            re_alert_interval=re_alert_interval,
            now=now,
            old_failures=old_failures,
            old_ever=old_ever,
            old_down_alerted=old_down_alerted,
            old_episode=old_episode,
            last_alerted_at=old_extra.get("last_alerted_at"),
        )

        monitor_extra: dict = dict(old_extra)
        resolved = None

        if tr.became_down or tr.re_alert_due:
            resolved = self._resolve_alert_target(
                device, status_repo=repo,
                fallback_role=fallback_role, blindspot_role=blindspot_role,
            )
            has_recipient = resolved.has_recipient
            seq = 0 if tr.became_down else old_extra.get("re_alert_seq", 0) + 1
            monitor_extra["re_alert_seq"] = seq
            monitor_extra["last_alerted_at"] = now.isoformat()
            if not has_recipient:
                monitor_extra["alert_blindspot_at"] = now.isoformat()
            else:
                monitor_extra.pop("alert_blindspot_at", None)
        elif tr.recovered:
            monitor_extra.pop("alert_blindspot_at", None)
            monitor_extra["re_alert_seq"] = 0

        if protocol == MonitorProtocolCode.PING.value:
            monitor_extra["ping_reachable"] = bool(tr.reachable)

        fields = {
            "device_id": device.id,
            "protocol": protocol,
            "reachable": tr.reachable,
            "ever_reachable": tr.ever_reachable,
            "down_alerted": tr.down_alerted,
            "down_episode": tr.episode,
            "consecutive_failures": tr.failures,
            "latency_ms": result.latency_ms,
            "extra": {**(result.extra or {}), **monitor_extra},
            "last_error": result.error,
            "last_checked_at": now,
            "last_reachable_at": now if reachable else old_reachable_at,
            "last_unreachable_at": now if (not reachable) else old_unreachable_at,
        }

        repo.upsert(**fields)

        MonitorTimeseriesRepository(session=repo.session).add_event(
            device_id=device.id,
            protocol=protocol,
            reachable=tr.reachable,
            latency_ms=result.latency_ms,
            consecutive_failures=tr.failures,
            episode=tr.episode,
            is_alert=bool(tr.alert_action),
            error=result.error,
            extra={**(result.extra or {})},
            probed_at=now,
        )


        if tr.alert_action == "unreachable":
            self._enqueue_alert(
                device, NotificationTypeCode.DEVICE_UNREACHABLE, "critical", result, tr.episode, protocol,
                re_alert_seq=monitor_extra.get("re_alert_seq", 0), resolved=resolved,
                session=repo.session, now=now,
            )
        elif tr.alert_action == "recovered":
            self._enqueue_alert(
                device, NotificationTypeCode.DEVICE_RECOVERED, "info", result, tr.episode, protocol, 0,
                resolved=None, session=repo.session, now=now,
            )


    def _resolve_alert_target(self, device, status_repo=None,
                              fallback_role=None, blindspot_role=None) -> AlertTarget:
        """解析告警目标。

        - 责任人有值 → AlertTarget(target_type="user", ...)
        - 为空 → 先尝试兜底角色 MONITOR_FALLBACK_ROLE（默认 admin）；
          若该角色无活跃用户，再回退到盲区应急组 MONITOR_BLINDSPOT_ROLE；
          两者皆无活跃用户 → 真正的「告警盲区」，has_recipient=False，
          由 _alert / apply_result 记录 critical 日志 + 状态标记，避免关键告警静默丢失。
        - allow_broadcast：责任人缺失时为 False，不走企微/飞书等外部广播渠道。
        - `status_repo`：可选注入（每任务独立 Session 场景），用于查角色活跃用户。
        - fallback_role/blindspot_role 由事务外预读后传入，避免事务内触发
          动态配置 Redis I/O；未传时向后兼容 fallback 到 _cfg()。
        """
        responsible = getattr(device, "responsible_person", None)
        if responsible:
            return AlertTarget("user", responsible, ("inbox", "wechat_work", "feishu"), True, True)

        if fallback_role is None:
            fallback_role = self._cfg("MONITOR_FALLBACK_ROLE", "admin")
        if self._role_has_active_user(fallback_role, status_repo=status_repo):
            return AlertTarget("role", fallback_role, ("inbox",), False, True)

        if blindspot_role is None:
            blindspot_role = self._cfg("MONITOR_BLINDSPOT_ROLE", "admin")
        if blindspot_role != fallback_role and self._role_has_active_user(blindspot_role, status_repo=status_repo):
            logger.warning(
                "监控告警兜底角色 %s 无活跃用户，已回退到盲区应急组 %s (device_id=%s)",
                fallback_role, blindspot_role, getattr(device, "id", None),
            )
            return AlertTarget("role", blindspot_role, ("inbox",), False, True)

        logger.critical(
            "监控告警盲区：设备 %s 责任人缺失且兜底角色 %s / 盲区角色 %s 均无活跃用户，"
            "critical 告警将无法投递，请检查角色配置",
            getattr(device, "id", None), fallback_role, blindspot_role,
        )
        return AlertTarget("role", blindspot_role, ("inbox",), False, False)

    def _role_has_active_user(self, role_name: str, status_repo=None) -> bool:
        """兜底角色是否存在活跃（status==0）用户。

        P1 修复：加进程级 TTL 缓存（5 分钟），避免同批次 N 台设备宕机产生 N 次重复查询。
        """
        cached = _ROLE_ACTIVE_USER_CACHE.get(role_name)
        if cached is not None and cached[1] > time.monotonic():
            return cached[0]

        from app.models.user import User
        from app.models.rbac import Role, UserRole

        with _ROLE_ACTIVE_USER_CACHE_LOCK:
            cached = _ROLE_ACTIVE_USER_CACHE.get(role_name)
            if cached is not None and cached[1] > time.monotonic():
                return cached[0]

            session = (status_repo or self.status_repo).session
            result = (
                session.query(User)
                .join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .filter(Role.name == role_name, User.status == 0)
                .first()
                is not None
            )
            _ROLE_ACTIVE_USER_CACHE[role_name] = (result, time.monotonic() + _ROLE_ACTIVE_USER_TTL)
            return result

    def _build_alert_payload(self, device, alert_type: str, severity: str, result: ProbeResult,
                              episode: int, protocol: str, re_alert_seq: int = 0,
                              resolved=None, now=None) -> dict:
        """构造告警的 notify 参数字典（不发送，供入箱/测试复用）。

        source_module 按设备隔离冷却，idempotency_key 含 episode + re_alert_seq，
        使不同不可达周期（episode）及同一周期内的周期重告警（re_alert_seq>=1）
        互不幂等去重。target_type/target_id/channels/allow_broadcast 由 resolved
        （_resolve_alert_target 结果）决定；resolved 未传时内部解析一次。
        """
        if resolved is None:
            resolved = self._resolve_alert_target(device)
        target_type = resolved.target_type
        target_id = resolved.target_id
        channels = resolved.channels
        allow_broadcast = resolved.allow_broadcast

        metadata = {
            "device_id": device.id,
            "device_name": getattr(device, "device_name", None),
            "management_ip": getattr(device, "management_ip", None),
            "protocol": protocol,
            "episode": episode,
            "error": result.error,
        }

        source = (result.extra or {}).get("source")

        if alert_type == NotificationTypeCode.DEVICE_RECOVERED:
            metadata["reachable"] = True
            if source == "zabbix":
                title = f"设备恢复（Zabbix）：{getattr(device, 'device_name', device.id)}"
                content = "Zabbix 监控显示设备已恢复。"
            else:
                title = f"设备恢复：{getattr(device, 'device_name', device.id)}"
                content = "设备已恢复可达。"
        else:  # device_unreachable（默认）
            metadata["reachable"] = False
            if source == "zabbix":
                title = f"设备异常（Zabbix）：{getattr(device, 'device_name', device.id)}"
                content = (
                    (result.error or "Zabbix 监控判定设备异常")
                    + "；注意 Zabbix available 状态未必等于设备网络直接不可达，请结合 Zabbix 面板确认。"
                )
            else:
                title = f"设备不可达：{getattr(device, 'device_name', device.id)}"
                content = result.error or "设备连续探测失败，已达到不可达阈值。"

        alert_type_str = getattr(alert_type, "value", alert_type)
        idempotency_now = now or self._now()
        from app.services.monitoring.alert_ingress import build_dedup_key
        _conn_index = f"{idempotency_now.date().isoformat()}_{episode}_{re_alert_seq}"
        _conn_action = "recover" if "recover" in alert_type_str else "raise"
        idempotency_key = build_dedup_key(
            alert_type_str, device.id, None, _conn_index, _conn_action
        )
        source_module = f"monitor:{device.id}"

        return {
            "type": alert_type,
            "severity": severity,
            "title": title,
            "content": content,
            "payload": metadata,
            "source_module": source_module,
            "target_type": target_type,
            "target_id": target_id,
            "channels": channels,
            "idempotency_key": idempotency_key,
            "allow_broadcast": allow_broadcast,
        }

    def _enqueue_alert(self, device, alert_type: str, severity: str, result: ProbeResult,
                       episode: int, protocol: str, re_alert_seq: int = 0,
                       resolved=None, session=None, now=None) -> None:
        """入箱一条待发告警（与状态 upsert 同一事务提交）。

        不再在 apply_result 内同步调用 notify，避免「状态未提交即已发送通知」的
        一致性窗口；投递由进程内 MonitorOutboxSender 轮询完成。
        dedup_key 直接复用 notify 的 idempotency_key：发件器重放时 notify 幂等去重
        保证「至少一次投递」且不会重复通知。
        """
        payload = self._build_alert_payload(
            device, alert_type, severity, result, episode, protocol,
            re_alert_seq=re_alert_seq, resolved=resolved, now=now,
        )

        try:
            from app.core.enums import DeviceStatus
            if device.status == DeviceStatus.MAINTENANCE:
                logger.info(
                    "设备维护中，告警静默 device=%s alert_type=%s",
                    device.id, getattr(alert_type, "value", alert_type),
                )
                return
        except Exception:
            logger.warning("维护模式判定失败（fail-open 不阻断）", exc_info=True)

        from app.services.monitoring.alert_ingress import governance_should_emit
        alert_type_str = getattr(alert_type, "value", alert_type)
        should_emit, aggregated, suppressed_count = governance_should_emit(
            device.id, alert_type_str, payload["idempotency_key"],
            severity=severity,
            skip_maintenance_cache=True,  # 维护态已用内存 device 对象判过
        )
        if not should_emit:
            return
        if aggregated:
            payload = dict(payload)
            payload["suppressed_count"] = suppressed_count

        outbox_row = MonitorAlertOutboxRepository(session=session).add(
            device.id, alert_type, severity, payload["idempotency_key"], payload,
        )

        try:
            from app.services.monitoring.alert_ingress import publish_monitor_alert_event
            publish_monitor_alert_event(
                device.id, alert_type_str, severity,
                payload["idempotency_key"], outbox_row.id, payload,
            )
        except Exception:
            logger.warning("SSE 推送失败（不影响告警入箱）", exc_info=True)

        try:
            from app.services.monitoring.incident_aggregator import aggregate_alert
            alert_type_str = getattr(alert_type, "value", alert_type)
            aggregate_alert(device.id, alert_type_str, severity,
                            outbox_id=outbox_row.id)
        except Exception:
            logger.warning("monitor 事件聚合失败 device_id=%s", device.id,
                           exc_info=True)



def get_overview(failure_threshold: int = 2) -> dict:
    """监控总览统计（多 repo 聚合）。

    P1-1：读路径下沉 service，路由层不再直访 repository。
    """
    from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository
    from app.persistence.device_metric_alert_state_repository import DeviceMetricAlertStateRepository
    status_repo = DeviceMonitorStatusRepository()
    _metric_alert_state_repo = DeviceMetricAlertStateRepository()
    stats = status_repo.overview_stats(failure_threshold=failure_threshold)
    by_protocol = status_repo.distribution_by_protocol()
    by_device_type = status_repo.distribution_by_device_type()
    recent = status_repo.recent_alerts(limit=20)
    alert_stats = _metric_alert_state_repo.overview_alert_stats()
    return {
        **stats,
        **alert_stats,
        "by_protocol": by_protocol,
        "by_device_type": by_device_type,
        "recent_alerts": recent,
    }


def list_statuses(status_filter: str = None, page: int = 1, per_page: int = 20,
                  keyword: str = None) -> dict:
    """批量查询设备监控状态（含指标告警聚合）。

    返回 {"total": int, "items": list[dict]}。
    P1-1：读路径下沉 service，路由层不再直访 repository。
    keyword：模糊匹配 device_name / management_ip / ipmi_address（透传至 repo）。
    """
    from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository
    from app.persistence.device_metric_alert_state_repository import DeviceMetricAlertStateRepository
    status_repo = DeviceMonitorStatusRepository()
    _metric_alert_state_repo = DeviceMetricAlertStateRepository()
    device_ids = None
    if status_filter == "metric_alerting":
        device_ids = list(_metric_alert_state_repo.active_alerts_by_device().keys())
    elif status_filter == "interrupted":
        device_ids = list(_metric_alert_state_repo.interrupted_device_ids())

    total, items = status_repo.list_with_device(
        status_filter=status_filter, page=page, per_page=per_page, device_ids=device_ids,
        keyword=keyword,
    )
    alert_by_device = _metric_alert_state_repo.active_alerts_by_device()
    interrupted_ids = _metric_alert_state_repo.interrupted_device_ids()
    for row in items:
        agg = alert_by_device.get(row["device_id"], {})
        row["active_metric_alerts"] = agg.get("alert_count", 0)
        row["max_alert_severity"] = agg.get("max_severity", 0)
        row["monitor_interrupted"] = row["device_id"] in interrupted_ids
    return {"total": total, "items": items}


def list_alerts(params: dict) -> dict:
    """分页查询告警投递历史。

    返回 {"total": int, "items": list[dict], "page": int, "per_page": int}。
    P1-1：读路径下沉 service，路由层不再直访 repository。

    scope=mine：仅返回当前用户负责的设备的告警（device.responsible_person == user_id）。
    user_id 由调用方（路由层）注入，避免 service 依赖 request 上下文。
    """
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    alert_repo = MonitorAlertOutboxRepository()
    page = params.get("page") or 1
    per_page = params.get("per_page") or 20

    device_ids = None
    if params.get("scope") == "mine":
        user_id = params.get("user_id")
        if user_id is not None:
            from app.models.device import Device
            device_ids = [
                d.id for d in
                alert_repo.session.query(Device.id)
                .filter(Device.responsible_person == user_id, Device.deleted_at.is_(None))
                .all()
            ]

    total, items = alert_repo.list_with_device(
        alert_type=params.get("alert_type"),
        severity=params.get("severity"),
        status=params.get("status"),
        device_id=params.get("device_id"),
        start_date=params.get("start_date"),
        end_date=params.get("end_date"),
        page=page,
        per_page=per_page,
        device_ids=device_ids,
        metric_key=params.get("metric_key"),
        index_key=params.get("index_key"),
    )
    return {"total": total, "items": items, "page": page, "per_page": per_page}


def get_alert_detail(alert_id: int) -> dict:
    """P1-6: 查询单条告警详情（含 device 展示字段 + acknowledged_* + payload 解析）。

    返回完整字段 dict；行不存在抛 BusinessLogicError(404)。
    """
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    from app.exceptions.business import BusinessLogicError
    alert_repo = MonitorAlertOutboxRepository()
    item = alert_repo.get_by_id_with_device(alert_id)
    if item is None:
        raise BusinessLogicError("告警记录不存在", status_code=404)
    return item


def retry_alert(alert_id: int) -> dict:
    """乐观锁重试失败告警：仅当 status=='failed' 时重置为 pending。

    返回 {"retried": bool, "alert_id": int, "status": str, "message"?: str}。
    I3：route handler 不再直访 alert_repo / ORM session。
    """
    from app.models.monitor_alert_outbox import MonitorAlertOutbox
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    from app.exceptions.business import BusinessLogicError
    alert_repo = MonitorAlertOutboxRepository()
    ok = alert_repo.reset_to_pending(alert_id)
    if not ok:
        existing = alert_repo.session.get(MonitorAlertOutbox, alert_id)
        if existing is None:
            raise BusinessLogicError("告警记录不存在", status_code=404)
        return {
            "retried": False,
            "alert_id": alert_id,
            "status": existing.status,
            "message": "该告警非 failed 状态，无需重试",
        }
    return {"retried": True, "alert_id": alert_id, "status": "pending"}


def ack_alert(alert_id: int, user: str, note: Optional[str] = None) -> dict:
    """G9: 人工确认/认领告警。

    幂等：已确认告警再次确认将刷新 acknowledged_at 与 ack_note。
    不变更 status（保持 sent），仅填充 acknowledged_by/at/note 三字段。
    升级扫描通过 acknowledged_at IS NULL 判断未确认，ack 后天然排除该行，无需失效缓存。

    返回 {"id": int, "acknowledged_by": str, "acknowledged_at": str|None, "ack_note": str|None}。
    """
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    from app.exceptions.business import BusinessLogicError
    alert_repo = MonitorAlertOutboxRepository()
    row = alert_repo.acknowledge(alert_id, user=user, note=note)
    if row is None:
        raise BusinessLogicError("告警记录不存在", status_code=404)
    return {
        "id": row.id,
        "acknowledged_by": row.acknowledged_by,
        "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
        "ack_note": row.ack_note,
    }


def batch_ack_alert(ids: list, user: str, note: Optional[str] = None) -> dict:
    """G9 批量确认/认领告警。返回 {"acknowledged": N, "not_found": M}。"""
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    alert_repo = MonitorAlertOutboxRepository()
    return alert_repo.batch_acknowledge(ids, user=user, note=note)


def batch_retry_alert(ids: list) -> dict:
    """批量乐观锁重试失败告警。返回 {"retried": N, "skipped": M}。"""
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    alert_repo = MonitorAlertOutboxRepository()
    return alert_repo.batch_reset_to_pending(ids)


def close_alert(alert_id: int, user: str, reason: Optional[str] = None) -> dict:
    """P2-16: 手动关闭告警。"""
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    from app.exceptions.business import BusinessLogicError
    alert_repo = MonitorAlertOutboxRepository()
    row = alert_repo.close_alert(alert_id, user=user, reason=reason)
    if row is None:
        raise BusinessLogicError("告警记录不存在", status_code=404)
    return {
        "id": row.id,
        "closed_by": row.closed_by,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "close_reason": row.close_reason,
    }


def batch_close_alert(ids: list, user: str, reason: Optional[str] = None) -> dict:
    """P2-16: 批量手动关闭告警。"""
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    alert_repo = MonitorAlertOutboxRepository()
    return alert_repo.batch_close(ids, user=user, reason=reason)


def get_probe_trends(
    device_id: int,
    from_: Optional[datetime] = None,
    to_: Optional[datetime] = None,
    protocol: Optional[str] = None,
) -> dict:
    """聚合统计（供趋势卡片）：可达率 / 延迟统计 / 不可达周期数。

    90 天 retention floor 决策下沉到 service 层：
    - from_ 在 90 天内 → 走 events 明细表
    - from_ 超过 90 天 → 走 hourly 聚合表
    """
    if to_ is None:
        to_ = datetime.now(timezone.utc).replace(tzinfo=None)
    if from_ is None:
        from_ = to_ - timedelta(days=7)

    retention_floor = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
    ts_repo = MonitorTimeseriesRepository()
    if from_ >= retention_floor:
        agg = ts_repo.aggregate_events(
            device_id, from_=from_, to_=to_, protocol=protocol
        )
    else:
        agg = ts_repo.aggregate_hourly(
            device_id, from_=from_, to_=to_, protocol=protocol
        )
    return agg


def aggregate_alerts(
    window_minutes: int = 5,
    start_date=None,
    end_date=None,
    severity: Optional[str] = None,
    only_active: bool = True,
    max_groups: int = 50,
) -> list:
    """P2-10: 告警聚合/事件关联。返回聚类组列表。"""
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    repo = MonitorAlertOutboxRepository()
    return repo.aggregate_alerts(
        window_minutes=window_minutes,
        start_date=start_date,
        end_date=end_date,
        severity=severity,
        only_active=only_active,
        max_groups=max_groups,
    )


def get_alert_statistics(
    start_date=None,
    end_date=None,
    device_id: Optional[int] = None,
    severity: Optional[str] = None,
    bucket: str = "hour",
    top_n: int = 10,
) -> dict:
    """P2-15: 告警多维度统计报表。

    参数:
    - start_date / end_date: 时间范围（ISO 字符串或 datetime）
    - device_id: 仅统计指定设备
    - severity: 仅统计指定级别
    - bucket: density 桶粒度，'hour' 或 'day'
    - top_n: Top N 设备/类型取多少条
    """
    from app.persistence.monitor_alert_outbox_repository import MonitorAlertOutboxRepository
    from datetime import datetime

    def _parse_dt(v):
        if v is None or isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(v)
        except (ValueError, TypeError):
            return None

    repo = MonitorAlertOutboxRepository()
    return repo.statistics(
        start_date=_parse_dt(start_date),
        end_date=_parse_dt(end_date),
        device_id=device_id,
        severity=severity,
        bucket=bucket,
        top_n=top_n,
    )
