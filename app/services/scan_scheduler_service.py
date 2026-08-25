# -*- coding: utf-8 -*-
"""自动扫描调度 + 陈旧度清理服务（v5 陈旧度模型）

两个独立循环：
1. 扫描调度：按 SCAN_AUTO_INTERVAL 触发各扫描单元（物理机房/虚拟机房各扫各的）
2. 陈旧度清理：按 SCAN_AUTO_CLEANUP_INTERVAL 降级超期未观测的 IP

多进程/多实例下各自 Redis leader 选举（心跳续约 + token 校验主动释放）。
续约失败时通过 lock_lost Event 联动中止主流程。

设计文档：docs/AUTO_SCAN_DESIGN.md（v5）
"""
import threading
import time
import uuid

from app.services.monitoring.dynamic_config import MonitorDynamicConfig
from app.utils.logging import get_logger

logger = get_logger(__name__)

_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

_RENEW_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    redis.call('set', KEYS[1], ARGV[1], 'xx', 'ex', ARGV[2])
    return 1
else
    return 0
end
"""


class ScanSchedulerService:

    SCAN_LEADER_KEY = "scan_scheduler:scan_leader"
    CLEANUP_LEADER_KEY = "scan_scheduler:cleanup_leader"
    LOCK_TTL = 90
    RENEW_INTERVAL = 30
    RENEW_JOIN_TIMEOUT = 5

    def __init__(self, app):
        self.app = app
        self._stop_event = threading.Event()
        self._instance_id = str(uuid.uuid4())
        self._threads: list[threading.Thread] = []

    def _get_redis(self):
        from app.services.monitoring.monitor_worker import _redis_client
        return _redis_client(self.app)

    def start(self):
        for target, name in [(self._scan_loop, "scan-scheduler"), (self._cleanup_loop, "scan-cleanup")]:
            t = threading.Thread(target=target, daemon=True, name=name)
            t.start()
            self._threads.append(t)

    def stop(self):
        self._stop_event.set()

    def _scan_loop(self):
        while not self._stop_event.is_set():
            with self.app.app_context():
                interval = self._get_interval()
                try:
                    self._scan_tick()
                except Exception:
                    logger.exception("扫描调度异常")
            self._stop_event.wait(interval)

    def _scan_tick(self):
        if not self._get_enabled():
            return
        got, token, lock_lost, renew_stop, renew_thread = self._acquire_lock(self.SCAN_LEADER_KEY)
        if not got:
            logger.debug("扫描调度未获取到 leader 锁（其他实例持有）")
            return
        try:
            self._do_scan(lock_lost)
        finally:
            self._stop_renew(renew_stop, renew_thread)
            self._release_lock(self.SCAN_LEADER_KEY, token)

    def _do_scan(self, lock_lost: threading.Event):
        room_ids, vr_ids = self._get_scan_units()
        self._validate_scan_units(room_ids, vr_ids)

        from app.services.network_scanner_service import NetworkScannerService
        orchestrator = NetworkScannerService()

        for i, rid in enumerate(room_ids):
            if lock_lost.is_set():
                logger.error("扫描中途锁丢失，跳过剩余 %d 个物理机房 + %d 个虚拟机房",
                             len(room_ids) - i, len(vr_ids))
                return
            try:
                result = orchestrator.full_scan(room_id=rid)
                logger.info("物理机房 %d 自动扫描完成: completed=%s, failed=%s",
                            rid, result.get("completed"), result.get("failed"))
            except Exception:
                logger.exception("物理机房 %d 自动扫描失败", rid)

        for i, vid in enumerate(vr_ids):
            if lock_lost.is_set():
                logger.error("扫描中途锁丢失，跳过剩余 %d 个虚拟机房", len(vr_ids) - i)
                return
            try:
                result = orchestrator.full_scan(virtual_room_id=vid)
                logger.info("虚拟机房 %d 自动扫描完成: completed=%s, failed=%s",
                            vid, result.get("completed"), result.get("failed"))
            except Exception:
                logger.exception("虚拟机房 %d 自动扫描失败", vid)

    def _cleanup_loop(self):
        while not self._stop_event.is_set():
            with self.app.app_context():
                interval = self._get_cleanup_interval()
                try:
                    self._cleanup_tick()
                except Exception:
                    logger.exception("陈旧度清理异常")
            self._stop_event.wait(interval)

    def _cleanup_tick(self):
        if not self._get_enabled():
            return
        got, token, _lock_lost, renew_stop, renew_thread = self._acquire_lock(self.CLEANUP_LEADER_KEY)
        if not got:
            logger.debug("陈旧度清理未获取到 leader 锁（其他实例持有）")
            return
        try:
            grace = self._get_grace_period()
            from extensions import db
            from app.persistence.ip_repositories import IPManagerRepository
            ip_repo = IPManagerRepository(db.session)
            affected = ip_repo.sweep_stale_active_ips(grace)
            logger.info("陈旧度清理完成: 降级 %d 个 IP（grace=%ds）", affected, grace)
        except Exception:
            from extensions import db
            db.session.rollback()
            raise
        finally:
            self._stop_renew(renew_stop, renew_thread)
            self._release_lock(self.CLEANUP_LEADER_KEY, token)

    def _acquire_lock(self, key: str):
        redis_client = self._get_redis()
        token = f"{self._instance_id}:{time.time()}"
        got = redis_client.set(key, token, nx=True, ex=self.LOCK_TTL)
        if not got:
            return False, None, None, None, None

        lock_lost = threading.Event()
        renew_stop = threading.Event()
        renew_thread = threading.Thread(
            target=self._renew_loop,
            args=(key, token, lock_lost, renew_stop),
            daemon=True,
            name=f"renew-{key}",
        )
        renew_thread.start()
        return True, token, lock_lost, renew_stop, renew_thread

    def _renew_loop(self, key: str, token: str, lock_lost: threading.Event, stop_event: threading.Event):
        redis_client = self._get_redis()
        renew_script = redis_client.register_script(_RENEW_LOCK_SCRIPT)
        while not stop_event.wait(self.RENEW_INTERVAL):
            if self._stop_event.is_set():
                return
            try:
                renewed = renew_script(keys=[key], args=[token, self.LOCK_TTL])
                if not renewed:
                    logger.warning("锁 %s 续约失败（可能被其他实例抢占），通知主流程中止", key)
                    lock_lost.set()
                    return
            except Exception:
                logger.exception("锁 %s 续约异常", key)
                lock_lost.set()
                return

    def _stop_renew(self, renew_stop: threading.Event | None, renew_thread: threading.Thread | None):
        if renew_stop is None or renew_thread is None:
            return
        renew_stop.set()
        if renew_thread.is_alive():
            renew_thread.join(timeout=self.RENEW_JOIN_TIMEOUT)

    def _release_lock(self, key: str, token: str):
        if not token:
            return
        try:
            redis_client = self._get_redis()
            release_script = redis_client.register_script(_RELEASE_LOCK_SCRIPT)
            release_script(keys=[key], args=[token])
        except Exception:
            logger.exception("释放锁异常 key=%s", key)

    def _get_enabled(self) -> bool:
        return bool(MonitorDynamicConfig.get("SCAN_AUTO_ENABLED"))

    def _get_interval(self) -> int:
        return int(MonitorDynamicConfig.get("SCAN_AUTO_INTERVAL") or 21600)

    def _get_cleanup_interval(self) -> int:
        return int(MonitorDynamicConfig.get("SCAN_AUTO_CLEANUP_INTERVAL") or 1800)

    def _get_grace_period(self) -> int:
        return int(MonitorDynamicConfig.get("SCAN_AUTO_GRACE_PERIOD") or 64800)

    def _get_scan_units(self) -> tuple[list[int], list[int]]:
        room_str = MonitorDynamicConfig.get("SCAN_AUTO_ROOM_IDS") or ""
        vr_str = MonitorDynamicConfig.get("SCAN_AUTO_VR_IDS") or ""
        room_ids = [int(x) for x in room_str.split(",") if x.strip().isdigit()]
        vr_ids = [int(x) for x in vr_str.split(",") if x.strip().isdigit()]
        return room_ids, vr_ids

    def _validate_scan_units(self, room_ids, vr_ids):
        from app.models.room import Room
        from app.models.virtual_room import VirtualRoom
        for rid in room_ids:
            if not Room.query.filter_by(id=rid, deleted_at=None).first():
                logger.warning("配置的物理机房 ID=%s 不存在或已删除", rid)
        for vid in vr_ids:
            if not VirtualRoom.query.filter_by(id=vid).first():
                logger.warning("配置的虚拟机房 ID=%s 不存在", vid)


def start_scan_scheduler(app):
    service = ScanSchedulerService(app)
    service.start()
    app.scan_scheduler = service

    import atexit
    atexit.register(service.stop)
    return service
