# -*- coding: utf-8 -*-
"""SNMP MIB 扫描服务（snmp-mib-scan 工具）

回应用户「自动生成 MIB 对应数据」需求：对目标设备做 MIB walk，自动发现其支持的
OID / 值类型 / 取值范围 / 采样值，输出 ``detected_metrics.json`` 作为「该厂商设备
能采什么」的自动清单。运维把探测出的 OID 拖入指标模板（MonitorMetricTemplate）
即可完成新厂商接入，零代码。

CLI 用法（Flask 命令注册见 flask_cli）::

    flask snmp-mib-scan <ip> <protocol> [--community public] [--out metrics.json]

实现：
- 复用 SNMPAdapter 的 pysnmp 7 异步 API 与凭据构造（`_build_snmp_cred`）。
- walk 起始 OID 从 ``.1``（iso）开始，收集所有可达 OID 的数值/类型。
- 输出 JSON：``{"detected": [{"oid", "value", "type", "sample_values"}], ...}``。
"""
import asyncio
import json
import os

from app.services.monitoring.adapters.snmp_adapter import (
    _build_snmp_cred,
    _get_pysnmp_async,
    _resolve_snmp_version,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

_START_OID = "1.3.6.1"
_STANDARD_MIB2_OID = "1.3.6.1.2"
_SYS_OBJECT_ID_OID = "1.3.6.1.2.1.1.2.0"
_WALK_TIME_BUDGET_SEC = float(os.environ.get("MIB_WALK_TIME_BUDGET_SEC", "60"))

_MIB_PROBE_CACHE_TTL = int(os.environ.get("MIB_PROBE_CACHE_TTL_SECONDS", "86400"))
_MIB_PROBE_CACHE_MAX_ENTRIES = int(os.environ.get("MIB_PROBE_CACHE_MAX_ENTRIES", "500"))
_MIB_PROBE_CACHE_PREFIX = "monitor:mib-probe:"


async def _read_sys_object_id(
    credential: dict, ip: str, version: str, timeout: int
) -> str | None:
    _p = _get_pysnmp_async()
    snmp_cred = _build_snmp_cred(credential, version)
    transport = _p.UdpTransportTarget.create((ip, 161), timeout=timeout, retries=1)
    transport = await transport if asyncio.iscoroutine(transport) else transport
    try:
        iterator = _p.get_cmd(
            _p.SnmpEngine(),
            snmp_cred,
            transport,
            _p.ContextData(),
            _p.ObjectType(_p.ObjectIdentity(_SYS_OBJECT_ID_OID)),
        )
        error_indication, error_status, _ei, var_binds = await iterator
        if error_indication or error_status:
            logger.warning(
                "读取 sysObjectID 失败 ip=%s error=%s", ip, error_indication or error_status
            )
            return None
        for _oid, val in var_binds:
            value = val.prettyPrint() if hasattr(val, "prettyPrint") else str(val)
            return str(value)
    except Exception:
        logger.warning("读取 sysObjectID 异常 ip=%s", ip, exc_info=True)
        return None
    return None


def _extract_enterprise(sys_object_id_value: str | None) -> str | None:
    if not sys_object_id_value:
        return None
    if "enterprises." in sys_object_id_value:
        after = sys_object_id_value.split("enterprises.", 1)[1]
        enterprise = after.split(".", 1)[0]
        return enterprise if enterprise else None
    if "1.3.6.1.4.1." in sys_object_id_value:
        after = sys_object_id_value.split("1.3.6.1.4.1.", 1)[1]
        enterprise = after.split(".", 1)[0]
        return enterprise if enterprise else None
    return None


async def _walk_subtree(
    start_oid: str, snmp_cred, transport, _p, deadline: float, rows: list, ip: str, version: str
) -> list:
    iterator = _p.bulk_walk_cmd(
        _p.SnmpEngine(),
        snmp_cred,
        transport,
        _p.ContextData(),
        0, 25,
        _p.ObjectType(_p.ObjectIdentity(start_oid)),
        lexicographicMode=True,
    )
    async for error_indication, error_status, _ei, var_binds in iterator:
        if error_indication or error_status:
            logger.warning(
                "MIB walk 返回错误 ip=%s version=%s start=%s error_indication=%s error_status=%s error_index=%s",
                ip, version, start_oid, error_indication, error_status, _ei,
            )
            break
        for oid, val in var_binds:
            rows.append(
                {
                    "oid": str(oid),
                    "type": type(val).__name__ or str(val.tagSet),
                    "value": val.prettyPrint() if hasattr(val, "prettyPrint") else str(val),
                }
            )
        if asyncio.get_event_loop().time() >= deadline:
            logger.info(
                "MIB walk 时间预算耗尽 ip=%s start=%s rows=%d deadline=%.1f",
                ip, start_oid, len(rows), deadline,
            )
            return rows
    return rows


async def _walk_all(credential: dict, ip: str, timeout: int) -> list:
    version = _resolve_snmp_version(credential)
    _p = _get_pysnmp_async()
    snmp_cred = _build_snmp_cred(credential, version)
    transport = _p.UdpTransportTarget.create((ip, 161), timeout=timeout, retries=1)
    transport = await transport if asyncio.iscoroutine(transport) else transport

    rows: list = []
    deadline = asyncio.get_event_loop().time() + _WALK_TIME_BUDGET_SEC
    await _walk_subtree(_START_OID, snmp_cred, transport, _p, deadline, rows, ip, version)

    seen: set = set()
    deduped: list = []
    for row in rows:
        if row["oid"] in seen:
            continue
        seen.add(row["oid"])
        deduped.append(row)

    before_filter = len(deduped)
    deduped, filtered_parents = _filter_noise_oids(deduped)
    filtered_count = before_filter - len(deduped)
    if filtered_count > 0:
        logger.info(
            "MIB walk 过滤无意义 OID ip=%s filtered=%d remaining=%d",
            ip, filtered_count, len(deduped),
        )

    if not deduped:
        logger.warning(
            "MIB walk 返回 0 个 OID ip=%s version=%s（可能设备不可达/凭据错误/对端无响应）",
            ip, version,
        )
    return deduped, filtered_parents


_NETSNMP_MIBNAME_PREFIX = "1.3.6.1.4.1.8072.1.2.1.1.4"
_SERIAL_TABLE_MIN = 50


def _filter_noise_oids(rows: list) -> list:
    if not rows:
        return rows, []

    kept: list = []
    for r in rows:
        oid = r["oid"]
        if oid.startswith(_NETSNMP_MIBNAME_PREFIX):
            continue
        kept.append(r)

    rule_prefixes: list[str] = []
    try:
        from app.services.monitoring.oid_category_service import _load_rule_prefixes
        rule_prefixes = _load_rule_prefixes()
    except Exception:
        pass

    from collections import defaultdict
    by_parent: dict[str, list] = defaultdict(list)
    for r in kept:
        parts = r["oid"].rsplit(".", 1)
        parent = parts[0] if len(parts) == 2 else r["oid"]
        by_parent[parent].append(r)

    serial_parents: set = set()
    for parent, items in by_parent.items():
        if len(items) < _SERIAL_TABLE_MIN:
            continue
        if any(parent.startswith(pfx) for pfx in rule_prefixes):
            continue
        try:
            vals = sorted(int(it["value"]) for it in items)
        except (ValueError, TypeError):
            continue
        n = len(vals)
        if vals == list(range(n)) or vals == list(range(1, n + 1)):
            serial_parents.add(parent)

    filtered_parents: list[dict] = []
    if serial_parents:
        kept = [r for r in kept if r["oid"].rsplit(".", 1)[0] not in serial_parents]
        filtered_parents = [
            {"parent": p, "row_count": len(by_parent[p])} for p in sorted(serial_parents)
        ]

    return kept, filtered_parents


_ENTITY_SENSOR_TYPE_OID = "1.3.6.1.2.1.99.1.1.1.1"
_ENTITY_SENSOR_VALUE_PREFIX = "1.3.6.1.2.1.99.1.1.1.5."


async def _walk_entity_sensor_type(credential: dict, ip: str, timeout: int) -> dict[str, int]:
    version = _resolve_snmp_version(credential)
    _p = _get_pysnmp_async()
    snmp_cred = _build_snmp_cred(credential, version)
    transport = _p.UdpTransportTarget.create((ip, 161), timeout=timeout, retries=1)
    transport = await transport if asyncio.iscoroutine(transport) else transport

    type_map: dict[str, int] = {}
    rows: list = []
    deadline = asyncio.get_event_loop().time() + _WALK_TIME_BUDGET_SEC
    await _walk_subtree(
        _ENTITY_SENSOR_TYPE_OID, snmp_cred, transport, _p, deadline, rows, ip, version
    )
    for r in rows:
        idx = r["oid"].rsplit(".", 1)[-1]
        try:
            type_map[idx] = int(r["value"])
        except (ValueError, TypeError):
            continue
    return type_map


def scan_device(ip: str, credential: dict, timeout: int = 5) -> dict:
    rows, filtered_parents = asyncio.run(_walk_all(credential, ip, timeout))
    by_type: dict = {}
    for r in rows:
        by_type.setdefault(r["type"], 0)
        by_type[r["type"]] += 1
    sensor_type_map: dict[str, int] = {}
    if any(r["oid"].startswith(_ENTITY_SENSOR_VALUE_PREFIX) for r in rows):
        try:
            sensor_type_map = asyncio.run(_walk_entity_sensor_type(credential, ip, timeout))
        except Exception:
            logger.warning("entPhySensorType walk 失败，降级为 entity_sensor 兜底 ip=%s", ip, exc_info=True)
            sensor_type_map = {}
    from app.services.monitoring.oid_category_service import categorize_oids, extract_vendor_id
    rows, category_summary = categorize_oids(rows, sensor_type_map=sensor_type_map or None)
    vendor_id = extract_vendor_id(rows)
    return {
        "device_ip": ip,
        "vendor_id": vendor_id,
        "oid_count": len(rows),
        "type_summary": by_type,
        "category_summary": category_summary,
        "filtered_parents": filtered_parents,
        "detected": rows,
        "hint": "将感兴趣的 OID / MIB 符号登记到 monitor_metric_templates 即完成指标接入",
    }


def scan_to_file(ip: str, credential: dict, out_path: str, timeout: int = 5) -> str:
    result = scan_device(ip, credential, timeout)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    return out_path


def _strip_device_ip(result: dict) -> dict:
    return {k: v for k, v in result.items() if k != "device_ip"}


def _rebuild_with_ip(ip: str, capability: dict) -> dict:
    return {**capability, "device_ip": ip}


def scan_device_cached(ip: str, credential: dict, model_key: str | None = None,
                       timeout: int = 5) -> dict:
    cache_key = f"{_MIB_PROBE_CACHE_PREFIX}{ip}"
    try:
        from app.services.scan_redis import get_scan_redis_client
        r = get_scan_redis_client()
        if r is not None:
            cached = r.get(cache_key)
            if cached:
                try:
                    return _rebuild_with_ip(ip, json.loads(cached))
                except (json.JSONDecodeError, TypeError):
                    logger.warning("MIB 探测缓存解析失败，重新探测 key=%s", cache_key)
    except Exception:
        logger.warning("MIB 探测缓存读取失败，降级为直接探测 key=%s", cache_key, exc_info=True)

    result = scan_device(ip, credential, timeout)

    if result.get("oid_count", 0) > 0:
        try:
            from app.services.scan_redis import get_scan_redis_client
            r = get_scan_redis_client()
            if r is not None:
                _write_probe_cache(r, cache_key, _strip_device_ip(result))
        except Exception:
            logger.warning("MIB 探测缓存写入失败 key=%s", cache_key, exc_info=True)
    else:
        logger.warning(
            "MIB 探测返回 0 个 OID，不写缓存（避免污染后续探测）ip=%s", ip
        )

    return result


def _write_probe_cache(r, cache_key: str, result: dict) -> None:
    index_key = f"{_MIB_PROBE_CACHE_PREFIX}index"
    r.set(cache_key, json.dumps(result, ensure_ascii=False), ex=_MIB_PROBE_CACHE_TTL)
    try:
        if not r.sismember(index_key, cache_key):
            if int(r.scard(index_key) or 0) >= _MIB_PROBE_CACHE_MAX_ENTRIES:
                logger.warning(
                    "MIB 探测缓存已达上限 %d，新探测不再登记索引", _MIB_PROBE_CACHE_MAX_ENTRIES,
                )
                return
        r.sadd(index_key, cache_key)
        r.expire(index_key, _MIB_PROBE_CACHE_TTL)
    except Exception:
        logger.warning("MIB 探测缓存索引维护失败", exc_info=True)
