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
    """记录一次探测线程超时未回收（底层可能 socket/线程泄漏）。

    返回累计遗弃计数。跨 timeout 场景累计：
    - 达到 _ORPHAN_ALERT_THRESHOLD 倍数时升级为 critical 告警；
    - 达到 _ORPHAN_FUSE_THRESHOLD 时触发熔断（置 _orphan_fuse_blown 标志），
      由 run_with_timeout 短路后续探测，避免线程/socket 持续泄漏。
    """
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
    """查询是否已触发孤儿线程熔断（探测入口据此短路实际 I/O）。"""
    with _orphan_lock:
        return _orphan_fuse_blown


def reset_orphan_fuse() -> None:
    """重置熔断标志（人工处置/测试后恢复探测）。不清零累计计数。"""
    global _orphan_fuse_blown
    with _orphan_lock:
        _orphan_fuse_blown = False


def get_orphan_count() -> int:
    """当前累计遗弃线程数（测试/可观测用）。"""
    with _orphan_lock:
        return _orphan_count


@dataclass
class ProbeResult:
    """统一探测结果，供 MonitorService 消费，不关心具体协议细节"""
    reachable: bool
    latency_ms: int | None = None
    extra: dict = field(default_factory=dict)
    error: str | None = None
    skipped: bool = False


class MonitorAdapter(ABC):
    """监控协议适配器基类，参照 app/adapters/base_adapter.py 的 BaseDeviceAdapter(ABC) 模式"""

    protocol: MonitorProtocolCode

    @staticmethod
    def resolve_target_ip(device) -> Optional[str]:
        """统一解析设备探测目标 IP。

        服务器类型（device_type == "server"）：优先 ipmi_address（BMC 地址），
        无则兜底 management_ip。与展示层（monitor_credential_repository /
        device_monitor_status_repository 的 SQL case + coalesce）保持一致。

        其他类型（network/other）：直接用 management_ip。

        返回 None 表示无可用目标 IP，调用方应返回 NO_MANAGEMENT_IP 错误。
        """
        if getattr(device, "device_type", None) == "server":
            hardware = getattr(device, "hardware", None)
            ipmi = getattr(hardware, "ipmi_address", None) if hardware else None
            return ipmi or getattr(device, "management_ip", None)
        return getattr(device, "management_ip", None)

    @abstractmethod
    def probe(self, device, credential) -> ProbeResult:
        """执行一次探测，任何网络/协议异常都应在内部捕获并转换为
        ProbeResult(reachable=False, error=...)，不向上抛出——
        单个设备探测失败不应该影响轮询循环里其他设备的探测。
        """
        raise NotImplementedError


def monitor_timeout_seconds(default: int = 5) -> int:
    """探测超时（秒）。优先取 current_app.config[MONITOR_TIMEOUT_SECONDS]，
    无 app context 或配置缺省/非法时回退 default。"""
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
    """判断 host 是否已是 IP 地址（含 IPv4/IPv6），避免对 IP 误走 DNS。"""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def resolve_host_with_timeout(host: str, timeout: int) -> Optional[str]:
    """带超时地解析 hostname → IP。

    socket.getaddrinfo 在 DNS 服务器挂死时会无限期阻塞，
    故放在 daemon 子线程内并用 join(timeout) 限时；超时或失败返回 None，
    由调用方决定跳过本轮探测（不进入协议适配器线程，避免泄漏）。

    已是 IP 地址则直接原样返回（不触发 DNS）。
    """
    if _is_ip_address(host):
        return host
    holder: dict = {}
    err_holder: dict = {}
    logger.debug("DNS 预解析开始: host=%s timeout=%s", host, timeout)

    def _run():
        try:
            infos = socket.getaddrinfo(host, None)
            holder["ip"] = infos[0][4][0]
        except Exception as e:  # noqa: BLE001 - 内层统一吞掉，外层判定超时/失败
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
    """在 daemon 子线程执行 fn，限时 timeout 秒。

    返回 ``(ok, result_or_error, elapsed_ms)``：
    - 成功：(True, fn 返回值, 耗时)
    - 超时未回收：(False, "probe_timeout", 耗时) —— daemon 线程被遗弃，
      底层永久阻塞时 socket 不释放；此处仅记录告警便于发现泄漏
    - 异常：(False, "probe_error", 耗时)

    与 CPython 私有 API 零耦合，跨 Python 版本安全；适配器复用此函数，
    消除各自重复实现（SNMP/Redfish/IPMI 三处曾有几乎相同的超时样板）。
    """
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
        except Exception as e:  # noqa: BLE001 - 内层统一吞掉，交由外层判定
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
