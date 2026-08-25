"""IPMI 监控适配器（服务器 / BMC，Redfish 不可用时的兜底）。

设计要点（与 `snmp_adapter.py` / `redfish_adapter.py` 保持同一套结构 + 防挂死模式）：
- `probe()` 只做一件事：调用模块级函数 `_ipmi_get_power_status()` 取 chassis 电源
  状态，并把它转成统一的 `ProbeResult`。该内层函数被单测 patch，因此真实 pyghmi
  调用是否完全正确是次要的——结构 + 测试通过是首要目标。
- 该适配器仅在设备**没有 Redfish 凭据、只有 IPMI 凭据**时被 `MonitorService` 选中
  （Task 5 负责选择逻辑）；此处只实现 `probe`。
- 防挂死兜底：把 `_ipmi_get_power_status` 放进普通 `threading.Thread(daemon=True)`，
  用 `join(timeout=monitor_timeout_seconds())` 限时。若 pyghmi 同步阻塞（如 BMC 无响应、
  UDP 不回包），外加这层超时能在 `monitor_timeout_seconds()` 内强制返回
  `ProbeResult(reachable=False, error="probe_timeout")`。与 CPython 私有 API 零耦合，
  跨 Python 版本安全。

此"daemon 线程 + join(timeout)"模式从 Task 2（SNMPAdapter）已验收的修复复用，
**不使用 `concurrent.futures` 私有内部 API**（如 `_threads_queues` / `_worker`）。
"""

import logging
import threading
import time

from app.services.monitoring.adapters.base_adapter import (
    MonitorAdapter,
    MonitorProtocolCode,
    ProbeResult,
    monitor_timeout_seconds,
    run_with_timeout,
)
from app.core.enums import ProbeErrorCode

logger = logging.getLogger(__name__)

_DEFAULT_IPMI_PORT = 623

_DISK_EVENT_KEYWORDS = (
    "drive",
    "disk",
    "storage",
    "raid",
    "array",
    "logical drive",
    "physical drive",
)


def _ipmi_get_power_status(
    credential: dict, bmc_ip: str
) -> tuple[bool, str | None, str | None]:
    """通过 pyghmi 取 BMC 上报的 chassis 电源状态（`chassis power status`）。

    返回 `(success, power_state_or_None, error_or_None)`。
    success 为 False 时，error 为简短错误标记（如 "timeout" / "ipmi_error"）。
    任何异常都被内部吞掉，绝不向上抛出——保证单测可稳定 patch。

    `pyghmi` 采用惰性 import，因此即使依赖未安装也不会破坏模块加载。
    """
    try:
        from pyghmi.ipmi.command import Command
    except Exception as exc:  # pragma: no cover - 仅在依赖缺失时触发
        logger.debug("pyghmi 不可用: %s", exc)
        return False, None, f"import_error:{exc}"

    username = credential.get("username", "")
    password = credential.get("password", "")
    port = credential.get("port", _DEFAULT_IPMI_PORT)

    cmd = None
    try:
        cmd = Command(bmc=bmc_ip, userid=username, password=password, port=port)
        result = cmd.get_power()
    except Exception as exc:
        msg = str(exc).lower()
        if "timeout" in msg:
            logger.debug("IPMI 超时 %s: %s", bmc_ip, exc)
            return False, None, ProbeErrorCode.TIMEOUT.value
        logger.warning("IPMI 错误 %s: %s", bmc_ip, exc)
        return False, None, ProbeErrorCode.IPMI_ERROR.value
    finally:
        if cmd is not None:
            try:
                cmd.ipmi_session.logout()
            except Exception as exc:  # pragma: no cover - 兜底，logout 异常不应掩盖业务结果
                logger.debug("IPMI logout 异常 %s: %s", bmc_ip, exc)

    state = result.get("powerstate") if isinstance(result, dict) else None
    if state is None:
        return False, None, ProbeErrorCode.IPMI_NO_DATA.value
    return True, str(state), None


def _ipmi_collect_metrics(credential: dict, bmc_ip: str, timeout: int) -> dict:
    """同步采集 IPMI 指标（温度传感器 + SEL 磁盘/存储事件）。

    返回 ``{metric_key: {index: value}}``，其中：
    - temperature：``{sensor_name: sensor_value}``（gauge，单位 Celsius）
    - raid_failure / disk_failure：``{sel_record_id: 描述}``（event 型，出现即告警）

    复用 `_ipmi_get_power_status` 的会话释放模式：单次建立 Command 会话，
    同时采集传感器与 SEL，finally 中 logout 释放，避免 BMC 会话累积。
    """
    result: dict = {}
    try:
        from pyghmi.ipmi.command import Command
    except Exception as exc:  # pragma: no cover - 依赖缺失
        return result

    username = credential.get("username", "")
    password = credential.get("password", "")
    port = credential.get("port", _DEFAULT_IPMI_PORT)

    cmd = None
    try:
        cmd = Command(bmc=bmc_ip, userid=username, password=password, port=port)

        sensors: list = []
        sensor_event = threading.Event()

        def _on_sensors(sensor_list, _err=None):
            sensors.extend(sensor_list or [])
            sensor_event.set()

        sel_records: list = []
        sel_event = threading.Event()

        def _on_sel(records, _err=None):
            sel_records.extend(records or [])
            sel_event.set()

        cmd.get_sensor_reading(readingcallback=_on_sensors)
        cmd.get_sel_entries(selcallback=_on_sel)

        sensor_waiter = threading.Thread(
            target=sensor_event.wait, args=(timeout,), daemon=True
        )
        sel_waiter = threading.Thread(
            target=sel_event.wait, args=(timeout,), daemon=True
        )
        sensor_waiter.start()
        sel_waiter.start()
        sensor_waiter.join(timeout=timeout)
        sel_waiter.join(timeout=timeout)

        temp_entries: dict = {}
        disk_temp_entries: dict = {}
        for s in sensors:
            name = str(getattr(s, "name", "")).lower()
            value = getattr(s, "value", None)
            if "temp" in name and value is not None:
                if "disk" in name or "drive" in name:
                    disk_temp_entries[str(s.name)] = value
                else:
                    temp_entries[str(s.name)] = value
        if temp_entries:
            result["temperature"] = temp_entries
        if disk_temp_entries:
            result["disk_temperature"] = disk_temp_entries

        disk_fail: dict = {}
        raid_fail: dict = {}
        for rec in sel_records:
            text = " ".join(
                str(getattr(rec, k, "")) for k in ("eventtype", "sensortype", "eventdata")
            ).lower()
            if any(kw in text for kw in _DISK_EVENT_KEYWORDS):
                record_id = str(getattr(rec, "id", len(disk_fail) + 1))
                disk_fail[record_id] = str(getattr(rec, "eventdata", "disk event"))
                if "raid" in text or "array" in text or "logical drive" in text:
                    raid_fail[record_id] = str(getattr(rec, "eventdata", "raid event"))
        if disk_fail:
            result["disk_failure"] = disk_fail
        if raid_fail:
            result["raid_failure"] = raid_fail

    except Exception as exc:  # noqa: BLE001 - 采集失败静默降级
        logger.warning("IPMI 指标采集异常 %s: %s", bmc_ip, exc)
    finally:
        if cmd is not None:
            try:
                cmd.ipmi_session.logout()
            except Exception:  # pragma: no cover - 释放兜底
                logger.warning("IPMI session logout 失败", exc_info=True)
    return result


class IPMIAdapter(MonitorAdapter):
    """IPMI 协议适配器（服务器 / BMC，Redfish 兜底）。"""

    protocol = MonitorProtocolCode.IPMI

    def _bmc_ip(self, device):
        return self.resolve_target_ip(device)

    def collect_metrics(self, device, credential, templates: list) -> dict:
        """按指标模板采集 IPMI 指标（温度 / SEL 磁盘/RAID 故障）。

        只处理 source=ipmi 的模板（temperature / disk_failure / raid_failure）。
        返回 ``{metric_key: {index: value}}``；采集失败返回空 dict，不抛出。
        """
        needed = {t["metric_key"] for t in templates if t.get("source") == "ipmi"}
        if not needed:
            return {}
        bmc_ip = self._bmc_ip(device)
        if not bmc_ip:
            return {}
        timeout = monitor_timeout_seconds()
        ok, res, _elapsed = run_with_timeout(
            lambda: _ipmi_collect_metrics(credential, bmc_ip, timeout), timeout + 3
        )
        if not ok:
            return {}
        return {k: v for k, v in res.items() if k in needed}

    def probe(self, device, credential) -> ProbeResult:
        bmc_ip = self._bmc_ip(device)
        if not bmc_ip:
            return ProbeResult(reachable=False, error=ProbeErrorCode.NO_MANAGEMENT_IP.value)

        ok, res, elapsed_ms = run_with_timeout(
            lambda: _ipmi_get_power_status(credential, bmc_ip), monitor_timeout_seconds()
        )
        if not ok:
            return ProbeResult(reachable=False, error=res)
        success, power_state, error = res
        if success:
            return ProbeResult(
                reachable=True, latency_ms=elapsed_ms, extra={"power_state": power_state}
            )
        return ProbeResult(reachable=False, error=error or "unknown")
