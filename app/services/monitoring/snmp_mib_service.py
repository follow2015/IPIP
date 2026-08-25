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
    """异步读取设备 sysObjectID（1.3.6.1.2.1.1.2.0），返回其 prettyPrint 值。

    sysObjectID 是设备自报的「本设备型号 OID」，形如
    ``SNMPv2-SMI::enterprises.674.10892.5`` 或 ``1.3.6.1.4.1.674.10892.5``。
    它不依赖任何预置品牌知识库，换任何品牌都能读到，用于定位该设备的高价值
    私有指标子树（enterprise 号）。读取失败返回 None（降级为整棵 walk）。
    """
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
    except Exception:  # noqa: BLE001 - 读不到 sysObjectID 不影响探测能力
        logger.warning("读取 sysObjectID 异常 ip=%s", ip, exc_info=True)
        return None
    return None


def _extract_enterprise(sys_object_id_value: str | None) -> str | None:
    """从 sysObjectID 值提取 enterprise 号。

    支持两种形态：
    - ``SNMPv2-SMI::enterprises.674.10892.5`` → "674"
    - ``1.3.6.1.4.1.674.10892.5`` → "674"
    无法解析返回 None。
    """
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
    """对单棵子树做 bulkwalk，把结果追加到 ``rows``，超过 ``deadline`` 时间戳即停。

    返回更新后的 rows（可安全忽略返回值，rows 为原地追加）。
    使用 bulk_walk_cmd（非 next_cmd）：pysnmp v3arch.asyncio 下 next_cmd 返回
    coroutine（无 __aiter__），直接 async for 会报 "'async for' requires an
    object with __aiter__ method"；bulk_walk_cmd（带下划线，非旧名 bulkwalk_cmd）
    返回 async_generator，可直接 async for。

    时间预算替代条数上限：不按 OID 条数截断，按 wall-clock 时间截断，
    保证标准 MIB-2 和厂商私有子树按字典序自然混合 walk，分类靠后端规则匹配。
    """
    iterator = _p.bulk_walk_cmd(
        _p.SnmpEngine(),
        snmp_cred,
        transport,
        _p.ContextData(),
        0, 25,  # non-repeaters=0, max-repetitions=25
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
    """对设备做全量 MIB walk，返回 ``[{oid, type, value}]`` 列表（去重）。

    策略：整棵 ``1.3.6.1`` 一次 walk，标准 MIB-2 和厂商私有子树按字典序自然混合，
    walk 到时间预算耗尽即停。分类靠后端规则匹配（categorize_oids），walk 多少分类多少。

    时间预算替代条数上限：条数上限下厂商私有子树（如华为 2011 ~50000 OID）会占满额度，
    导致标准 MIB-2 完全采不到；时间预算下标准 + 私有按字典序公平 walk，
    标准 MIB-2（1.3.6.1.2.*）在私有子树（1.3.6.1.4.*）之前，必然先采到。
    """
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
    """过滤无监控意义的 OID，保留有指标价值的 OID。

    两类过滤：
    1. net-snmp 内部 MIB 名称映射表（8072.1.2.1.1.4 下的 nsMIBTable）：
       值是 MIB 名字符串（mibII/sysDescr、ip、tcp 等），是 agent 自描述表，无监控价值。
    2. 纯序号表：同一父 OID 下值是连续整数 0,1,2,... 的表（如 nsTransactionTable），
       是表行号索引，无监控价值。仅当≥50 条连续整数才判为序号表，避免误杀小表。
       排除有分类规则的父 OID（如 DELL 温度探针索引表 ...300.40.1.2 有 temperature 规则，
       值 1..386 是探针编号，不应误杀）。
    """
    if not rows:
        return rows, []

    kept: list = []
    for r in rows:
        oid = r["oid"]
        if oid.startswith(_NETSNMP_MIBNAME_PREFIX):
            continue  # net-snmp 内部表，直接过滤
        kept.append(r)

    rule_prefixes: list[str] = []
    try:
        from app.services.monitoring.oid_category_service import _load_rule_prefixes
        rule_prefixes = _load_rule_prefixes()
    except Exception:  # noqa: BLE001 - 规则加载失败降级为不排除（保守不过滤）
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
    """walk entPhySensorType，返回 {index: type_value} 映射。

    用于 ENTITY-SENSOR-MIB 联表细分：entPhySensorValue 只给读数，
    需联表 entPhySensorType 才能判断是温度/电压/风扇/电源。
    设备不支持该 MIB 时返回空 dict。
    """
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
    """对设备做 MIB walk，返回探测清单 dict（可直接序列化 JSON）。

    ``credential`` 为 SNMP 凭据 payload（community 或 v3 字段）。
    """
    rows, filtered_parents = asyncio.run(_walk_all(credential, ip, timeout))
    by_type: dict = {}
    for r in rows:
        by_type.setdefault(r["type"], 0)
        by_type[r["type"]] += 1
    sensor_type_map: dict[str, int] = {}
    if any(r["oid"].startswith(_ENTITY_SENSOR_VALUE_PREFIX) for r in rows):
        try:
            sensor_type_map = asyncio.run(_walk_entity_sensor_type(credential, ip, timeout))
        except Exception:  # noqa: BLE001 - 设备不支持该 MIB 或 walk 失败，降级为不细分
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
    """扫描并写入 JSON 文件，返回文件路径。"""
    result = scan_device(ip, credential, timeout)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    return out_path


def _strip_device_ip(result: dict) -> dict:
    """从探测结果剥离设备 IP（缓存不存设备特有字段，避免跨设备串数据）。

    缓存复用的是「探测能力」（OID 清单），device_ip 是设备特有字段，
    一旦写入缓存，其他设备命中时会拿到错误 IP。故缓存内容与设备 IP 解耦。
    """
    return {k: v for k, v in result.items() if k != "device_ip"}


def _rebuild_with_ip(ip: str, capability: dict) -> dict:
    """用当前设备 IP 覆盖能力，重组为完整探测结果。"""
    return {**capability, "device_ip": ip}


def scan_device_cached(ip: str, credential: dict, model_key: str | None = None,
                       timeout: int = 5) -> dict:
    """对设备做 MIB walk，探测结果按 IP 缓存。

    缓存设计要点（修复跨设备串数据）：
    - 缓存 key **只含 IP**：彻底去掉 model_key（device_model）维度。不同厂商设备
      （如 Dell 674 vs 浪潮）私有子树 OID 天差地别，「按型号复用 OID 能力」本身
      就不成立；且 device_model 常为空/不可靠，作为隔离维度会串数据。按 IP 缓存
      后，同一台设备重复探测命中缓存省一次 walk，不同设备（IP）绝不共享。
    - 缓存内容剥离 device_ip：返回时用当前 IP 覆盖，双保险。

    Args:
        ip: 设备管理 IP（缓存唯一隔离维度）
        credential: SNMP 凭据 payload
        model_key: 已废弃（不再参与缓存 key），保留参数仅为兼容旧调用方
        timeout: 单次探测超时秒数

    Returns:
        dict: 与 ``scan_device`` 同构的探测清单
    """
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
    except Exception:  # noqa: BLE001 - Redis 不可用降级为直接探测
        logger.warning("MIB 探测缓存读取失败，降级为直接探测 key=%s", cache_key, exc_info=True)

    result = scan_device(ip, credential, timeout)

    if result.get("oid_count", 0) > 0:
        try:
            from app.services.scan_redis import get_scan_redis_client
            r = get_scan_redis_client()
            if r is not None:
                _write_probe_cache(r, cache_key, _strip_device_ip(result))
        except Exception:  # noqa: BLE001 - 缓存写入失败不影响探测结果
            logger.warning("MIB 探测缓存写入失败 key=%s", cache_key, exc_info=True)
    else:
        logger.warning(
            "MIB 探测返回 0 个 OID，不写缓存（避免污染后续探测）ip=%s", ip
        )

    return result


def _write_probe_cache(r, cache_key: str, result: dict) -> None:
    """写入探测结果缓存，并对缓存条目数做容量上限控制。

    用一个 Redis set（``monitor:mib-probe:index``）维护所有探测缓存键；
    达到 ``_MIB_PROBE_CACHE_MAX_ENTRIES`` 上限时，仅允许「已存在键」刷新，
    拒绝新增键，避免缓存无限增长。
    """
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
    except Exception:  # noqa: BLE001 - 索引维护失败不影响缓存本身
        logger.warning("MIB 探测缓存索引维护失败", exc_info=True)
