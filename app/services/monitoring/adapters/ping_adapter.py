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

探测模式（P0-2：「连通性监控」升级为「质量监控」）
-------------------------------------------------
凭据 payload 可选 ``probe_mode``：

- ``fast``（**默认**，等价于历史行为）：单发 ICMP，只回答「死没死」。
  默认值刻意保持不变 —— 质量模式是逐台**额外**成本（N 个包 + N×间隔的墙钟），
  不能让升级把已有部署的探测周期整体拖长。
- ``quality``：一次 ``ping -c N`` 连续采样，额外给出丢包率 / 抖动 / 平均 RTT。
  可选 ``samples``（默认 5，上限 60）与 ``interval_ms``（默认 200，下限 200）。

``collect_metrics``：把质量采样结果喂进**既有的**指标模板 + 阈值 + 告警链
（`MetricCollector` → `DeviceMetricLatestRepository` / `device_metric_timeseries`
→ `MetricAlertService`），因此告警侧零改动。
"""
from app.utils.logging import get_logger

from app.core.enums import IPStatus, ProbeErrorCode
from app.services.ip_status_service import (
    DEFAULT_PING_INTERVAL_MS,
    DEFAULT_PING_SAMPLES,
    MAX_PING_SAMPLES,
    MIN_PING_INTERVAL_MS,
    detect_ip_status,
    ping_quality,
)
from app.services.monitoring.adapters.base_adapter import (
    MonitorAdapter,
    MonitorProtocolCode,
    ProbeResult,
    monitor_timeout_seconds,
    run_with_timeout,
)

logger = get_logger(__name__)

PROBE_MODE_FAST = "fast"
PROBE_MODE_QUALITY = "quality"

PING_QUALITY_METRIC_KEYS = frozenset({
    "ping_loss_pct",       # 丢包率 %
    "ping_jitter_ms",      # 抖动 ms
    "ping_latency_avg_ms",  # 平均 RTT ms（真实 ICMP RTT，非墙钟）
})

PING_QUALITY_INDEX = "0"


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


def _resolve_quality_params(credential: dict) -> tuple | None:
    """解析质量探测参数。返回 ``(samples, interval_ms)``；非质量模式返回 None。

    参数非法（非数字/越界）一律**钳制**而不是报错：探测链路对"配置写错"
    的容错预期是"降级到最近的合法值并继续"，而不是让整台设备停止被监控。
    """
    if (credential or {}).get("probe_mode") != PROBE_MODE_QUALITY:
        return None

    def _int(key: str, default: int, lo: int, hi: int) -> int:
        raw = (credential or {}).get(key)
        if raw is None:
            return default
        try:
            val = int(raw)
        except (TypeError, ValueError):
            logger.warning("Ping 凭据 %s 非法（%r），回退默认 %s", key, raw, default)
            return default
        if val < lo or val > hi:
            clamped = min(max(val, lo), hi)
            logger.warning("Ping 凭据 %s=%s 超出 [%s, %s]，钳制为 %s", key, val, lo, hi, clamped)
            return clamped
        return val

    return (
        _int("samples", DEFAULT_PING_SAMPLES, 1, MAX_PING_SAMPLES),
        _int("interval_ms", DEFAULT_PING_INTERVAL_MS, MIN_PING_INTERVAL_MS, 10_000),
    )


def _quality_sample(ip: str, samples: int, interval_ms: int, timeout: int):
    """执行一次质量采样（连续 N 包），返回 ``PingQuality``。"""
    return ping_quality(ip, count=samples, interval_ms=interval_ms, timeout=timeout)


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

    def _probe_quality(
        self, ip: str, credential: dict, samples: int, interval_ms: int, timeout: int
    ) -> ProbeResult:
        """质量模式探测：连续采样 → 丢包率 / 抖动 / 平均 RTT。"""
        ok, quality, elapsed_ms = run_with_timeout(
            lambda: _quality_sample(ip, samples, interval_ms, timeout),
            int(interval_ms / 1000.0 * samples + timeout * samples) + 6,
        )
        if not ok:
            return ProbeResult(reachable=False, error=quality)

        extra: dict = {"source": "ping", "probe_mode": PROBE_MODE_QUALITY}
        if quality.parsed:
            extra["loss_pct"] = quality.loss_pct
            extra["jitter_ms"] = quality.jitter_ms
            extra["samples"] = quality.sent

        if quality.reachable:
            latency = int(round(quality.rtt_avg_ms)) if quality.rtt_avg_ms is not None else elapsed_ms
            return ProbeResult(
                reachable=True,
                latency_ms=latency,
                loss_pct=quality.loss_pct,
                jitter_ms=quality.jitter_ms,
                samples=quality.sent,
                extra=extra,
            )
        ports = _resolve_ping_ports(credential or {})
        active, error = _ping_with_ports(ip, timeout, ports)
        if active:
            return ProbeResult(
                reachable=True, latency_ms=elapsed_ms,
                loss_pct=quality.loss_pct, jitter_ms=quality.jitter_ms,
                samples=quality.sent, extra={**extra, "reachable_via": "tcp_port"},
            )
        return ProbeResult(
            reachable=False,
            error=error or ProbeErrorCode.NETWORK_ERROR.value,
            loss_pct=quality.loss_pct,
            jitter_ms=quality.jitter_ms,
            samples=quality.sent,
            extra=extra,
        )

    def collect_metrics(self, device, credential, templates: list) -> dict:
        """按模板采集 ping 质量指标，返回 ``{metric_key: {index: value}}``。

        与 SNMP/IPMI 的 ``collect_metrics`` 同契约，因此 `MetricCollector` 的
        阈值评估、`MetricAlertService` 的入箱/恢复去重全部**零改动复用** ——
        这正是需求里"进现有时序存储与阈值模板体系"的落点。

        只在**确有 ping 质量模板启用**时才发包：质量采样是逐台的真实网络成本，
        没有消费方就不该产生流量。
        """
        ip = self.resolve_target_ip(device)
        if not ip or not templates:
            return {}
        wanted = {
            t["metric_key"] for t in templates
            if t.get("metric_key") in PING_QUALITY_METRIC_KEYS
        }
        if not wanted:
            return {}

        params = _resolve_quality_params(credential or {})
        if params is None:
            logger.debug(
                "设备 %s 启用了 ping 质量模板但 probe_mode 不是 quality，跳过质量采样",
                getattr(device, "id", None),
            )
            return {}
        samples, interval_ms = params
        timeout = monitor_timeout_seconds()

        quality = _quality_sample(ip, samples, interval_ms, timeout)
        if not quality.parsed:
            logger.warning(
                "ping 质量汇总解析失败 ip=%s（探测数据不落库，避免假绿灯）", ip
            )
            return {}

        values = {
            "ping_loss_pct": quality.loss_pct,
            "ping_jitter_ms": quality.jitter_ms,
            "ping_latency_avg_ms": quality.rtt_avg_ms,
        }
        return {
            key: {PING_QUALITY_INDEX: value}
            for key, value in values.items()
            if key in wanted and value is not None
        }

    def probe(self, device, credential) -> ProbeResult:
        ip = self.resolve_target_ip(device)
        if not ip:
            return ProbeResult(reachable=False, error=ProbeErrorCode.NO_MANAGEMENT_IP.value)

        timeout = monitor_timeout_seconds()
        params = _resolve_quality_params(credential or {})
        if params is not None:
            return self._probe_quality(ip, credential or {}, params[0], params[1], timeout)

        ports = _resolve_ping_ports(credential or {})
        ok, res, elapsed_ms = run_with_timeout(
            lambda: _ping_with_ports(ip, timeout, ports), timeout + 3
        )
        if not ok:
            return ProbeResult(reachable=False, error=res)
        active, error = res
        if active:
            return ProbeResult(reachable=True, latency_ms=elapsed_ms, extra={"source": "ping"})
        return ProbeResult(reachable=False, error=error or ProbeErrorCode.UNKNOWN.value)

