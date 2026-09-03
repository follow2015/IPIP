# -*- coding: utf-8 -*-
"""Ping 连通性适配器（复用 IP 模块的探测能力）。

作为设备的「连通性触发源」，替代原先 Redfish/IPMI/Zabbix 承载的
「设备可达性」判定语义：`reachable` 在此仅表示「网络连通」，不再承担
「设备健康」判定（健康由 SNMP/IPMI 指标采集负责）。

设计要点：
- **完全复用** `app/services/ip_status_service.py` 的既有能力，不重复造轮子：
  - `detect_ip_status(ip, timeout)`：同步单 IP 探测（内部建独立 event loop），
    对私网地址只 Ping、公网地址额外顺序 TCP 端口探测（见 `_probe_ip`），
    并内置 `SAFE_MAX_CONCURRENT` 防 ARP 洪泛的安全语义。
  - 无新增 ICMP 依赖：Ping 走系统 `ping` 子进程，端口探测走 asyncio TCP connect。
- 支持「ping + 端口探测」组合：凭据 payload 可选 `ports` 列表，追加 TCP 端口
  探测（默认复用 ip_status_service 的 FAST_PROBE_PORTS）。
- 防挂死兜底：与其它适配器一致，复用 `base_adapter.run_with_timeout`
  （daemon 子线程 + join(timeout)），保证 probe() 有界返回。
- `probe()` 保持同步接口不变，兼容 MonitorService 线程池模型。
"""
from app.utils.logging import get_logger
import time

from app.core.enums import IPStatus, ProbeErrorCode
from app.services.ip_status_service import detect_ip_status
from app.services.monitoring.adapters.base_adapter import (
    MonitorAdapter,
    MonitorProtocolCode,
    ProbeResult,
    monitor_timeout_seconds,
    run_with_timeout,
)

logger = get_logger(__name__)


def _resolve_ping_ports(credential: dict) -> tuple:
    """从凭据解析待追加的 TCP 端口探测列表。

    凭据可选字段 `ports`（list[int]）：运维可为公网管理设备配置额外端口
    （如 22/443）；缺省为空元组，仅依赖 ip_status_service 的默认策略
    （私网只 Ping、公网默认端口）。
    """
    ports = credential.get("ports")
    if not ports:
        return ()
    try:
        return tuple(int(p) for p in ports)
    except (TypeError, ValueError):
        logger.warning("Ping 凭据 ports 非法，忽略: %s", ports)
        return ()


def _ping_with_ports(ip: str, timeout: int, ports: tuple) -> tuple[bool, str | None]:
    """核心探测：先 Ping，再按需 TCP 端口探测。

    返回 `(active, error_or_None)`：
    - Ping 通 → active=True；
    - Ping 不通且配置了 ports → 逐个 TCP 探测，任一可达即 active=True；
    - 全部失败 → active=False，error 为可读标记。

    说明：`detect_ip_status` 已内置「私网只 Ping / 公网默认端口」策略；
    这里在 Ping 不通时，用凭据配置的 `ports` 做补充探测，二者互补。
    """
    if detect_ip_status(ip, timeout=timeout) == IPStatus.ACTIVE:
        return True, None

    if ports:
        import asyncio
        from app.services.ip_status_service import _async_tcp_probe

        loop = asyncio.new_event_loop()
        try:
            for port in ports:
                if loop.run_until_complete(_async_tcp_probe(ip, port, timeout=timeout)):
                    return True, None
        finally:
            loop.close()
    return False, ProbeErrorCode.NETWORK_ERROR.value


class PingAdapter(MonitorAdapter):
    """Ping 连通性适配器（复用 ip_status_service 探测能力）。"""

    protocol = MonitorProtocolCode.PING

    def probe(self, device, credential) -> ProbeResult:
        ip = self.resolve_target_ip(device)
        if not ip:
            return ProbeResult(reachable=False, error=ProbeErrorCode.NO_MANAGEMENT_IP.value)

        ports = _resolve_ping_ports(credential or {})
        timeout = monitor_timeout_seconds()
        ok, res, elapsed_ms = run_with_timeout(
            lambda: _ping_with_ports(ip, timeout, ports), timeout + 3
        )
        if not ok:
            return ProbeResult(reachable=False, error=res)
        active, error = res
        if active:
            return ProbeResult(reachable=True, latency_ms=elapsed_ms, extra={"source": "ping"})
        return ProbeResult(reachable=False, error=error or ProbeErrorCode.UNKNOWN.value)
