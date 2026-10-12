# -*- coding: utf-8 -*-
"""安全巡检调度：每日一轮，多 worker 下 leader 选举保证单实例执行。

照 `app/services/notification_cleanup.py` 的成熟模式：
`LEADER_KEY` + `SET NX EX` 选举、`_stop_event.wait()` 代替 `sleep`（停机即时中断）、
`atexit` 注册优雅停机。

与实施计划原稿的三处差异（同步登记到设计文档 §11.2）：
- logger 用 `app.utils.logging.get_logger`，不用 `app.logger` —— 与 Task 6 的 D-8
  同一口径（`tests/test_logger_convergence_guard.py` 已上提到全 app 树）；
- leader 键走 `app.utils.redis_keys.SECURITY_CHECK_LEADER_KEY` **集中登记**——
  `redis_keys` 只增不改，且 `tests/test_redis_key_inventory.py` 要求"登记了必须有人用"；
- `atexit` 只注册一次（`_atexit_registered` 标志，照 notification_cleanup）——
  原稿每次 `start` 都 `atexit.register`，多 worker 反复启动会堆叠重复回调。

**不启动时也不许"漏跑"**：一轮巡检是幂等 upsert，故 Redis 不可用时 leader 选举
fail-open 直接执行（宁可多跑一轮，不可让风险永远无人看）。
"""
from __future__ import annotations

import atexit
import os
import threading

from app.services.security.scanner import notify_violations, run_scan
from app.utils import redis_keys
from app.utils.logging import get_logger
from app.utils.redis_client import get_redis_client

logger = get_logger(__name__)

SECURITY_CHECK_INTERVAL = int(os.environ.get("SECURITY_CHECK_INTERVAL", 86400))

LEADER_KEY = redis_keys.SECURITY_CHECK_LEADER_KEY

LEADER_TTL = 3600

STOP_JOIN_TIMEOUT = 5.0

_stop_event = threading.Event()
_thread: threading.Thread | None = None
_atexit_registered = False


def _try_acquire_leader():
    """抢本轮 leader。

    Returns:
        tuple[bool, object | None]：(本轮是否应执行巡检, 抢到的 Redis 客户端)。
        第二个元素仅在**确实抢到锁**时非 None，供本轮结束释放；fail-open 时为 None。

    设计取舍（与 notification_cleanup / scan_scheduler 一致）：
    - 抢锁用 `SET NX EX`，释放复用 `app/utils/concurrency/redis_lock.py` 的
      owner token + Lua CAS，保证不会误删他人的锁；
    - **不做心跳续约**：一轮巡检 TTL 内必然结束，即使极端超时被别的 worker 重跑，
      `upsert_finding` 按唯一键幂等，无正确性影响；
    - **Redis 不可用时 fail-open**（返回 True 执行）：巡检只读被扫对象、只写 findings，
      幂等；fail-close 会让风险在 Redis 抖动期间静默停检。
    """
    from app.utils.concurrency.redis_lock import owner_token

    client = get_redis_client()
    if client is None:
        logger.debug("安全巡检：Redis 不可用，跳过 leader 选举直接执行（fail-open）")
        return True, None
    try:
        if client.set(LEADER_KEY, owner_token(), nx=True, ex=LEADER_TTL):
            return True, client
        return False, None
    except Exception:
        logger.warning("安全巡检：leader 选举失败，降级为执行本轮", exc_info=True)
        return True, None


def _release_leader(client) -> None:
    """释放本轮 leader 锁（Lua CAS：只删仍属于自己的锁）。"""
    if client is None:
        return
    try:
        from app.utils.concurrency.redis_lock import release_owner_lock
        release_owner_lock(client, LEADER_KEY)
    except Exception:
        logger.warning("安全巡检：leader 锁释放失败（TTL 兜底过期）", exc_info=True)


def run_once() -> dict:
    """执行一轮巡检（含 leader 选举与告警）。

    Returns:
        `scanner.run_scan()` 的结果；未抢到 leader 时为
        `{"ok": True, "skipped": True, "reason": "leader_held"}`。
    """
    acquired, client = _try_acquire_leader()
    if not acquired:
        logger.debug("安全巡检：本进程未抢到 leader，跳过本轮（另有 worker 在执行）")
        return {"ok": True, "skipped": True, "reason": "leader_held"}
    try:
        result = run_scan()
        if not result.get("skipped"):
            result["notified"] = notify_violations(result)
        return result
    finally:
        _release_leader(client)


def _loop(app) -> None:
    """定时巡检循环（后台守护线程）。

    用 `_stop_event.wait(interval)` 而非 `time.sleep(interval)`：停机信号能立刻中断
    等待，进程退出前不必等满一个（默认 24 小时）间隔。
    """
    while not _stop_event.wait(SECURITY_CHECK_INTERVAL):
        with app.app_context():
            try:
                run_once()
            except Exception:
                logger.warning("安全巡检失败（下轮重试）", exc_info=True)


def _run_with_app_context(app) -> None:
    """线程入口：先跑一轮（新部署不必等满一个间隔）再进入循环。"""
    with app.app_context():
        try:
            run_once()
        except Exception:
            logger.warning("安全巡检首次执行失败", exc_info=True)
    _loop(app)


def start_security_check_scheduler(app) -> threading.Event:
    """启动后台巡检线程（重复启动幂等）。

    Args:
        app: Flask 应用实例（用于保证 application context 可用）。

    Returns:
        threading.Event：停机事件（已注册 atexit 优雅停机，返回值供测试显式停机）。
    """
    global _thread, _atexit_registered

    if _thread is not None and _thread.is_alive():
        logger.debug("安全巡检线程已在运行，跳过重复启动")
        return _stop_event

    _stop_event.clear()
    _thread = threading.Thread(target=_run_with_app_context, args=(app,),
                               name="security-check", daemon=True)
    _thread.start()

    if not _atexit_registered:
        atexit.register(stop_security_check_scheduler)
        _atexit_registered = True

    logger.info("安全巡检调度已启动（间隔 %ss，leader 键=%s）",
                SECURITY_CHECK_INTERVAL, LEADER_KEY)
    return _stop_event


def stop_security_check_scheduler(timeout: float = STOP_JOIN_TIMEOUT) -> None:
    """请求停机并等待线程退出（幂等，可重复调用）。

    Args:
        timeout: join 等待上限（秒）。超时仅告警不阻塞退出。
    """
    global _thread
    _stop_event.set()
    thread = _thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning("安全巡检线程未在 %.1fs 内退出（非阻塞退出）", timeout)
    _thread = None
