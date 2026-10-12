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

from app.utils.redis_client import get_redis_client
from app.utils import redis_keys
from app.utils.logging import get_logger

logger = get_logger(__name__)

SNAPSHOT_TTL_SECONDS = 300

SNAPSHOT_VERSION = 4

SNAPSHOT_MAX_BYTES = 4 * 1024 * 1024


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


def save_snapshot(device_id: int, snapshot: dict, *,
                  max_bytes: int | None = None) -> bool:
    """写入 Redis。**未写入一律返回 ``False``**（调用方无需处理，见下）。

    返回 ``False`` 的三种情形都是"本轮不共享缓存"，调用方拿到的是**本次实采结果**
    照常返回，因此不影响正确性，只损失本轮复用：

    1. Redis 未配置（``get_redis_client()`` 返回 ``None``）；
    2. 序列化 / 写入抛错；
    3. **超过单键体积上限**（评审 N9，见 :data:`SNAPSHOT_MAX_BYTES`）—— 主动丢弃并
       warning，把"Redis 被顶爆、别处莫名 OOM"换成一条可检索的日志。

    Args:
        max_bytes: 覆盖 :data:`SNAPSHOT_MAX_BYTES`（单测与将来的分层注入用）。
            ``None`` = 用模块常量；``<= 0`` = **豁免**（不做体积判定）。
    """
    client = get_redis_client()
    if client is None:
        return False
    limit = SNAPSHOT_MAX_BYTES if max_bytes is None else int(max_bytes)
    try:
        payload = json.dumps(
            {"v": SNAPSHOT_VERSION, "tables": snapshot}, ensure_ascii=False,
        )
        size = len(payload.encode("utf-8"))
        if limit > 0 and size > limit:
            logger.warning(
                "快照超单键体积上限，本轮**丢弃不写缓存**（退化为直采）device_id=%s "
                "size=%dB limit=%dB tables=%d —— 若为常态请核对设计文档 §5.2 阈值",
                device_id, size, limit, len(snapshot),
            )
            return False
        client.set(redis_keys.snmp_snapshot_key(device_id), payload,
                   ex=SNAPSHOT_TTL_SECONDS)
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
                 keys: set[str] | frozenset[str] | tuple[str, ...] | None = None,
                 max_bytes: int | None = None) -> dict:
    """取快照：命中缓存时**补齐本次缺的键**再返回，否则采集并写缓存。

    Redis 不可用（``get_redis_client()`` 返回 ``None``）时**每次现采、不写缓存** ——
    退化为改造前的逐能力直采，不会更差。

    Args:
        keys: 按需子集（透传给 ``collect_snapshot``）。
        max_bytes: 单键写入上限（透传给 ``save_snapshot``；``None`` = 模块常量）。
            **写不进去不影响返回值** —— 两条写缓存路径都紧跟 ``return``，无论
            ``save_snapshot`` 返回 ``True``/``False``，调用方拿到的都是**本轮完整的
            采集结果**（超限只是"下一轮不共享"，不是"本轮没数据"）。

    > **缺键增量合并（2026-10-10 评审 N5）**：命中缓存但本次 ``keys`` 里有缓存没有的
    > 键时，**只补采这批缺失键**、与已有缓存合并后写回。由此得到两条性质：
    > ① 调用方拿到的字典**一定含本次请求的全部键**（不再出现"命中缓存返回上一轮
    > 子集 ⇒ 解析层逐表缺键回退 ⇒ 共享收益落空"）；
    > ② **本轮内每张表最多 walk 一次**（首采写缓存，后续能力只补自己缺的那几张）。
    >
    > 为什么不是"由扫描入口算一次本轮能力并集再整轮复用"：同一次 ``collect()`` 里
    > 多个能力是**线程池并发**跑的（``BaseChannel.collect``），并发下"都请求并集"
    > 会让每个线程各采一遍全并集（N 倍放大）；而"各自只补自己缺的键"在并发下天然
    > 近似等于并集的最优解（各能力键集基本不相交）。且该实现与调用点数量**解耦**：
    > 新增能力/新增入口都不需要任何人记得去改并集清单。
    >
    > ``keys=None`` 保持历史语义（有缓存就直接用，不判完整性）：全量调用方没有
    > "我缺什么"的判据，且缺键仍由解析层的缺键回退兜底。
    """
    if not force:
        cached = load_snapshot(device_id)
        if cached is not None:
            if keys is None:
                return cached
            missing = frozenset(keys) - set(cached)
            if not missing:
                return cached
            patch = collect_snapshot(credential, ip, timeout, keys=missing)
            merged = {**cached, **patch}
            save_snapshot(device_id, merged, max_bytes=max_bytes)
            return merged
    snapshot = collect_snapshot(credential, ip, timeout, keys=keys)
    save_snapshot(device_id, snapshot, max_bytes=max_bytes)
    return snapshot
