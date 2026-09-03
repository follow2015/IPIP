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
from app.utils.logging import get_logger
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

logger = get_logger(__name__)

_SYS_UPTIME_OID = "1.3.6.1.2.1.1.3.0"

_V2C_WARN_INTERVAL_SECONDS = 24 * 60 * 60
_V2C_WARN_MAX_ENTRIES = 50_000  # 容量上限（触发惰性清理的阈值）


class _TTLDict:
    """极简 TTL 字典：entry 在 ``ttl`` 秒后自动过期，访问时惰性剔除。

    替代原先「锁内 sorted 全表扫描 + 手动淘汰」实现，避免长列表排序开销与
    「clear 后迭代空字典误删未过期项」的回归（见 #90）。无第三方依赖。

    **线程安全约定（P3）**：本类自身不加锁；``__contains__`` 在惰性剔除过期项时会
    执行 ``del`` 写操作，故调用方**必须**在持外部分布式/线程锁（此处为 ``_v2c_lock``）
    的情况下组合调用 ``__contains__`` + ``__setitem__``。当前所有调用点均已持锁，
    若未来新增直接调用 ``__contains__`` 的路径，须自行加锁，否则存在竞态。
    """

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
    """返回 pysnmp 7 异步高层 API 模块对象（懒加载并缓存）。

    仅在该函数首次被调用且 pysnmp 已安装时 import，因此依赖缺失不会在模块
    导入期失败；后续调用直接复用缓存的模块对象，避免每个探测重复 import 解析。
    """
    global _pysnmp_async
    if _pysnmp_async is None:
        with _pysnmp_lock:
            if _pysnmp_async is None:
                import pysnmp.hlapi.v3arch.asyncio as _mod
                _pysnmp_async = _mod
    return _pysnmp_async


def _resolve_snmp_version(credential: dict) -> str:
    """从凭据 payload 解析 SNMP 版本键。

    兼容两种键名：version（适配器约定）与 snmp_version（凭据 payload 历史键名）。
    键存在即采用其【值】（含空串——空串会在下方白名单校验处被判为非法），
    两者皆缺省才回退 "v2c"，避免 v3 凭据因键名不匹配被静默降级。
    """
    if "version" in credential:
        return credential["version"]
    if "snmp_version" in credential:
        return credential["snmp_version"]
    return "v2c"


def _build_snmp_cred(credential: dict, version: str):
    """按 version 构造 pysnmp 7 的认证对象（CommunityData / UsmUserData）。

    pysnmp 在此处才被懒加载 import，因此依赖缺失时不会掩盖上方 version 校验错误，
    也不会在模块导入期触发 import 失败。
    """
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
    """通过 SNMP 异步取对端 sysUptime（百分之一秒为单位）。

    返回 `(success, sysUptime_or_None, error_or_None)`。
    success 为 False 时，error 为简短错误标记（如 "timeout" / "auth_error"）。
    任何异常都被内部吞掉，绝不向上抛出——保证外层 `asyncio.run` 与单测稳定。
    """
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
    except Exception as exc:  # noqa: BLE001 - 内层统一吞掉，交由外层判定
        msg = str(exc).lower()
        if "timeout" in msg:
            return False, None, ProbeErrorCode.TIMEOUT.value
        logger.warning("SNMP _snmp_get_single 异常 ip=%s", ip, exc_info=True)
        return False, None, "exception"


def _snmp_get_sysuptime(
    credential: dict, ip: str, timeout: int | None = None
) -> tuple[bool, int | None, str | None]:
    """同步边界：在独立事件循环中跑异步 SNMP 探测。

    保留此函数名是为了兼容单测的 patch 目标（测试 patch 本函数即可旁路真实 I/O）；
    真实路径通过 `asyncio.run` 进入 pysnmp 7 异步 API。

    协程级硬兜底：用 ``asyncio.wait_for`` 包裹整个异步探测，超时（略大于传输层
    自身 timeout）即取消未完成的 ``await`` 并令 ``asyncio.run`` 返回——循环关闭时
    pysnmp 传输被 asyncio 回收 socket，**daemon 线程正常结束、不产生孤儿线程**。
    正常场景下传输层 ``UdpTransportTarget.create(timeout=…, retries=0)`` 会先优雅返回
    ``"timeout"``，wait_for 不会触发；仅当传输层超时机制本身失效（协程永久 await）的
    极端场景，wait_for 才作为最终协程级兜底。外层 ``run_with_timeout`` 的 daemon 线程
    仍是所有路径（含 SNMP）的最终安全网。

    P2-2：``timeout`` 由调用线程（probe，有 app context）读取动态配置后透传，
    daemon 线程内不再调用 ``monitor_timeout_seconds()``（否则无 app context 回退默认，
    动态配置热更新对实际 I/O 完全无效）。缺省时回退 ``monitor_timeout_seconds()+2``
    以兼容单测直接调用。
    """
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
    """构造 SNMP ObjectIdentity，优先用数字 OID 避免厂商 MIB 加载。

    根因：``ObjectIdentity(mib, symbol)`` 和 ``ObjectIdentity("1.3.6.1...")`` 都会
    在 ``resolve_with_mib`` 时触发 ``load_modules`` 加载厂商 MIB（如 HH3C-OAM-MIB），
    而 pysnmp 不自带这些 MIB 文件，报 ``MibNotFoundError``。

    解法：用 ``pyasn1.type.univ.ObjectIdentifier`` 构造，pysnmp 走不同解析分支，
    ``resolve_with_mib`` 时 ``__modName`` 为空，不触发厂商 MIB 加载。

    Returns:
        (ObjectIdentity, resolved_oid_str) 或 (None, None)（构造失败）
        resolved_oid_str 是数字 OID 字符串（用于子树前缀匹配，避免 str(oid_identity) 抛 SmiError）
    """
    if not oid and mib and symbol:
        oid = _MIB_SYMBOL_OID_FALLBACK.get((mib, symbol))
    if oid:
        try:
            from pyasn1.type import univ as _asn1_univ
            return pysnmp_module.ObjectIdentity(_asn1_univ.ObjectIdentifier(oid)), oid
        except Exception:  # noqa: BLE001
            return None, None
    if mib and symbol:
        try:
            return pysnmp_module.ObjectIdentity(mib, symbol), None
        except Exception:  # noqa: BLE001
            return None, None
    return None, None


async def _snmp_walk_table_async(credential: dict, ip: str, mib: str, symbol: str,
                                 timeout: int | None = None, oid: str | None = None) -> dict:
    """异步 bulkwalk 采集某 MIB 表（符号）下所有实例。

    返回 ``{str_index: value}``（str_index 为 OID 尾缀，如端口 ifIndex / 传感器编号）。
    与 sysUptime 探测一致：内部吞掉所有异常，返回可空 dict；调用方经 run_with_timeout
    兜底，避免阻塞 worker。

    依赖 pysnmp 自带标准 MIB（IF-MIB / ENTITY-SENSOR-MIB 等）；厂商私有 MIB 需放入
    pysnmp MIB 搜索路径（见 ``mibs/vendor/`` 说明），否则 OID 解析失败返回空。
    """
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
            except Exception:  # noqa: BLE001
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
            0, 25,  # non-repeaters=0, max-repetitions=25
            _p.ObjectType(oid_identity),
            lexicographicMode=True,
            lookupMib=False,  # 不解析返回 varbind 的 MIB，避免厂商 MIB 缺失报错
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
    except Exception:  # noqa: BLE001 - 内层吞掉，调用方判定
        logger.warning("SNMP 指标采集异常 mib=%s symbol=%s ip=%s", mib, symbol, ip, exc_info=True)
        return {}


async def _snmp_collect_all_async(
    credential: dict, ip: str, templates: list, timeout: int
) -> dict:
    """并发采集所有模板的指标（单事件循环内 asyncio.gather）。

    每个模板用 ``asyncio.wait_for`` 单独限时，超时或异常的模板返回空 dict，
    不影响其他模板。返回 ``{metric_key: {index: value}}``。
    """
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
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001 - 单模板失败不影响其他
            logger.warning("SNMP 单模板采集失败 metric_key=%s mib=%s symbol=%s oid=%s ip=%s", metric_key, mib, symbol, oid, ip, exc_info=True)
            return metric_key, {}

    pairs = await asyncio.gather(*(_one(tpl) for tpl in templates), return_exceptions=False)
    return {key: table for key, table in pairs if key}


def _snmp_collect_metrics(
    credential: dict, ip: str, templates: list, timeout: int | None = None
) -> dict:
    """同步边界：按模板批量采集指标（单次 asyncio.run + gather 并发）。

    返回 ``{metric_key: {index: value}}``。单个模板失败不影响其他模板。

    P0 修复：原先在 for 循环内对每个模板独立 ``asyncio.run()``，N 个模板 = N 次事件
    循环创建/销毁，开销显著。改为单次 ``asyncio.run`` 内用 ``asyncio.gather`` 并发，
    仅创建一个事件循环，且并发度提升采集吞吐。

    P2-2 修复：原实现内层 ``wait_for(timeout+2)`` 与外层 ``run_with_timeout(timeout+3)``
    仅差 1s，内层略晚返回会触发外层误判为线程泄漏（``_record_orphan`` 噪声）。
    现将内层超时对齐为 ``timeout``（传输层自身即会优雅返回 "timeout"），外层仍留
    ``+3`` 缓冲，彻底消除倒挂误判。
    """
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
    """SNMP 协议适配器。"""

    protocol = MonitorProtocolCode.SNMP

    def collect_metrics(self, device, credential, templates: list) -> dict:
        """按指标模板采集 SNMP 指标（连通性之外的业务指标采集）。

        供 worker 指标采集循环调用（区别于 probe 的连通性探测）。返回
        ``{metric_key: {index: value}}``；采集失败/无模板返回空 dict，不抛出。
        """
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
