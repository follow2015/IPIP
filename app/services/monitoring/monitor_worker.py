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
- [WARN] 锁只保证**互斥**，不保证**限速**：抢不到锁的实例照样按自己的 interval 起轮
  ⇒ 聚合频率 = interval ÷ 实例数（gunicorn 多 worker / celery / 独立采集服务并存时
  实测 60 s 被打成 ≈18.9 s）。故另有最小间隔闸门 `monitor:rate:<loop>`
  （见 `_rate_limit_allow`），同 loop 的全部实例共享一个 interval 配额。
- 优雅退出：threading.Event 作 stop 信号；create_app 里注册 atexit 置位并 join 全部线程。
"""
import threading
import time
import weakref
from app.utils.time_utils import now_utc_naive
from app.utils.concurrency.redis_lock import owner_token, release_owner_lock

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




_RENEW_LOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
else
    return 0
end
"""

def _lock_ttl(interval: int) -> int:
    """轮询锁 TTL：进程崩溃时的兜底过期时间。

    正常路径由 `_LockWatchdog` 续期，故 TTL 不需要覆盖「一轮最长耗时」；
    TTL 越短，崩溃后其他进程接管越快。
    """
    return max(int(interval) * 2, 600)


_RATE_LIMIT_LUA = """
local t = redis.call('TIME')
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local last = redis.call('GET', KEYS[1])
if last then
    local last_ms = tonumber(last)
    if last_ms and (now_ms - last_ms) < tonumber(ARGV[1]) then
        return 0
    end
end
redis.call('SET', KEYS[1], tostring(now_ms), 'EX', tonumber(ARGV[2]))
return 1
"""


def _rate_limit_allow(r, loop_name: str, interval: int) -> bool:
    """最小间隔闸门：距上次放行不足 `interval` 则本轮跳过（不碰锁）。

    Returns:
        True = 可以继续去抢锁；False = 本轮被限速（已记入 `record_skip`）。

    **降级（fail-open）**：Redis 执行不了脚本时放行。闸门只是限速语义，锁才是互斥
    权威 —— 反过来（fail-closed）会把一次 Redis 能力缺失演变成"全网监控静默停摆"，
    与 ○7 修过的故障同型。`MONITOR_RATE_LIMIT_ENABLED=false` 可整体关掉本闸门。

    [WARN] 重启语义（有意取舍）：判据以 Redis 里的上次轮次为准 ⇒ 重启后首轮最多等一个
    interval。需要立刻探测就删 `monitor:rate:<loop>`，或临时关掉闸门开关。
    """
    try:
        allowed = r.eval(
            _RATE_LIMIT_LUA, 1, f"monitor:rate:{loop_name}",
            str(max(int(interval), 1) * 1000), str(_lock_ttl(interval)),
        )
    except Exception:
        logger.debug(
            "监控最小间隔闸门不可用（本轮放行） loop=%s", loop_name, exc_info=True
        )
        return True

    if allowed:
        return True

    try:
        from app.services.monitoring.round_metrics import record_skip

        record_skip(loop_name)
    except Exception:  # noqa: BLE001  指标写失败不得影响采集
        logger.debug("监控跳过计数写入失败（已忽略） loop=%s", loop_name)
    return False


def _resolve_rate_limit_enabled(app) -> bool:
    """解析「最小间隔闸门」开关（热重载，默认开启）。

    读取顺序与 `_resolve_loop_interval` 保持一致：动态配置（Redis/DB 双写，可在线
    改，经 `MonitorDynamicConfig.get`）→ `app.config` → 默认 True。任一步失败都
    降级到下一级，**不得抛错**（它在轮询循环里被调用）。

    默认必须是**开**：关掉即回到"聚合频率 = interval ÷ 实例数"的放大状态，而配置值
    看起来完全正常、没有任何报错。
    """
    cfg_key = "MONITOR_RATE_LIMIT_ENABLED"
    try:
        with app.app_context():
            from app.services.monitoring.dynamic_config import MonitorDynamicConfig

            val = MonitorDynamicConfig.get(cfg_key)
        if val is not None:
            return bool(val)
    except Exception:
        logger.debug("最小间隔闸门开关读取失败（回退配置默认值）", exc_info=True)
    try:
        return bool(app.config.get(cfg_key, True))
    except Exception:  # noqa: BLE001
        return True


def _acquire_lock(r, loop_name: str, interval: int, rate_limit: bool = True) -> bool:
    """尝试抢轮询锁：先过**最小间隔闸门**，再 SET NX EX 抢占。

    Args:
        rate_limit: 是否启用最小间隔闸门（默认 True）。显式传 False 用于现场排障
            或需要无视节奏立刻跑一轮的场合；调用方通常经
            `_resolve_rate_limit_enabled(app)` 解析配置后传入。

    闸门与锁解决的是**两件不同的事**，缺一不可：
      - 闸门（`monitor:rate:<loop>`）保证**频率**：距上次放行不足 interval 就跳过，
        使聚合频率与实例数无关；
      - 锁（`monitor:lock:<loop>`）保证**互斥**：同一时刻只有一个实例在采。
    只有锁时聚合频率 = interval ÷ 实例数（实测 60 s → 18.9 s），这正是缺陷所在。

    成功（key 不存在，写入本进程 owner token，TTL=安全上限）返回 True；
    失败（未到最小间隔 / 锁已被其他进程持有）返回 False。锁在每轮成功结束后由
    release_owner_lock 显式释放，TTL 仅作为进程崩溃时的兜底（防止锁永不过期导致
    监控停摆）。
    """
    if rate_limit and not _rate_limit_allow(r, loop_name, interval):
        return False
    return bool(
        r.set(f"monitor:lock:{loop_name}", owner_token(),
              nx=True, ex=_lock_ttl(interval))
    )


def _renew_lock(r, loop_name: str, interval: int) -> bool:
    """续期轮询锁；仍持有返回 True，已易主 / 已过期返回 False。"""
    res = r.eval(
        _RENEW_LOCK_LUA, 1, f"monitor:lock:{loop_name}",
        owner_token(), str(_lock_ttl(interval)),
    )
    return bool(res)


class _LockWatchdog:
    """轮次内锁续期看门狗（上下文管理器）。

    背景（P0-2）：TTL = ``max(interval*2, 600)``；数千台设备一轮探测可能超过
    600s，锁在轮次进行中过期 → 另一进程抢到锁开始双跑，且本进程结束时的
    release 会误删对方的锁。看门狗按 TTL/3 周期做 CAS 续期，只要进程活着锁就
    不会过期；进程崩溃则续期停止，TTL 到期后自然释放（兜底语义不变）。

    `enabled=False` 时完全不起线程（供不支持 Lua eval 的降级环境/测试使用）。
    """

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


_redis_client_cache_lock = threading.Lock()
_redis_client_cache: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()

_LOOP_ERROR_BACKOFF_SECONDS = 5.0

_STOP_POLL_SECONDS = 1.0

_LOOP_ERROR_LOG_BURST = 5
_LOOP_ERROR_LOG_INTERVAL = 60.0
_loop_error_log_state: dict = {}


def _log_loop_error(loop_name: str) -> None:
    """循环级异常日志（带突发抑制，B-28）。

    前 `_LOOP_ERROR_LOG_BURST` 次打**完整堆栈**（第一次就能定位根因）；此后每
    `_LOOP_ERROR_LOG_INTERVAL` 秒只打一条**摘要**。动机：进程退出阶段同一异常
    每轮必抛，未抑制时实测刷出 4.3 万行（还会因 logging stream 已关闭而演变成
    "报错 → 写日志失败 → 再报错"的洪水）。

    这是**限流不是吞错** —— 异常仍被吞掉并继续循环（○7 的既有语义不变），
    只是日志不再随循环次数线性膨胀。故断言"Redis 拒连时必须反复重试"的测试
    应当断言 `_acquire_lock` 的**调用次数**（不受本函数影响），而不是日志行数。
    """
    import time as _time

    state = _loop_error_log_state.setdefault(loop_name, [0, 0.0])
    state[0] += 1
    now = _time.monotonic()
    if state[0] <= _LOOP_ERROR_LOG_BURST:
        logger.error(
            "监控轮询循环异常（已吞掉，本轮作废并退避 %.0fs） loop=%s",
            _LOOP_ERROR_BACKOFF_SECONDS, loop_name, exc_info=True,
        )
        state[1] = now
    elif now - state[1] >= _LOOP_ERROR_LOG_INTERVAL:
        logger.error(
            "监控轮询循环异常持续（连续 %d 次，本轮作废并退避 %.0fs；完整堆栈见前 %d 条） loop=%s",
            state[0], _LOOP_ERROR_BACKOFF_SECONDS, _LOOP_ERROR_LOG_BURST, loop_name,
        )
        state[1] = now


def _redis_timeout(app, config_key: str, default: float) -> float:
    """读取 Redis 超时配置，非法值（非数字 / ≤0）回退默认值。"""
    raw = app.config.get(config_key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _redis_client(app) -> "redis.Redis":
    """返回该 app 的共享 redis 客户端（每 app 一池，弱引用缓存）。

    签名保留供测试 patch（fakeredis 注入替换整个函数，缓存随之绕过）。
    不复用 app.utils.redis_client 的全局单例——app.config["REDIS_URL"]
    经 from_object(配置类) 拷入的是 @property 描述符对象而非 str（生产路径
    拿不到 URL 字符串），曾尝试的「URL 一致时复用共享池」分支实为死分支，
    已在 code review 中移除。用 REDIS_HOST/PORT/PASSWORD/DB 构造客户端，
    密码不进字符串避免泄漏；连接异常在使用时暴露，由调用方降级
    （锁续期失败、直查 DB 等），语义与收敛前一致。
    （N-AI-1：缓存原在 dynamic_config 内部，下沉至此使 alert_ingress 等
    每次调用新建客户端的路径一并收敛。）
    """
    with _redis_client_cache_lock:
        client = _redis_client_cache.get(app)
        if client is not None:
            return client
        host = app.config.get("REDIS_HOST", "localhost")
        port = app.config.get("REDIS_PORT", 6379)
        password = app.config.get("REDIS_PASSWORD", "") or None
        db = app.config.get("REDIS_DB", 0)
        client = redis.Redis(
            host=host, port=port, password=password, db=db, decode_responses=True,
            socket_timeout=_redis_timeout(app, "MONITOR_REDIS_SOCKET_TIMEOUT", 5.0),
            socket_connect_timeout=_redis_timeout(app, "MONITOR_REDIS_CONNECT_TIMEOUT", 3.0),
            health_check_interval=30,
        )
        _redis_client_cache[app] = client
        return client


def _parse_whitelist(app) -> set:
    """解析 MONITOR_DEVICE_IDS_WHITELIST（逗号分隔 id，空=全部）。"""
    raw = (app.config.get("MONITOR_DEVICE_IDS_WHITELIST", "") or "").strip()
    if not raw:
        return set()
    return {int(x) for x in raw.split(",") if x.strip()}



def _resolve_port_sync_enabled(device_id: int) -> bool:
    """解析设备级端口同步开关。

    优先级：DeviceSwitchExt.port_sync_enabled > 全局 MONITOR_NON_MANAGED_PORT_SYNC
    - port_sync_enabled = True  → 强制开启
    - port_sync_enabled = False → 强制关闭
    - port_sync_enabled = NULL  → 跟随全局开关

    Args:
        device_id: 设备 ID

    Returns:
        bool: 是否启用端口同步
    """
    from app.persistence.device_switch_ext_repository import DeviceSwitchExtRepository
    from app.services.monitoring.dynamic_config import MonitorDynamicConfig

    ext = DeviceSwitchExtRepository().find_by_device_id(device_id)
    if ext is not None and ext.port_sync_enabled is not None:
        return bool(ext.port_sync_enabled)

    return bool(MonitorDynamicConfig.get("MONITOR_NON_MANAGED_PORT_SYNC"))


def _resolve_monitor_credential(device_id: int):
    """解析设备的监控凭据（SNMP 优先，无 SNMP 则 Zabbix）。

    Returns:
        (cred, collector) 或 (None, None)
    """
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
    """网络设备端口自动同步（监控轮询期间）。

    触发条件：
    - 设备级/全局端口同步开关已打开
    - device_type == "network"（网络设备）
    - 有 SNMP 或 Zabbix 凭据（SNMP 优先，无 SNMP 则用 Zabbix）

    分流：
    - 非网管设备（has_ssh=False）：PortSyncService 四元组匹配全量替换
    - 网管设备（has_ssh=True）：ManagedPortStatusSyncService 仅更新状态 + 不匹配告警

    任何异常被吞掉，不阻断主探测流程。

    注意：本函数在 _check_one_device 的 app context + db session 内调用，
    复用当前 session，由调用方统一 commit / remove。
    """
    try:
        device_type = getattr(device, "device_type", None)
        if device_type != "network":
            return

        from app.persistence.switch_ext_repository import SwitchExtRepository
        from extensions import db  # 下面的 commit 需要（函数内导入 = 可测性支点）

        switch_cred = SwitchExtRepository().get_by_device_id(device.id)
        has_ssh = bool(switch_cred and switch_cred.has_ssh)

        if not _resolve_port_sync_enabled(device.id):
            return

        ip = getattr(device, "management_ip", None)
        if not ip:
            return

        cred, collector = _resolve_monitor_credential(device.id)
        if cred is None or collector is None:
            return  # 无 SNMP / Zabbix 凭据，无法采集

        db.session.commit()

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
    except Exception:  # noqa: BLE001 - 端口同步失败不阻断主探测
        logger.warning(
            "网络设备端口同步失败 device_id=%s", getattr(device, "id", None),
            exc_info=True,
        )


def _check_one_device(app, monitor_service, device_id: int) -> bool:
    """探测单个设备，返回是否成功（True=成功，False=异常已吞掉）。

    在调用线程内 push app context（check_device 内部用 current_app.config），
    重新按 id 取出 Device（不跨线程复用 ORM 对象），结束 finally 释放 session。
    任何异常都被吞掉，不中断整轮，但返回 False 供调用方统计失败计数。
    """
    from app.models.device import Device
    from extensions import db

    try:
        with app.app_context():
            try:
                device = db.session.get(Device, device_id)
                if device is None:
                    return True  # 设备不存在视为无操作成功
                _ = device.hardware
                db.session.expunge(device)
                db.session.commit()
                monitor_service.check_device(device)
                collected = monitor_service.collect_device_metrics(device)
                if collected:
                    from app.services.monitoring.metric_alert_service import MetricAlertService
                    from app.persistence.device_metric_latest_repository import (
                        DeviceMetricLatestRepository,
                    )
                    try:
                        DeviceMetricLatestRepository().upsert_many(device.id, collected)
                    except Exception:  # noqa: BLE001 - latest 写入失败不阻断告警
                        db.session.rollback()
                        logger.warning("device_metric_latest upsert 失败 device_id=%s", device.id, exc_info=True)
                    try:
                        from app.persistence.device_metric_timeseries_repository import (
                            DeviceMetricTimeseriesRepository,
                        )
                        DeviceMetricTimeseriesRepository().add_many(device.id, collected)
                    except Exception:  # noqa: BLE001 - 时序写入失败不阻断告警
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
    """执行一轮探测，返回本轮统计 {checked, failed, total}。

    - snmp 循环：protocols=["snmp"]，device_type ∈ {network, server, other}
    - bmc 循环：protocols=["ipmi"]，device_type == server
    - zabbix 循环：protocols=["zabbix"]，device_type ∈ {network, server, other}
    - ping 循环：protocols=["ping"]，device_type ∈ {network, server, other}（无凭据，查全部启用设备）
    按启用凭据（ping 除外）+ 设备类型 + 白名单过滤后，用 executor 并发提交 _check_one_device。

    `executor` 可由调用方传入并跨轮复用（见 `_poll_loop`，与 standalone_service
    一致，避免每轮新建销毁线程池）；缺省（直接调用 / 单测）则临时创建，保持向后兼容。

    返回 {checked, failed, total}：失败计数用于可观测性，单设备异常虽不中断整轮，
    但若无计数，探测静默失败将无法被监控（review 2.6 诉求）。
    """
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
        ex = executor or ThreadPoolExecutor(
            max_workers=pool_size, thread_name_prefix=f"monitor-{loop_name}"
        )
        checked = 0
        failed = 0
        aborted = False
        try:
            futures = [
                ex.submit(_check_one_device, app, monitor_service, did)
                for did in target_ids
            ]
            for f in futures:
                while not f.done():
                    if stop_event is not None and stop_event.is_set():
                        aborted = True
                        break
                    if stop_event is not None:
                        stop_event.wait(_STOP_POLL_SECONDS)  # 可被 set 立即唤醒
                    else:
                        time.sleep(_STOP_POLL_SECONDS)
                if aborted:
                    break
                try:
                    if f.result():
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
        stats = {"checked": checked, "failed": failed, "total": len(target_ids)}
        if aborted:
            stats["aborted"] = True
        return stats


def _check_monitor_interrupted(app, monitor_service, enabled_ids: list, loop_name: str) -> None:
    """检测监控中断：启用监控的设备若 last_checked_at 超时，注入 monitor_interrupted 告警/恢复。

    语义：设备启用了监控（monitor_enabled=True），但探测循环长时间未更新 last_checked_at
    （如 worker 崩溃、配置错误导致设备被跳过、探测异常未落库）。这与"设备宕机"不同：
    设备宕机是探测了但不可达（已有 device_unreachable 告警）；监控中断是根本没探测到。

    P0-5：「从未探测」（无状态行或 last_checked_at 为 None）≠「探测中断」。
    新启用、尚未首探的设备首轮即判 critical 会造成批量启用时的告警风暴，
    故从未探测的设备不告警（恢复态），仅记录 info 供观测配置遗漏；
    只有探测过但 last_checked_at 超时的设备才注入 monitor_interrupted。

    阈值 = 3 × interval（默认 60s → 180s），可通过 MONITOR_INTERRUPTED_THRESHOLD_SECS 配置。
    """
    from datetime import timedelta
    from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository

    threshold_secs = app.config.get("MONITOR_INTERRUPTED_THRESHOLD_SECS", 180)
    threshold = timedelta(seconds=threshold_secs)
    now = now_utc_naive()

    status_repo = DeviceMonitorStatusRepository()
    status_map = status_repo.find_by_device_ids(list(enabled_ids))
    interrupted_result: dict = {}
    never_probed: list = []
    for did in enabled_ids:
        status = status_map.get(did)
        if status is None or status.last_checked_at is None:
            interrupted_result[did] = False
            never_probed.append(did)
        else:
            last = status.last_checked_at.replace(tzinfo=None) if status.last_checked_at.tzinfo else status.last_checked_at
            interrupted_result[did] = (now - last) > threshold

    if never_probed:
        logger.info(
            "监控中断检测：%s 台设备已启用但从未被探测（不注入中断告警，等待首轮探测） device_ids=%s",
            len(never_probed), never_probed[:20],
        )

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
    """构造 MonitorService（无状态适配器 + 凭据服务 + 状态仓库）。

    适配器实例化统一走协议注册表 `build_adapter`（OCP）：新增协议只需在
    `ProtocolSpec` 注册，无需在此散点 new 具体适配器类。
    """
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


MIN_LOOP_INTERVAL = 5


def _resolve_loop_interval(app, loop_name: str, current: int) -> int:
    """热重载读取轮询间隔（每轮调用）。

    优先动态配置 MONITOR_INTERVAL_<LOOP>（Redis/DB 双写），否则回退
    app.config，再否则沿用当前值 current。读取出错（Redis 不可达等）时
    降级到 app.config / current，保证 Worker 健壮不崩溃。

    最终结果钳制到 MIN_LOOP_INTERVAL 下限（m1）。
    """
    cfg_key = f"MONITOR_INTERVAL_{loop_name.upper()}"
    candidates = []
    try:
        with app.app_context():
            from app.services.monitoring.dynamic_config import MonitorDynamicConfig

            iv = MonitorDynamicConfig.get(cfg_key)
        if iv is not None:
            candidates.append(iv)
    except Exception:
        logger.warning(
            "轮询 interval 热重载读取失败（沿用旧值） loop=%s", loop_name, exc_info=True
        )
    try:
        candidates.append(app.config.get(cfg_key, current))
    except Exception:  # noqa: BLE001
        pass

    for raw in candidates:
        try:
            val = int(raw)
        except (TypeError, ValueError):
            continue
        return max(val, MIN_LOOP_INTERVAL)
    return max(int(current), MIN_LOOP_INTERVAL)


def _poll_loop(app, loop_name: str, interval: int, stop_event: threading.Event) -> None:
    """单个轮询循环（daemon 线程入口）。

    每轮：动态读取 MONITOR_INTERVAL_<LOOP>（热重载）→ 过最小间隔闸门（同 loop 的
    全部实例共享一个 interval 配额）→ 抢 Redis 锁（TTL 随 interval 同步）→ 抢到则
    跑一轮 → stop_event.wait(interval)（可被 set 提前唤醒）。
    复用单一 ThreadPoolExecutor（与 standalone_service 一致），避免每轮新建销毁池。
    """
    monitor_service = _build_monitor_service()
    r = _redis_client(app)
    pool_size = app.config.get("MONITOR_THREAD_POOL_SIZE", 20)
    executor = ThreadPoolExecutor(
        max_workers=pool_size, thread_name_prefix=f"monitor-{loop_name}"
    )
    try:
        while not stop_event.is_set():
            try:
                interval = _resolve_loop_interval(app, loop_name, interval)
                if _acquire_lock(
                    r, loop_name, interval,
                    rate_limit=_resolve_rate_limit_enabled(app),
                ):
                    try:
                        with _LockWatchdog(r, loop_name, interval):
                            stats = _run_one_round(
                                app, loop_name, monitor_service,
                                executor=executor, stop_event=stop_event,
                            )
                        if stats.get("aborted"):
                            logger.info("监控轮询本轮因停机中止 loop=%s", loop_name)
                        elif stats.get("failed", 0) > 0:
                            logger.warning(
                                "监控轮询一轮有失败 loop=%s checked=%d failed=%d total=%d",
                                loop_name, stats["checked"], stats["failed"], stats["total"],
                            )
                        try:
                            from app.services.monitoring.round_metrics import record_round

                            record_round(loop_name)
                        except Exception:  # noqa: BLE001
                            logger.debug("监控轮次指标写入失败（已忽略） loop=%s", loop_name)
                    except Exception:
                        logger.error("监控轮询一轮异常（已吞掉，继续循环） loop=%s", loop_name, exc_info=True)
                    finally:
                        try:
                            release_owner_lock(r, f"monitor:lock:{loop_name}")
                        except Exception:
                            logger.warning("监控轮询锁释放失败 loop=%s", loop_name, exc_info=True)
                from app.services.monitoring.adapters.base_adapter import get_orphan_count
                logger.debug("监控轮询一轮结束 loop=%s orphan_count=%d", loop_name, get_orphan_count())
                stop_event.wait(interval)
            except Exception:
                if stop_event.is_set():
                    break
                _log_loop_error(loop_name)
                stop_event.wait(_LOOP_ERROR_BACKOFF_SECONDS)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)



def start_monitor_worker(app) -> tuple[list[threading.Thread], threading.Event]:
    """启动全部轮询循环（由协议注册表 worker_loops() 驱动），返回 (threads, stop_event)。

    每个 worker_loop 启动一个 daemon 线程；轮询间隔按 loop 名解析
    `MONITOR_INTERVAL_<LOOP.upper()>`（回退默认值 snmp=60 / bmc=60；单一真源 `protocol_registry.DEFAULT_LOOP_INTERVALS`）。
    优雅退出由调用方（create_app）注册 atexit 置位 stop_event 并 join 全部线程。

    新增协议只要注册表声明新的 worker_loop，此处自动多起一个线程，无需散点改动。
    """
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
