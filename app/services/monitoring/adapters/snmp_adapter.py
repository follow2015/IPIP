"""SNMP 监控适配器（网络设备 + 其他支持 SNMP 的设备）。

采用 `pysnmp` 7.x 的**异步（asyncio）高层 API**（`pysnmp.hlapi.v3arch.asyncio`）。
注意：原 `pysnmp` 已停止维护、`pysnmp-lextudio` 维护版也被官方弃用并卸载，
项目现统一使用 `pysnmp==7.1.27`，其 API 与旧同步版（`getCmd` / `pysnmp.hlapi.v3arch`
非 async 子模块）不兼容。

设计要点：
- `probe()` 保持**同步接口不变**：上层 `MonitorService`、worker 的 `ThreadPoolExecutor`
  线程模型、挂死保护（`run_with_timeout`）与现有单测的 patch 目标全部不动。
- 真正的 SNMP I/O 在协程 `_snmp_get_sysuptime_async()` 内完成；同步边界
  `_snmp_get_sysuptime()` 用 `asyncio.run()` 包裹它，使同步 `probe()` 能消费异步结果。
  调用方（worker 线程 / API 请求线程）均无运行中的事件循环，故 `asyncio.run` 安全。
- `SnmpEngine` 在每次探测的协程内创建（pysnmp 7 异步传输与事件循环绑定，
  无法跨 `asyncio.run` 复用），开销远小于网络 RTT，故不再做旧的 `threading.local` 缓存。
- 防挂死兜底仍由 `base_adapter.run_with_timeout`（daemon 子线程 + join(timeout)）提供：
  异步探测若底层永久阻塞，外层线程超时返回 `probe_timeout`，被遗弃的 asyncio loop
  随 daemon 线程回收（与 H2 线程泄漏防护设计一致）。
"""

import asyncio
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
from app.services.monitoring.snmp_versions import SNMP_REQUIRED_BY_VERSION

logger = logging.getLogger(__name__)

_SYS_UPTIME_OID = "1.3.6.1.2.1.1.3.0"

_V2C_WARN_INTERVAL_SECONDS = 24 * 60 * 60
_V2C_WARN_MAX_ENTRIES = 50_000


class _TTLDict:

    def __init__(self, ttl: float, maxsize: int):
        self._ttl = ttl
        self._maxsize = maxsize
        self._data: dict = {}

    def __contains__(self, key) -> bool:
        item = self._data.get(key)
        if item is None:
            return False
        expires_at = item[0]
        if expires_at <= time.monotonic():
            del self._data[key]
            return False
        return True

    def __setitem__(self, key, value) -> None:
        self._data[key] = (time.monotonic() + self._ttl, value)
        if len(self._data) > self._maxsize:
            now = time.monotonic()
            expired = [k for k, (exp, _) in self._data.items() if exp <= now]
            for k in expired:
                del self._data[k]

    def clear(self) -> None:
        self._data.clear()


_v2c_warned_at = _TTLDict(ttl=_V2C_WARN_INTERVAL_SECONDS, maxsize=_V2C_WARN_MAX_ENTRIES)
_v2c_lock = threading.Lock()

_SUPPORTED_SNMP_VERSIONS = set(SNMP_REQUIRED_BY_VERSION.keys())

_pysnmp_async = None
_pysnmp_lock = threading.Lock()


def _get_pysnmp_async():
    global _pysnmp_async
    if _pysnmp_async is None:
        with _pysnmp_lock:
            if _pysnmp_async is None:
                import pysnmp.hlapi.v3arch.asyncio as _mod
                _pysnmp_async = _mod
    return _pysnmp_async


def _resolve_snmp_version(credential: dict) -> str:
    if "version" in credential:
        return credential["version"]
    if "snmp_version" in credential:
        return credential["snmp_version"]
    return "v2c"


def _build_snmp_cred(credential: dict, version: str):
    _p = _get_pysnmp_async()
    CommunityData = _p.CommunityData
    UsmUserData = _p.UsmUserData
    USM_AUTH_HMAC96_SHA = _p.USM_AUTH_HMAC96_SHA
    USM_AUTH_HMAC128_SHA224 = _p.USM_AUTH_HMAC128_SHA224
    USM_AUTH_HMAC192_SHA256 = _p.USM_AUTH_HMAC192_SHA256
    USM_AUTH_HMAC256_SHA384 = _p.USM_AUTH_HMAC256_SHA384
    USM_AUTH_HMAC384_SHA512 = _p.USM_AUTH_HMAC384_SHA512
    USM_AUTH_HMAC96_MD5 = _p.USM_AUTH_HMAC96_MD5
    USM_AUTH_NONE = _p.USM_AUTH_NONE
    USM_PRIV_CFB128_AES = _p.USM_PRIV_CFB128_AES
    USM_PRIV_CFB192_AES = _p.USM_PRIV_CFB192_AES
    USM_PRIV_CFB256_AES = _p.USM_PRIV_CFB256_AES
    USM_PRIV_CBC56_DES = _p.USM_PRIV_CBC56_DES
    USM_PRIV_CBC168_3DES = _p.USM_PRIV_CBC168_3DES
    USM_PRIV_NONE = _p.USM_PRIV_NONE

    if version == "v3":
        user = credential.get("username", "")
        auth_key = credential.get("auth_key")
        priv_key = credential.get("priv_key")
        auth_proto = credential.get("auth_protocol", "sha")
        priv_proto = credential.get("priv_protocol", "aes")

        _auth_map = {
            "sha": USM_AUTH_HMAC96_SHA,
            "sha224": USM_AUTH_HMAC128_SHA224,
            "sha256": USM_AUTH_HMAC192_SHA256,
            "sha384": USM_AUTH_HMAC256_SHA384,
            "sha512": USM_AUTH_HMAC384_SHA512,
            "md5": USM_AUTH_HMAC96_MD5,
            "none": USM_AUTH_NONE,
        }
        _priv_map = {
            "aes": USM_PRIV_CFB128_AES,
            "aes192": USM_PRIV_CFB192_AES,
            "aes256": USM_PRIV_CFB256_AES,
            "des": USM_PRIV_CBC56_DES,
            "3des": USM_PRIV_CBC168_3DES,
            "none": USM_PRIV_NONE,
        }
        auth_proto_obj = _auth_map.get(auth_proto.lower(), USM_AUTH_HMAC96_SHA)
        if auth_proto.lower() not in _auth_map:
            logger.warning(
                "SNMP v3 auth_protocol '%s' 不支持，已降级为 SHA-1", auth_proto
            )
        priv_proto_obj = _priv_map.get(priv_proto.lower(), USM_PRIV_CFB128_AES)
        if priv_proto.lower() not in _priv_map:
            logger.warning(
                "SNMP v3 priv_protocol '%s' 不支持，已降级为 AES-128", priv_proto
            )
        return UsmUserData(
            user,
            authKey=auth_key or None,
            privKey=priv_key or None,
            authProtocol=auth_proto_obj if auth_key else USM_AUTH_NONE,
            privProtocol=priv_proto_obj if (priv_key and auth_key) else USM_PRIV_NONE,
        )

    community = credential.get("community", "public")
    return CommunityData(community, mpModel=1)


async def _snmp_get_sysuptime_async(
    credential: dict, ip: str, timeout: int | None = None
) -> tuple[bool, int | None, str | None]:
    version = _resolve_snmp_version(credential)

    if version not in _SUPPORTED_SNMP_VERSIONS:
        return False, None, f"unsupported_version:{version}"

    _p = _get_pysnmp_async()
    ContextData = _p.ContextData
    SnmpEngine = _p.SnmpEngine
    UdpTransportTarget = _p.UdpTransportTarget
    ObjectType = _p.ObjectType
    ObjectIdentity = _p.ObjectIdentity
    get_cmd = _p.get_cmd

    try:
        snmp_cred = _build_snmp_cred(credential, version)
        snmp_timeout = timeout if timeout is not None else monitor_timeout_seconds()
        transport = await UdpTransportTarget.create(
            (ip, 161), timeout=snmp_timeout, retries=0
        )
        iterator = get_cmd(
            SnmpEngine(),
            snmp_cred,
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(_SYS_UPTIME_OID)),
        )
        error_indication, error_status, _error_index, var_binds = await iterator

        if error_indication:
            msg = str(error_indication).lower()
            if "timeout" in msg:
                return False, None, ProbeErrorCode.TIMEOUT.value
            return False, None, "snmp_error"
        if error_status:
            return False, None, "snmp_error"
        for _oid, val in var_binds:
            try:
                return True, int(val), None
            except (ValueError, TypeError):
                return False, None, "no_data"
        return False, None, "no_data"
    except Exception as exc:
        msg = str(exc).lower()
        if "timeout" in msg:
            return False, None, ProbeErrorCode.TIMEOUT.value
        logger.warning("SNMP _snmp_get_single 异常 ip=%s", ip, exc_info=True)
        return False, None, "exception"


def _snmp_get_sysuptime(
    credential: dict, ip: str, timeout: int | None = None
) -> tuple[bool, int | None, str | None]:
    inner_timeout = timeout if timeout is not None else monitor_timeout_seconds()
    try:
        return asyncio.run(
            asyncio.wait_for(
                _snmp_get_sysuptime_async(credential, ip, inner_timeout),
                timeout=inner_timeout,
            )
        )
    except asyncio.TimeoutError:
        return False, None, ProbeErrorCode.TIMEOUT.value


_MIB_SYMBOL_OID_FALLBACK = {
    ("ENTITY-SENSOR-MIB", "entPhySensorValue"): "1.3.6.1.2.1.99.1.1.1.5",
}


def _build_oid_identity(pysnmp_module, oid: str | None, mib: str | None, symbol: str | None):
    if not oid and mib and symbol:
        oid = _MIB_SYMBOL_OID_FALLBACK.get((mib, symbol))
    if oid:
        try:
            from pyasn1.type import univ as _asn1_univ
            return pysnmp_module.ObjectIdentity(_asn1_univ.ObjectIdentifier(oid)), oid
        except Exception:
            return None, None
    if mib and symbol:
        try:
            return pysnmp_module.ObjectIdentity(mib, symbol), None
        except Exception:
            return None, None
    return None, None


async def _snmp_walk_table_async(credential: dict, ip: str, mib: str, symbol: str,
                                 timeout: int | None = None, oid: str | None = None) -> dict:
    version = _resolve_snmp_version(credential)
    if version not in _SUPPORTED_SNMP_VERSIONS:
        return {}
    _p = _get_pysnmp_async()
    try:
        snmp_cred = _build_snmp_cred(credential, version)
        snmp_timeout = timeout if timeout is not None else monitor_timeout_seconds()
        transport = _p.UdpTransportTarget.create((ip, 161), timeout=snmp_timeout, retries=0)
        transport = await transport if asyncio.iscoroutine(transport) else transport

        result: dict = {}
        oid_identity, resolved_oid = _build_oid_identity(_p, oid, mib, symbol)
        if oid_identity is None:
            logger.warning(
                "SNMP 指标采集：OID 构造失败 mib=%s symbol=%s oid=%s ip=%s",
                mib, symbol, oid, ip,
            )
            return {}
        base_oid_str = resolved_oid or oid
        if not base_oid_str:
            try:
                base_oid_str = str(oid_identity)
            except Exception:
                logger.warning(
                    "SNMP 指标采集：无法解析 OID 前缀 mib=%s symbol=%s ip=%s",
                    mib, symbol, ip,
                )
                return {}
        if base_oid_str.endswith(".0"):
            error_indication, error_status, _ei, var_binds = await _p.get_cmd(
                _p.SnmpEngine(),
                snmp_cred,
                transport,
                _p.ContextData(),
                _p.ObjectType(oid_identity),
                lookupMib=False,
            )
            if error_indication or error_status:
                logger.warning(
                    "SNMP 指标采集：get_cmd 返回错误 mib=%s symbol=%s ip=%s error=%s",
                    mib, symbol, ip, error_status or error_indication,
                )
                return {}
            for _vb_oid, val in var_binds:
                result["0"] = val.prettyPrint() if hasattr(val, "prettyPrint") else str(val)
            return result

        iterator = _p.bulk_walk_cmd(
            _p.SnmpEngine(),
            snmp_cred,
            transport,
            _p.ContextData(),
            0, 25,
            _p.ObjectType(oid_identity),
            lexicographicMode=True,
            lookupMib=False,
        )
        base_prefix = base_oid_str + "."
        async for error_indication, error_status, _ei, var_binds in iterator:
            if error_indication or error_status:
                logger.warning(
                    "SNMP 指标采集：bulkwalk 返回错误 mib=%s symbol=%s ip=%s error=%s",
                    mib, symbol, ip, error_status or error_indication,
                )
                break
            for vb_oid, val in var_binds:
                oid_str = str(vb_oid)
                if not oid_str.startswith(base_prefix):
                    return result
                suffix = oid_str.rsplit(".", 1)[-1]
                result[suffix] = val.prettyPrint() if hasattr(val, "prettyPrint") else str(val)
        return result
    except RuntimeError as e:
        if "interpreter shutdown" in str(e):
            logger.debug(
                "SNMP 采集跳过（进程退出竞态）mib=%s symbol=%s ip=%s",
                mib, symbol, ip,
            )
            return {}
        logger.warning("SNMP 指标采集异常 mib=%s symbol=%s ip=%s", mib, symbol, ip, exc_info=True)
        return {}
    except Exception:
        logger.warning("SNMP 指标采集异常 mib=%s symbol=%s ip=%s", mib, symbol, ip, exc_info=True)
        return {}


async def _snmp_collect_all_async(
    credential: dict, ip: str, templates: list, timeout: int
) -> dict:
    async def _one(tpl: dict) -> tuple[str, dict]:
        metric_key = tpl.get("metric_key")
        mib, symbol = tpl.get("mib"), tpl.get("oid_symbol")
        oid = tpl.get("oid")
        if not metric_key or (not oid and not (mib and symbol)):
            return metric_key or "", {}
        try:
            table = await asyncio.wait_for(
                _snmp_walk_table_async(credential, ip, mib, symbol, timeout, oid=oid),
                timeout=timeout,
            )
            return metric_key, table
        except (asyncio.TimeoutError, Exception):
            logger.warning("SNMP 单模板采集失败 metric_key=%s mib=%s symbol=%s oid=%s ip=%s", metric_key, mib, symbol, oid, ip, exc_info=True)
            return metric_key, {}

    pairs = await asyncio.gather(*(_one(tpl) for tpl in templates), return_exceptions=False)
    return {key: table for key, table in pairs if key}


def _snmp_collect_metrics(
    credential: dict, ip: str, templates: list, timeout: int | None = None
) -> dict:
    if not templates:
        return {}
    inner_timeout = timeout if timeout is not None else monitor_timeout_seconds()
    try:
        return asyncio.run(
            asyncio.wait_for(
                _snmp_collect_all_async(credential, ip, templates, inner_timeout),
                timeout=inner_timeout,
            )
        )
    except asyncio.TimeoutError:
        return {}


class SNMPAdapter(MonitorAdapter):

    protocol = MonitorProtocolCode.SNMP

    def collect_metrics(self, device, credential, templates: list) -> dict:
        ip = self.resolve_target_ip(device)
        if not ip or not templates:
            return {}
        timeout = monitor_timeout_seconds()
        ok, res, _elapsed = run_with_timeout(
            lambda: _snmp_collect_metrics(credential, ip, templates, timeout), timeout + 3
        )
        return res if ok and isinstance(res, dict) else {}

    def probe(self, device, credential) -> ProbeResult:
        ip = self.resolve_target_ip(device)
        if not ip:
            return ProbeResult(reachable=False, error=ProbeErrorCode.NO_MANAGEMENT_IP.value)

        if _resolve_snmp_version(credential) == "v2c":
            with _v2c_lock:
                if ip not in _v2c_warned_at:
                    logger.warning(
                        "设备 %s 使用 SNMP v2c 不安全，建议升级至 v3（community 明文传输）", ip
                    )
                    _v2c_warned_at[ip] = True

        timeout = monitor_timeout_seconds()
        ok, res, elapsed_ms = run_with_timeout(
            lambda: _snmp_get_sysuptime(credential, ip, timeout), timeout + 3
        )
        if not ok:
            return ProbeResult(reachable=False, error=res)
        success, uptime, error = res
        if success:
            return ProbeResult(reachable=True, latency_ms=elapsed_ms, extra={"sys_uptime": uptime})
        return ProbeResult(reachable=False, error=error or ProbeErrorCode.UNKNOWN.value)
