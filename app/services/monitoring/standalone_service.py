# -*- coding: utf-8 -*-
"""监控独立微服务（Route A：独立 async 进程，复用 Flask ORM / notify）

将设备健康监控从 Flask 进程内「守护线程轮询」抽离为**独立进程**：由 asyncio 事件
循环驱动探测轮次，复用同一套 Flask ORM（db / models）、`notification_service`
（经 Redis pub/sub → realtime_gateway → SSE 推前端），但**不绑定 HTTP 生命周期**、
**不启动 in-Flask 监控线程**。

设计要点（与既有 `monitor_worker` 的关系）：
- 设备管理 / 协议分流 / 状态机 / 告警：完全复用 `MonitorService` 的
  `check_device_in_session`（每任务独立 Session 变体，替代 `@transactional` 全局
  scoped session，解耦 Flask scoped session，顺手修掉 Zabbix 会放大的 DB 连接占用）。
- 轮询循环分组（snmp / bmc）、协议→设备类型映射：由 `protocol_registry` 单一数据源驱动。
- 多进程协调：复用 `monitor_worker` 的 Redis 锁 `monitor:lock:<loop>`，与（若仍启用的）
  in-Flask worker 互斥，避免双跑；Redis 不可用时降级为「本进程直接跑」并告警。
- 适配器仍为同步接口（SNMP 内部 asyncio.run，IPMI requests）：经
  `run_in_executor` 移出主事件循环线程执行，既不被阻塞、又让 SNMP 的 asyncio.run
  在 worker 线程内安全自起 loop（主循环线程无运行中的 loop）。

与「主 app 保持 Flask」决策兼容：本服务只是多起一个进程，主 Flask 应用无需改动。
"""
import asyncio
import os
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from sqlalchemy.orm import sessionmaker

from app import create_app
from app.core.enums import MonitorProtocolCode
from app.models.device import Device
from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository
from app.persistence.device_repository import DeviceRepository
from app.services.monitoring.credential_service import MonitorCredentialService
from app.services.monitoring.monitor_service import MonitorService
from app.services.monitoring.monitor_worker import (
    _acquire_lock,
    _LockWatchdog,
    _parse_whitelist,
    _redis_client,
    _release_lock,
    _resolve_loop_interval,
)
from app.services.monitoring.protocol_registry import (
    build_adapter,
    device_types_for_loop,
    protocols_for_loop,
    worker_loops,
    DEFAULT_LOOP_INTERVALS,
    PROTOCOL_REGISTRY,
)
from extensions import db
from app.utils.logging import get_logger

logger = get_logger(__name__)


def create_headless_monitor_app(config_name: Optional[str] = None):
    prev = os.environ.get("MONITOR_WORKER_IN_PROCESS")
    os.environ["MONITOR_WORKER_IN_PROCESS"] = "false"
    try:
        if config_name is None:
            config_name = os.getenv("FLASK_ENV", "production")
        return create_app(config_name)
    finally:
        if prev is None:
            os.environ.pop("MONITOR_WORKER_IN_PROCESS", None)
        else:
            os.environ["MONITOR_WORKER_IN_PROCESS"] = prev


class StandaloneMonitorService:

    def __init__(
        self,
        app,
        snmp_adapter=None,
        ipmi_adapter=None,
        zabbix_adapter=None,
        ping_adapter=None,
        credential_service=None,
        notify=None,
        max_workers: Optional[int] = None,
        use_redis_lock: bool = True,
    ):
        self.app = app
        self.snmp_adapter = snmp_adapter or build_adapter(MonitorProtocolCode.SNMP.value)
        self.ipmi_adapter = ipmi_adapter or build_adapter(MonitorProtocolCode.IPMI.value)
        self.zabbix_adapter = zabbix_adapter or build_adapter(MonitorProtocolCode.ZABBIX.value)
        self.ping_adapter = ping_adapter or build_adapter(MonitorProtocolCode.PING.value)
        self.credential_service = credential_service or MonitorCredentialService()
        self.service = MonitorService(
            self.snmp_adapter,
            self.ipmi_adapter,
            self.zabbix_adapter,
            self.ping_adapter,
            self.credential_service,
            DeviceMonitorStatusRepository(),
            notify=notify,
        )
        self.max_workers = max_workers or app.config.get("MONITOR_THREAD_POOL_SIZE", 20)
        self.use_redis_lock = use_redis_lock
        with app.app_context():
            self.engine = db.engine
        self._sessionmaker = sessionmaker(bind=self.engine, expire_on_commit=False)
        self._redis = None
        self._stop_event: Optional[asyncio.Event] = None
        self._executor: Optional[ThreadPoolExecutor] = None


    def collect_target_ids(self, loop_name: str) -> List[int]:
        protocols = protocols_for_loop(loop_name)
        allowed_types = device_types_for_loop(loop_name)
        with self.app.app_context():
            enabled_ids = self.service.get_monitored_device_ids(protocols)
            if not enabled_ids:
                return []
            device_repo = DeviceRepository()
            whitelist = _parse_whitelist(self.app)
            matched = device_repo.find_ids_by_type(enabled_ids, allowed_types)
            target_ids = [did for did in matched if not whitelist or did in whitelist]

            spec = PROTOCOL_REGISTRY.get(loop_name)
            if spec and spec.excludes_loops:
                direct_ids: set = set()
                for ex in spec.excludes_loops:
                    direct_ids |= set(
                        self.service.get_monitored_device_ids(protocols_for_loop(ex))
                    )
                target_ids = [d for d in target_ids if d not in direct_ids]
            return target_ids


    def check_one(self, device_id: int) -> None:
        Session = self._sessionmaker
        try:
            with self.app.app_context():
                with Session() as session:
                    device = session.get(Device, device_id)
                    if device is None:
                        return
                    try:
                        self.service.check_device_in_session(device, session)
                    except Exception:
                        logger.error("监控探测异常 device_id=%s", device_id, exc_info=True)
        except Exception:
            logger.error("监控探测上下文异常 device_id=%s", device_id, exc_info=True)


    def run_round_sync(self, loop_name: str) -> int:
        target_ids = self.collect_target_ids(loop_name)
        for did in target_ids:
            self.check_one(did)
        return len(target_ids)


    def _try_acquire_lock(self, loop_name: str) -> bool:
        if not self.use_redis_lock:
            return True
        try:
            if self._redis is None:
                self._redis = _redis_client(self.app)
            interval = self.app.config.get(
                f"MONITOR_INTERVAL_{loop_name.upper()}",
                DEFAULT_LOOP_INTERVALS.get(loop_name, 60),
            )
            return _acquire_lock(self._redis, loop_name, interval)
        except Exception:
            degrade_mode = self.app.config.get("MONITOR_REDIS_DOWN_MODE", "skip")
            if degrade_mode == "execute":
                logger.warning(
                    "监控 Redis 锁获取失败，降级直接执行 loop=%s", loop_name, exc_info=True,
                )
                return True
            logger.error(
                "监控 Redis 锁获取失败，跳过本轮 loop=%s", loop_name, exc_info=True,
            )
            return False

    def _release_lock(self, loop_name: str) -> None:
        if not self.use_redis_lock or self._redis is None:
            return
        try:
            _release_lock(self._redis, loop_name)
        except Exception:
            logger.warning("监控 Redis 锁释放失败 loop=%s", loop_name, exc_info=True)


    async def _run_async_round(self, loop_name: str) -> int:
        if not self._try_acquire_lock(loop_name):
            logger.info("本轮监控锁被其他进程持有，跳过 loop=%s", loop_name)
            return 0
        try:
            watchdog_on = self.use_redis_lock and self._redis is not None
            with _LockWatchdog(
                self._redis,
                loop_name,
                self.app.config.get(
                    f"MONITOR_INTERVAL_{loop_name.upper()}",
                    DEFAULT_LOOP_INTERVALS.get(loop_name, 60),
                ),
                enabled=watchdog_on,
            ):
                target_ids = self.collect_target_ids(loop_name)
                if not target_ids:
                    return 0
                sem = asyncio.Semaphore(self.max_workers)
                loop = asyncio.get_running_loop()

                async def run_one(did: int) -> None:
                    async with sem:
                        await loop.run_in_executor(self._executor, self.check_one, did)

                await asyncio.gather(*(run_one(d) for d in target_ids))
                logger.info("监控一轮完成 loop=%s 设备数=%d", loop_name, len(target_ids))
                return len(target_ids)
        finally:
            self._release_lock(loop_name)

    async def _loop_for(self, loop_name: str) -> None:
        interval = self.app.config.get(
            f"MONITOR_INTERVAL_{loop_name.upper()}",
            DEFAULT_LOOP_INTERVALS.get(loop_name, 60),
        )
        while not self._stop_event.is_set():
            try:
                interval = _resolve_loop_interval(self.app, loop_name, interval)
            except Exception:
                logger.warning(
                    "standalone interval 热重载读取失败（沿用旧值） loop=%s",
                    loop_name, exc_info=True,
                )
            try:
                await self._run_async_round(loop_name)
            except Exception:
                logger.error("监控异步轮次异常 loop=%s", loop_name, exc_info=True)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass


    def run(self) -> None:
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        self._stop_event = asyncio.Event()
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix="monitor-io"
        )
        loops = worker_loops()
        tasks = [asyncio.create_task(self._loop_for(name)) for name in loops]

        loop = asyncio.get_running_loop()
        stop_event = self._stop_event

        sender_stop = threading.Event()
        from app.services.monitoring.outbox_sender import MonitorOutboxSender
        sender = MonitorOutboxSender(
            interval=self.app.config.get("MONITOR_OUTBOX_INTERVAL", 5),
        )
        sender_thread = threading.Thread(
            target=sender.run_loop, args=(self.app, sender_stop),
            daemon=True, name="monitor-outbox",
        )
        sender_thread.start()

        from app.services.monitoring.fd_monitor import start_fd_monitor

        start_fd_monitor(stop_event=sender_stop)

        def request_stop() -> None:
            logger.info("收到退出信号，准备停止监控服务…")
            loop.call_soon_threadsafe(stop_event.set)
            sender_stop.set()

        registered: List[int] = []
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, request_stop)
                registered.append(sig)
            except (NotImplementedError, RuntimeError):
                try:
                    signal.signal(sig, lambda *_: request_stop())
                    registered.append(sig)
                except (ValueError, OSError):
                    pass
        if not registered:
            logger.warning("无法注册任何信号 handler，仅可靠 stop_event 停止")

        try:
            await stop_event.wait()
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self._executor is not None:
                self._executor.shutdown(wait=False)
            for sig in registered:
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError):
                    pass
            logger.info("监控服务已停止")
