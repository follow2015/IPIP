import ipaddress
import logging
import socket
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from app.core.enums import MonitorProtocolCode, ProbeErrorCode

logger = logging.getLogger(__name__)

_orphan_lock = threading.Lock()
_orphan_count = 0
_orphan_fuse_blown = False
_ORPHAN_ALERT_THRESHOLD = 50
_ORPHAN_FUSE_THRESHOLD = 200


def _record_orphan(context: str) -> int:
    global _orphan_count, _orphan_fuse_blown
    with _orphan_lock:
        _orphan_count += 1
        n = _orphan_count
        if n >= _ORPHAN_FUSE_THRESHOLD:
            _orphan_fuse_blown = True
    logger.warning(
        "探测线程超时未回收（可能 socket/线程泄漏）: context=%s total=%d", context, n
    )
    if n >= _ORPHAN_ALERT_THRESHOLD and (
        n == _ORPHAN_ALERT_THRESHOLD or n % _ORPHAN_ALERT_THRESHOLD == 0
    ):
        logger.critical(
            "监控探测累计 %d 个遗弃线程（阈值 %d），疑似 socket/线程泄漏；"
            "请排查对端或网络，必要时人工重启监控进程回收资源。",
            n, _ORPHAN_ALERT_THRESHOLD,
        )
    if n == _ORPHAN_FUSE_THRESHOLD:
        logger.critical(
            "监控探测累计 %d 个遗弃线程，触发熔断保护：后续探测将跳过实际网络 I/O，"
            "避免线程/socket 持续泄漏。请立即人工处置并重启监控进程，"
            "或调用 reset_orphan_fuse() 恢复。",
            n,
        )
    return n


def orphan_fuse_blown() -> bool:
    with _orphan_lock:
        return _orphan_fuse_blown


def reset_orphan_fuse() -> None:
    global _orphan_fuse_blown
    with _orphan_lock:
        _orphan_fuse_blown = False


def get_orphan_count() -> int:
    with _orphan_lock:
        return _orphan_count


@dataclass
class ProbeResult:
    reachable: bool
    latency_ms: int | None = None
    extra: dict = field(default_factory=dict)
    error: str | None = None
    skipped: bool = False


class MonitorAdapter(ABC):

    protocol: MonitorProtocolCode

    @staticmethod
    def resolve_target_ip(device) -> Optional[str]:
        if getattr(device, "device_type", None) == "server":
            hardware = getattr(device, "hardware", None)
            ipmi = getattr(hardware, "ipmi_address", None) if hardware else None
            return ipmi or getattr(device, "management_ip", None)
        return getattr(device, "management_ip", None)

    @abstractmethod
    def probe(self, device, credential) -> ProbeResult:
        raise NotImplementedError


def monitor_timeout_seconds(default: int = 5) -> int:
    try:
        from flask import current_app
        val = current_app.config.get("MONITOR_TIMEOUT_SECONDS", default)
    except RuntimeError:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def resolve_host_with_timeout(host: str, timeout: int) -> Optional[str]:
    if _is_ip_address(host):
        return host
    holder: dict = {}
    err_holder: dict = {}
    logger.debug("DNS 预解析开始: host=%s timeout=%s", host, timeout)

    def _run():
        try:
            infos = socket.getaddrinfo(host, None)
            holder["ip"] = infos[0][4][0]
        except Exception as e:
            err_holder["e"] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        _record_orphan("resolve_host_with_timeout")
        logger.warning(
            "DNS 解析超时（可能 DNS 服务器挂死）: host=%s timeout=%s",
            host, timeout,
        )
        return None
    if "e" in err_holder:
        logger.warning("DNS 解析失败: host=%s err=%s", host, err_holder["e"])
        return None
    return holder.get("ip")


def run_with_timeout(fn, timeout: int) -> Tuple[bool, Any, int]:
    holder: dict = {}
    err_holder: dict = {}

    if orphan_fuse_blown():
        logger.critical(
            "孤儿线程熔断生效，探测已短路跳过（不执行网络 I/O）；"
            "请人工处置并重启监控进程或调用 reset_orphan_fuse()。"
        )
        return False, ProbeErrorCode.PROBE_TIMEOUT.value, 0

    import concurrent.futures.thread as _cf_thread
    if getattr(_cf_thread, "_shutdown", False):
        return False, ProbeErrorCode.PROBE_TIMEOUT.value, 0

    def _run():
        try:
            holder["v"] = fn()
        except Exception as e:
            err_holder["e"] = e

    start = time.monotonic()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    elapsed = int((time.monotonic() - start) * 1000)
    if t.is_alive():
        _record_orphan("run_with_timeout")
        return False, ProbeErrorCode.PROBE_TIMEOUT.value, elapsed
    if "e" in err_holder:
        return False, ProbeErrorCode.PROBE_ERROR.value, elapsed
    return True, holder["v"], elapsed
