# -*- coding: utf-8 -*-
"""SNMP 快照层：一次读全 → Redis → 离线解析。

方案与实测依据见 ``docs/design/2026-10-09-SNMP快照-一次性读全与离线解析.md``。
本模块只负责**采集与存取**；解析仍在 ``snmp_tables`` / ``snmp_port_collector``
（它们支持注入 ``raw``，注入时零触网）。

要解决的两个结构性问题：

1. **公共表被重复 walk**：``ifName`` 原先在一次扫描里被 7 个调用方各 walk 一次
   （ARP/MAC/LLDP/VLAN/LAG 各自的 ``_ifindex_to_port``、逻辑端口名、端口采集）。
2. **多表同批 walk 让大表收不全**：实测设备 178 —— ``ifStack`` 与 7 张表同批只回
   61 条、单独 walk 119 条；批次里混入一个不响应的 OID 还会让整批全空。

因此采集层**逐表串行**（不再有批次耦合），结果落 Redis；同一轮扫描内的多个能力
共享这一份，I/O 从 7 次降到 1 次。
"""
from __future__ import annotations

import json
import logging

from app.utils.redis_client import get_redis_client
from app.utils import redis_keys

logger = logging.getLogger(__name__)

SNAPSHOT_TTL_SECONDS = 300

SNAPSHOT_VERSION = 2


def snapshot_tables() -> tuple[dict, ...]:
    """解析层与端口采集的并集（按 ``metric_key`` 去重，先出现者生效）。

    运行时合并而非写死一份清单：两个来源各自用**自己的** OID 常量声明（不跨模块
    引用私有名），合并结果即唯一真源 —— 新增表只需在对应文件加一行。
    """
    from app.services.collector import snmp_tables
    from app.services.monitoring.snmp_port_collector import (
        SNAPSHOT_TABLES as PORT_SNAPSHOT_TABLES,
    )

    merged: dict[str, dict] = {}
    for table in (*snmp_tables.SNAPSHOT_TABLES, *PORT_SNAPSHOT_TABLES):
        merged.setdefault(table["metric_key"], table)
    return tuple(merged.values())


def walk_groups(tables: tuple[dict, ...]) -> tuple[dict, ...]:
    """把表清单按 ``(oid, full_index)`` 归并：**同一棵子树只 walk 一次**。

    归并的必要性（不是优化，是正确性）：``entClass`` 与 ``entClass2`` 是**同一个
    OID** 的两个键名（分属 ``collect_device_info_entry`` 与
    ``enrich_device_identity``），索引空间也相同。按 metric_key 各自 walk 会把同一
    棵子树采两遍；按 OID 归并后一次 walk、扇出两个键。

    归并键带上 ``full_index`` 是因为它决定**索引键的形状**（单段 vs 完整尾缀）：
    同 OID 不同 full_index 的两张表必须各走一次，不能归并。
    """
    groups: dict[tuple, dict] = {}
    for table in tables:
        group_key = (table["oid"], bool(table.get("full_index")))
        group = groups.setdefault(
            group_key,
            {
                "oid": table["oid"],
                "full_index": bool(table.get("full_index")),
                "metric_keys": [],
            },
        )
        group["metric_keys"].append(table["metric_key"])
    return tuple(
        {**g, "metric_key": g["metric_keys"][0]} for g in groups.values()
    )


def collect_snapshot(credential: dict, ip: str, timeout: int | None = None,
                     keys: set[str] | frozenset[str] | tuple[str, ...] | None = None) -> dict:
    """逐表 walk 快照表，返回 ``{metric_key: {index: value}}``。

    **逐表串行、单表失败只留空该表**（不抛、不影响其他表）—— 这正是与"一批并发"
    的关键差别：某表不响应时，只有它自己空，不会连累同批的其他表。

    Args:
        keys: **按需子集**。只采这批 metric_key（其余不触网）。本轮扫描只跑
            ARP+MAC 时，不该为 LLDP/VLAN/路由那几十张表付学费 —— 逐表串行的代价
            是**线性**的（实测 ``pysnmp.SnmpEngine()`` 构造 61ms/次，50 张表纯本地
            开销 3.26s），全量采会把小作业放大成重活。步 4 由通道层按本轮能力算出
            需要的键传进来。缺省（None）= 全清单，保持向后兼容。

    Returns:
        快照字典。设备完全不可达时返回的结果各表皆空（调用方按"没采到"处理）。
    """
    from app.services.collector import snmp_tables

    tables = snapshot_tables()
    if keys is not None:
        wanted = set(keys)
        tables = tuple(t for t in tables if t["metric_key"] in wanted)

    snapshot: dict[str, dict] = {}
    for group in walk_groups(tables):
        table = {
            "metric_key": group["metric_key"],
            "oid": group["oid"],
        }
        if group["full_index"]:
            table["full_index"] = True
        try:
            got = snmp_tables.walk_tables(credential, ip, [table], timeout)
        except Exception as exc:  # noqa: BLE001 —— 单表失败不得影响其他表
            logger.warning("快照单表采集失败 metric_key=%s: %s", group["metric_key"], exc)
            table_data: dict = {}
        else:
            table_data = (got or {}).get(group["metric_key"]) or {}
        for metric_key in group["metric_keys"]:
            snapshot[metric_key] = table_data
    return snapshot


def save_snapshot(device_id: int, snapshot: dict) -> bool:
    """写入 Redis。Redis 不可用/写入失败返回 ``False``（调用方无需处理）。"""
    client = get_redis_client()
    if client is None:
        return False
    try:
        payload = json.dumps(
            {"v": SNAPSHOT_VERSION, "tables": snapshot}, ensure_ascii=False,
        )
        client.set(redis_keys.snmp_snapshot_key(device_id), payload, ex=SNAPSHOT_TTL_SECONDS)
        return True
    except Exception as exc:  # noqa: BLE001 —— 缓存写失败不影响本轮采集结果
        logger.warning("快照写入 Redis 失败 device_id=%s: %s", device_id, exc)
        return False


def load_snapshot(device_id: int) -> dict | None:
    """读 Redis 快照。未配置 / 未命中 / 反序列化失败 / 版本不符 ⇒ ``None``。"""
    client = get_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(redis_keys.snmp_snapshot_key(device_id))
    except Exception as exc:  # noqa: BLE001 —— 读失败等同未命中
        logger.warning("快照读取 Redis 失败 device_id=%s: %s", device_id, exc)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("快照反序列化失败（视为未命中）device_id=%s", device_id)
        return None
    if not isinstance(data, dict) or data.get("v") != SNAPSHOT_VERSION:
        logger.info(
            "快照版本不符（视为未命中）device_id=%s got=%s want=%s",
            device_id, (data or {}).get("v") if isinstance(data, dict) else "?",
            SNAPSHOT_VERSION,
        )
        return None
    tables = data.get("tables")
    return tables if isinstance(tables, dict) else None


def clear_snapshot(device_id: int) -> None:
    """清掉某设备的快照（扫描入口调用，强制本轮重新采集）。

    清掉无副作用：下一次调用按未命中处理，重新 walk 一遍。
    """
    client = get_redis_client()
    if client is None:
        return
    try:
        client.delete(redis_keys.snmp_snapshot_key(device_id))
    except Exception as exc:  # noqa: BLE001 —— 清不掉最多是复用旧快照（TTL 会兜底）
        logger.warning("快照清理失败 device_id=%s: %s", device_id, exc)


def snapshot_for(device_id: int, credential: dict, ip: str, *,
                 timeout: int | None = None, force: bool = False,
                 keys: set[str] | frozenset[str] | tuple[str, ...] | None = None) -> dict:
    """取快照：命中缓存直接返回，否则采集并写缓存。

    Redis 不可用（``get_redis_client()`` 返回 ``None``）时**每次现采、不写缓存** ——
    退化为改造前的逐能力直采，不会更差。

    Args:
        keys: 按需子集（透传给 ``collect_snapshot``）。

    > [WARN] **子集与缓存相遇时的正确性约束**：命中缓存时返回的是**上一次**的子集，
    > 可能与本次要的不同。因此调用方要么整轮用同一个 keys（推荐：由扫描入口算一次
    > 本轮需要的能力集合），要么命中后自行判断所需键是否齐全 —— 缺的按缺键回退处理。
    > 这是"共享同一份采集结果"必须付的代价：一份快照不可能同时适配任意子集。
    """
    if not force:
        cached = load_snapshot(device_id)
        if cached is not None:
            return cached
    snapshot = collect_snapshot(credential, ip, timeout, keys=keys)
    save_snapshot(device_id, snapshot)
    return snapshot
