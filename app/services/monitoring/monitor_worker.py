# -*- coding: utf-8 -*-
"""监控后台轮询线程（Redis 选举锁 + 优雅退出）

由协议注册表 `worker_loops()` 驱动的 daemon 轮询循环（当前为 snmp / bmc / zabbix / ping）：
- snmp 循环：针对 device_type 为 network / server / other 的设备，使用 snmp 凭据探测；
- bmc 循环：针对 device_type 为 server 的设备，使用 ipmi 凭据探测（服务器兜底）；
- zabbix 循环：针对无直连凭据的设备，从 Zabbix server 视角判定；
- ping 循环：针对所有设备的连通性触发源（复用 ip_status_service，无凭据）。

轮询循环的数量 / 协议 / 设备类型全部由 `protocol_registry` 单一数据源决定
（M8 / OCP）：新增协议只要在 `ProtocolSpec` 注册 `worker_loop` 与
`applies_to_device_types`，此处自动跟随，无需散点改动 `start_monitor_worker`。

设计要点（详见 Task 6 brief）：
- SQLite 测试友好：ThreadPoolExecutor 在模块级导入，测试里把它 patch 成串行
  executor（同步在当前线程执行），避免跨线程访问 StaticPool 单连接 DB。
- 每个设备的探测在独立 app context 内重新按 id 取出 Device（避免跨线程访问主
  线程加载的 ORM 对象），探测结束 finally: db.session.remove()。
- 每把轮询循环各持一把 Redis 锁（monitor:lock:<loop>），TTL = 轮询间隔安全上限，
  正常一轮结束显式释放，进程崩溃时依赖 TTL 过期兜底。
- 优雅退出：threading.Event 作 stop 信号；create_app 里注册 atexit 置位并 join 全部线程。
"""
import os
import socket
import threading
import uuid

import redis
from concurrent.futures import ThreadPoolExecutor

from app.services.monitoring.protocol_registry import (
    protocols_for_loop,
    device_types_for_loop,
    build_adapter,
    worker_loops,
    DEFAULT_LOOP_INTERVALS,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


_RELEASE_LOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

_RENEW_LOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
else
    return 0
end
"""

_LOCK_OWNER_TOKEN: str | None = None
_LOCK_OWNER_PID: int | None = None
_LOCK_OWNER_MUTEX = threading.Lock()


def lock_owner_token() -> str:
    global _LOCK_OWNER_TOKEN, _LOCK_OWNER_PID
    pid = os.getpid()
    if _LOCK_OWNER_TOKEN is None or _LOCK_OWNER_PID != pid:
        with _LOCK_OWNER_MUTEX:
            if _LOCK_OWNER_TOKEN is None or _LOCK_OWNER_PID != pid:
                try:
                    host = socket.gethostname()
                except Exception:
                    host = "unknown"
                _LOCK_OWNER_TOKEN = f"{host}:{pid}:{uuid.uuid4().hex}"
                _LOCK_OWNER_PID = pid
    return _LOCK_OWNER_TOKEN


def _lock_ttl(interval: int) -> int:
    return max(int(interval) * 2, 600)


def _acquire_lock(r, loop_name: str, interval: int) -> bool:
    return bool(
        r.set(f"monitor:lock:{loop_name}", lock_owner_token(),
              nx=True, ex=_lock_ttl(interval))
    )


def _release_lock(r, loop_name: str) -> None:
    r.eval(_RELEASE_LOCK_LUA, 1, f"monitor:lock:{loop_name}", lock_owner_token())


def _renew_lock(r, loop_name: str, interval: int) -> bool:
    res = r.eval(
        _RENEW_LOCK_LUA, 1, f"monitor:lock:{loop_name}",
        lock_owner_token(), str(_lock_ttl(interval)),
    )
    return bool(res)


class _LockWatchdog:

    def __init__(self, r, loop_name: str, interval: int, enabled: bool = True):
        self._r = r
        self._loop_name = loop_name
        self._interval = interval
        self._enabled = enabled
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "_LockWatchdog":
        if not self._enabled:
            return self
        self._thread = threading.Thread(
            target=self._run,
            name=f"monitor-lockwd-{self._loop_name}",
            daemon=True,
        )
        self._thread.start()
        return self

    def _run(self) -> None:
        step = max(_lock_ttl(self._interval) / 3.0, 1.0)
        while not self._stop.wait(step):
            try:
                if not _renew_lock(self._r, self._loop_name, self._interval):
                    logger.warning(
                        "监控轮询锁续期失败：锁已不属于本进程 loop=%s", self._loop_name
                    )
                    return
            except Exception:
                logger.warning(
                    "监控轮询锁续期异常（本轮继续） loop=%s", self._loop_name, exc_info=True
                )

    def __exit__(self, *exc) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                logger.warning(
                    "监控轮询锁续期线程未在 2s 内退出（daemon 线程将在 Redis I/O 完成后自动结束）loop=%s",
                    self._loop_name,
                )
        return False


def _redis_client(app) -> "redis.Redis":
    url = app.config.get("REDIS_URL")
    if isinstance(url, str):
        return redis.from_url(url, decode_responses=True)
    host = app.config.get("REDIS_HOST", "localhost")
    port = app.config.get("REDIS_PORT", 6379)
    password = app.config.get("REDIS_PASSWORD", "") or None
    db = app.config.get("REDIS_DB", 0)
    return redis.Redis(host=host, port=port, password=password, db=db, decode_responses=True)


def _parse_whitelist(app) -> set:
    raw = (app.config.get("MONITOR_DEVICE_IDS_WHITELIST", "") or "").strip()
    if not raw:
        return set()
    return {int(x) for x in raw.split(",") if x.strip()}


def _resolve_port_sync_enabled(device_id: int) -> bool:
    from extensions import db
    from app.models.device_switch_ext import DeviceSwitchExt
    from app.services.monitoring.dynamic_config import MonitorDynamicConfig

    ext = (
        db.session.query(DeviceSwitchExt)
        .filter_by(device_id=device_id)
        .first()
    )
    if ext is not None and ext.port_sync_enabled is not None:
        return bool(ext.port_sync_enabled)

    return bool(MonitorDynamicConfig.get("MONITOR_NON_MANAGED_PORT_SYNC"))


def _resolve_monitor_credential(device_id: int):
    from app.services.monitoring.credential_service import MonitorCredentialService
    from app.core.enums import MonitorProtocolCode

    cred_service = MonitorCredentialService()
    cred = cred_service.get_decrypted(device_id, MonitorProtocolCode.SNMP.value)
    if cred is not None:
        from app.services.monitoring.snmp_port_collector import SnmpPortCollector
        return cred, SnmpPortCollector()

    cred = cred_service.get_decrypted(device_id, MonitorProtocolCode.ZABBIX.value)
    if cred is not None:
        from app.services.monitoring.zabbix_port_collector import ZabbixPortCollector
        return cred, ZabbixPortCollector()

    return None, None


def _try_sync_non_managed_ports(device) -> None:
    try:
        device_type = getattr(device, "device_type", None)
        if device_type != "network":
            return

        from app.models.switch_credentials import SwitchCredentials
        from extensions import db
        switch_cred = (
            db.session.query(SwitchCredentials)
            .filter_by(device_id=device.id)
            .first()
        )
        has_ssh = bool(switch_cred and switch_cred.has_ssh)

        if not _resolve_port_sync_enabled(device.id):
            return

        ip = getattr(device, "management_ip", None)
        if not ip:
            return

        cred, collector = _resolve_monitor_credential(device.id)
        if cred is None or collector is None:
            return

        if not has_ssh:
            from app.services.monitoring.port_sync_service import PortSyncService
            PortSyncService().sync_device_ports(
                device.id, cred, ip, collector=collector, device=device,
            )
        else:
            port_rows = collector.collect(cred, ip, device=device)
            from app.services.monitoring.managed_port_status_sync_service import (
                ManagedPortStatusSyncService,
            )
            ManagedPortStatusSyncService().sync_device_port_status(
                device.id, port_rows,
            )
        db.session.commit()
    except Exception:
        logger.warning(
            "网络设备端口同步失败 device_id=%s", getattr(device, "id", None),
            exc_info=True,
        )


def _check_one_device(app, monitor_service, device_id: int) -> bool:
    from app.models.device import Device
    from extensions import db

    try:
        with app.app_context():
            try:
                device = db.session.get(Device, device_id)
                if device is None:
                    return True
                monitor_service.check_device(device)
                collected = monitor_service.collect_device_metrics(device)
                if collected:
                    from app.services.monitoring.metric_alert_service import MetricAlertService
                    from app.persistence.device_metric_latest_repository import (
                        DeviceMetricLatestRepository,
                    )
                    try:
                        DeviceMetricLatestRepository().upsert_many(device.id, collected)
                    except Exception:
                        db.session.rollback()
                        logger.warning("device_metric_latest upsert 失败 device_id=%s", device.id, exc_info=True)
                    try:
                        from app.persistence.device_metric_timeseries_repository import (
                            DeviceMetricTimeseriesRepository,
                        )
                        DeviceMetricTimeseriesRepository().add_many(device.id, collected)
                    except Exception:
                        db.session.rollback()
                        logger.warning("device_metric_timeseries insert 失败 device_id=%s", device.id, exc_info=True)
                    MetricAlertService().process(device.id, collected)
                    db.session.commit()
                _try_sync_non_managed_ports(device)
            finally:
                db.session.remove()
        return True
    except Exception:
        logger.error("监控探测异常（已吞掉，不中断整轮） device_id=%s", device_id, exc_info=True)
        return False


def _run_one_round(app, loop_name: str, monitor_service, executor=None, stop_event=None) -> dict:
    protocols = protocols_for_loop(loop_name)
    allowed_types = device_types_for_loop(loop_name)

    if stop_event is not None and stop_event.is_set():
        return {"checked": 0, "failed": 0, "total": 0}

    from app.persistence.device_repository import DeviceRepository

    with app.app_context():
        enabled_ids = monitor_service.get_monitored_device_ids(protocols)
        if not enabled_ids:
            return {"checked": 0, "failed": 0, "total": 0}

        device_repo = DeviceRepository()
        whitelist = _parse_whitelist(app)

        matched_ids = device_repo.find_ids_by_type(enabled_ids, allowed_types)
        target_ids = [did for did in matched_ids if not whitelist or did in whitelist]

        if not target_ids:
            return {"checked": 0, "failed": 0, "total": 0}

        own_executor = executor is None
        pool_size = app.config.get("MONITOR_THREAD_POOL_SIZE", 20)
        ex = executor or ThreadPoolExecutor(max_workers=pool_size)
        checked = 0
        failed = 0
        try:
            futures = [
                ex.submit(_check_one_device, app, monitor_service, did)
                for did in target_ids
            ]
            for f in futures:
                try:
                    ok = f.result()
                    if ok:
                        checked += 1
                    else:
                        failed += 1
                except Exception:
                    logger.error("监控探测任务提交异常", exc_info=True)
                    failed += 1
            _check_monitor_interrupted(app, monitor_service, enabled_ids, loop_name)
        finally:
            if own_executor:
                ex.shutdown(wait=False)
        return {"checked": checked, "failed": failed, "total": len(target_ids)}


def _check_monitor_interrupted(app, monitor_service, enabled_ids: list, loop_name: str) -> None:
    from datetime import datetime, timedelta, timezone
    from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository

    threshold_secs = app.config.get("MONITOR_INTERRUPTED_THRESHOLD_SECS", 180)
    threshold = timedelta(seconds=threshold_secs)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    status_repo = DeviceMonitorStatusRepository()
    status_map = status_repo.find_by_device_ids(list(enabled_ids))
    interrupted_result: dict = {}
    for did in enabled_ids:
        status = status_map.get(did)
        if status is None or status.last_checked_at is None:
            interrupted_result[did] = True
        else:
            last = status.last_checked_at.replace(tzinfo=None) if status.last_checked_at.tzinfo else status.last_checked_at
            interrupted_result[did] = (now - last) > threshold

    collector_result = {}
    for did, interrupted in interrupted_result.items():
        collector_result[did] = {
            "monitor_interrupted": {
                str(did): {
                    "breached": interrupted,
                    "severity": "critical" if interrupted else "ok",
                    "value": "interrupted" if interrupted else "normal",
                }
            }
        }

    from app.services.monitoring.metric_alert_service import MetricAlertService
    alert_service = MetricAlertService()
    for did, result in collector_result.items():
        try:
            alert_service.process(did, result)
        except Exception:
            logger.error("监控中断告警注入异常 device_id=%s", did, exc_info=True)


def _build_monitor_service():
    from app.services.monitoring.credential_service import MonitorCredentialService
    from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository
    from app.services.monitoring.monitor_service import MonitorService
    from app.core.enums import MonitorProtocolCode

    return MonitorService(
        build_adapter(MonitorProtocolCode.SNMP.value),
        build_adapter(MonitorProtocolCode.IPMI.value),
        build_adapter(MonitorProtocolCode.ZABBIX.value),
        build_adapter(MonitorProtocolCode.PING.value),
        MonitorCredentialService(),
        DeviceMonitorStatusRepository(),
    )


def _resolve_loop_interval(app, loop_name: str, current: int) -> int:
    cfg_key = f"MONITOR_INTERVAL_{loop_name.upper()}"
    try:
        with app.app_context():
            from app.services.monitoring.dynamic_config import MonitorDynamicConfig

            iv = MonitorDynamicConfig.get(cfg_key)
        if iv is not None:
            return int(iv)
    except Exception:
        logger.warning(
            "轮询 interval 热重载读取失败（沿用旧值） loop=%s", loop_name, exc_info=True
        )
    try:
        return int(app.config.get(cfg_key, current))
    except (TypeError, ValueError):
        return current


def _poll_loop(app, loop_name: str, interval: int, stop_event: threading.Event) -> None:
    monitor_service = _build_monitor_service()
    r = _redis_client(app)
    pool_size = app.config.get("MONITOR_THREAD_POOL_SIZE", 20)
    executor = ThreadPoolExecutor(
        max_workers=pool_size, thread_name_prefix=f"monitor-{loop_name}"
    )
    try:
        while not stop_event.is_set():
            interval = _resolve_loop_interval(app, loop_name, interval)
            if _acquire_lock(r, loop_name, interval):
                try:
                    with _LockWatchdog(r, loop_name, interval):
                        stats = _run_one_round(
                            app, loop_name, monitor_service,
                            executor=executor, stop_event=stop_event,
                        )
                    if stats.get("failed", 0) > 0:
                        logger.warning(
                            "监控轮询一轮有失败 loop=%s checked=%d failed=%d total=%d",
                            loop_name, stats["checked"], stats["failed"], stats["total"],
                        )
                except Exception:
                    logger.error("监控轮询一轮异常（已吞掉，继续循环） loop=%s", loop_name, exc_info=True)
                finally:
                    try:
                        _release_lock(r, loop_name)
                    except Exception:
                        logger.warning("监控轮询锁释放失败 loop=%s", loop_name, exc_info=True)
            from app.services.monitoring.adapters.base_adapter import get_orphan_count
            logger.debug("监控轮询一轮结束 loop=%s orphan_count=%d", loop_name, get_orphan_count())
            stop_event.wait(interval)
    finally:
        executor.shutdown(wait=False)


def start_monitor_worker(app) -> tuple[list[threading.Thread], threading.Event]:
    from app.services.monitoring.dynamic_config import MonitorDynamicConfig

    try:
        MonitorDynamicConfig.load_all_from_db(app)
    except Exception:
        logger.warning("动态配置启动加载失败（运行时将降级到 DB 读取）", exc_info=True)

    default_intervals = DEFAULT_LOOP_INTERVALS
    stop_event = threading.Event()
    threads: list[threading.Thread] = []

    for loop_name in worker_loops():
        interval = app.config.get(
            f"MONITOR_INTERVAL_{loop_name.upper()}",
            default_intervals.get(loop_name, 60),
        )
        t = threading.Thread(
            target=_poll_loop,
            args=(app, loop_name, interval, stop_event),
            daemon=True,
            name=f"monitor-{loop_name}",
        )
        t.start()
        threads.append(t)

    from app.services.monitoring.outbox_sender import MonitorOutboxSender
    sender = MonitorOutboxSender(
        interval=app.config.get("MONITOR_OUTBOX_INTERVAL", 5),
    )
    st = threading.Thread(
        target=sender.run_loop,
        args=(app, stop_event),
        daemon=True,
        name="monitor-outbox",
    )
    st.start()
    threads.append(st)

    from app.services.monitoring.fd_monitor import start_fd_monitor

    start_fd_monitor(stop_event=stop_event)

    logger.info(
        "监控后台轮询线程已启动 loops=%s",
        [t.name for t in threads],
    )
    return (threads, stop_event)
