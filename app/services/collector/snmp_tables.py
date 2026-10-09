# -*- coding: utf-8 -*-
"""SNMP 的 ARP / MAC 转发表采集（一次 walk 采全）。


用户判据（2026-10-05）：**SSH 是"逐条命令"付费，SNMP 是"整表 walk"付费** ——
所以"按需获取"是 SSH 的约束，**不该**搬到 SNMP 上。能一次 walk 拿全的表就该一次拿全，
否则无 SSH 设备（SNMP 通道存在的理由）在台账里始终是残缺的。

这些表的共同点：都是**标准 MIB 的表**，一次 bulkwalk 即拿到整机数据，边际成本低。


本模块只负责"表 → 结构化条目"，**不做**过滤/字段命名 —— 那是 `cli_translate` 的职责。
两侧共用同一份翻译规则，才不会出现"CLI 叫 A、SNMP 叫 B"的双真源（R13）。

| 能力 | MIB | 说明 |
|---|---|---|
| ARP | IP-MIB `ipNetToMediaTable`(1.3.6.1.2.1.4.22.1) | 索引 = `ifIndex.IP`（**多段** → 必须 `full_index`） |
| MAC | Q-BRIDGE `dot1qTpFdbTable`(1.3.6.1.2.1.17.7.1.2.2.1) + BRIDGE `dot1dTpFdbTable`(…17.4.3.1) 兜底 | 索引含 VLAN；需 `dot1dBasePortIfIndex` 把 bridge port 换成 ifIndex |

> [WARN] 索引形态差异是这里的**头号坑**：walk 原语默认只取 OID 尾缀最后一段，
> 对 `ifIndex.IP` / `VLAN.MAC` 这类复合索引会让不同条目互相覆盖（见
> `snmp_adapter._snmp_walk_table_async` 的 `full_index` 说明）。
"""
from __future__ import annotations

from typing import Any

from app.services.monitoring.adapters.snmp_adapter import _snmp_collect_metrics

__all__ = [
    "IP_NET_TO_MEDIA_PREFIX",
    "collect_device_info_entry",
    "enrich_device_identity",
    "collect_logical_port_names",
    "collect_route_entries",
    "collect_lldp_entries",
    "collect_arp_entries",
    "collect_mac_entries",
]

IP_NET_TO_MEDIA_PREFIX = "1.3.6.1.2.1.4.22.1"
_IP_NET_IF_INDEX_OID = f"{IP_NET_TO_MEDIA_PREFIX}.1"     # ipNetToMediaIfIndex
_IP_NET_PHYS_ADDR_OID = f"{IP_NET_TO_MEDIA_PREFIX}.2"    # ipNetToMediaPhysAddress
_IP_NET_NET_ADDR_OID = f"{IP_NET_TO_MEDIA_PREFIX}.3"     # ipNetToMediaNetAddress

_DOT1Q_TP_FDB_PORT_OID = "1.3.6.1.2.1.17.7.1.2.2.1.2"    # 索引 = VLAN.MAC，值 = bridge port
_DOT1Q_TP_FDB_STATUS_OID = "1.3.6.1.2.1.17.7.1.2.2.1.3"  # 值 = 状态
_DOT1D_TP_FDB_PORT_OID = "1.3.6.1.2.1.17.4.3.1.2"        # 索引 = MAC，值 = bridge port
_DOT1D_TP_FDB_STATUS_OID = "1.3.6.1.2.1.17.4.3.1.3"
_DOT1D_BASE_PORT_IF_INDEX_OID = "1.3.6.1.2.1.17.1.4.1.2"  # 索引 = bridge port，值 = ifIndex
_IF_NAME_OID = "1.3.6.1.2.1.31.1.1.1.1"                   # ifIndex → 端口名

_FDB_STATUS_MAP = {
    "1": "static",     # other
    "3": "dynamic",    # learned
    "4": "static",     # self
    "5": "static",     # mgmt
}
_FDB_STATUS_SKIP = {"2"}     # invalid：设备已判定该表项无效


def _walk(credential: dict, ip: str, templates: list, timeout: int) -> dict:
    """批量 walk（单事件循环并发）；整体失败返回空 dict。"""
    try:
        return _snmp_collect_metrics(credential, ip, templates, timeout) or {}
    except Exception:  # noqa: BLE001 —— 采集失败一律降级为空（调用方据此标 FAILED/UNSUPPORTED）
        return {}


def walk_tables(credential: dict, ip: str, templates: list,
                timeout: int | None = None) -> dict:
    """公开的批量 walk 入口 —— 供快照层调用（内部即 `_walk`）。

    单独暴露一个公开名，是为了让快照层不必引用私有 `_walk`：跨模块依赖私有名会在
    本文件重构（改名/换实现）时静默炸掉。
    """
    return _walk(credential, ip, templates, int(timeout or 0) or 10)


def _resolve_raw(credential: dict, ip: str, templates: list, timeout: int,
                 raw: dict[str, dict] | None = None) -> dict:
    """解析层注入点：``raw`` **有键（哪怕空 dict）= 信任，缺键 = 只补 walk 缺的那几张**。

    与快照层"单表失败也写空 dict"的约定严格对齐（见 snmp_snapshot.collect_snapshot）：
    键存在 ⇒ 快照本轮真的采过这张表，空 = 设备没这数据；**无键** = 快照没覆盖它
    （keys 子集没带 / 旧版本快照），此时只对缺失的模板补一次 walk，不重采已有的。

    - ``raw is None``：行为与直接 ``_walk`` 逐字等价（既有路径零变化）。
    - 返回**新 dict**（缺键回退时合并），绝不原地改传入的 raw —— 快照是共享缓存，
      把回退补采的结果污染进缓存会让"本轮快照"与"本轮真实采集"混为一谈。
    """
    if raw is None:
        return _walk(credential, ip, templates, timeout)
    missing = [t for t in templates if t.get("metric_key") not in raw]
    if not missing:
        return raw
    merged = dict(raw)
    merged.update(_walk(credential, ip, missing, timeout))
    return merged


def _ifindex_from(raw: dict) -> dict:
    """``raw["ifName"]`` → ``{ifIndex: 端口名}``（纯转换，零触网，注入路径复用）。"""
    return {
        str(k): str(v).strip()
        for k, v in (raw.get("ifName") or {}).items() if str(v).strip()
    }


def _ifindex_to_port(credential: dict, ip: str, timeout: int,
                     raw: dict[str, dict] | None = None) -> dict:
    """ifIndex → 端口名（ARP 的 interface / MAC 的 port 都要用）。

    ``raw`` 提供且含 ``ifName`` 键（哪怕空）⇒ 零触网；缺键则只补 walk 这一张表。
    """
    return _ifindex_from(_resolve_raw(credential, ip, [
        {"metric_key": "ifName", "oid": _IF_NAME_OID},
    ], timeout, raw))


def collect_arp_entries(credential: dict, ip: str, timeout: int | None = None,
                        raw: dict[str, dict] | None = None) -> list[Any]:
    """采 ARP 表，返回 ``ParsedArpEntry`` 列表（供 `translate_arps` 消费）。

    ``raw``：快照注入（``{metric_key: {index: value}}``，None = 自己 walk）。
    语义见 ``_resolve_raw``：有键信任、缺键补 walk。以下各 ``collect_*`` 同。

    `full_index=True`：本表索引是 ``ifIndex.IP`` 两段，只取最后一段会让
    不同 ifIndex 下的条目按 IP 末段互相覆盖（如 192.168.1.10 与 10.1.1.10）。

    诚实的边界：IP-MIB 的 ARP 表**不提供 VLAN**（华为 `display arp` 有 VLAN 列），
    故 `vlan` 留空 —— 这是能力差异，不是 bug，由矩阵档位（PARTIAL）体现。
    """
    from app.adapters.base_adapter import ParsedArpEntry

    timeout = int(timeout or 0) or None
    raw = _resolve_raw(credential, ip, [
        {"metric_key": "arpIfIndex", "oid": _IP_NET_IF_INDEX_OID, "full_index": True},
        {"metric_key": "arpPhysAddr", "oid": _IP_NET_PHYS_ADDR_OID, "full_index": True},
        {"metric_key": "arpNetAddr", "oid": _IP_NET_NET_ADDR_OID, "full_index": True},
    ], timeout or 10, raw)
    if not raw:
        return []

    port_by_index = _ifindex_to_port(credential, ip, timeout or 10, raw)
    from app.services.monitoring.snmp_port_collector import _normalize_mac  # 复用格式归一

    entries: list[Any] = []
    indices = (raw.get("arpIfIndex") or {}).keys() | (raw.get("arpNetAddr") or {}).keys()
    for key in indices:
        ip_text = str(key).rsplit(".", 1)[-1]
        if_index = str((raw.get("arpIfIndex") or {}).get(key) or "").strip()
        net_addr = str((raw.get("arpNetAddr") or {}).get(key) or "").strip() or ip_text
        mac = _normalize_mac((raw.get("arpPhysAddr") or {}).get(key))
        if not net_addr or not mac:
            continue
        entries.append(ParsedArpEntry(
            ip_address=net_addr,
            mac_address=mac,
            vlan=None,                                   # IP-MIB 无 VLAN 信息（如实留空）
            interface=port_by_index.get(if_index) or "",
            type_vlan="",
        ))
    return entries


def collect_mac_entries(credential: dict, ip: str, timeout: int | None = None,
                        raw: dict[str, dict] | None = None) -> list[Any]:
    """采 MAC 转发表，返回 ``ParsedMacEntry`` 列表（供 `translate_macs` 消费）。

    主路径 Q-BRIDGE（索引含 VLAN，能拿到 VLAN）；设备不支持时兜底 BRIDGE-MIB
    （无 VLAN）。两段索引都需 `full_index`，否则不同 VLAN 的同 MAC 会互相覆盖。
    """
    from app.adapters.base_adapter import ParsedMacEntry

    from app.services.monitoring.snmp_port_collector import _normalize_mac

    timeout = int(timeout or 0) or None
    raw = _resolve_raw(credential, ip, [
        {"metric_key": "basePortIfIndex", "oid": _DOT1D_BASE_PORT_IF_INDEX_OID},
    ], timeout or 10, raw)
    base_port = raw.get("basePortIfIndex") or {}
    port_by_index = _ifindex_to_port(credential, ip, timeout or 10, raw)

    raw = _resolve_raw(credential, ip, [
        {"metric_key": "qFdbPort", "oid": _DOT1Q_TP_FDB_PORT_OID, "full_index": True},
        {"metric_key": "qFdbStatus", "oid": _DOT1Q_TP_FDB_STATUS_OID, "full_index": True},
    ], timeout or 10, raw)
    q_port = raw.get("qFdbPort") or {}
    q_status = raw.get("qFdbStatus") or {}

    entries: list[Any] = []
    if q_port:
        for key, bridge_port in q_port.items():
            parts = str(key).split(".")
            if len(parts) < 2:
                continue
            status = str(q_status.get(key) or "").strip()
            if status in _FDB_STATUS_SKIP:
                continue                     # invalid：设备已判定无效，不采进台账（M2）
            vlan_text, mac_text = parts[0], ".".join(parts[1:])
            mac = _normalize_mac_by_dotted(mac_text) or _normalize_mac(mac_text)
            if not mac:
                continue
            if_index = str(base_port.get(str(bridge_port).strip()) or "").strip()
            entries.append(ParsedMacEntry(
                mac_address=mac,
                vlan=vlan_text if vlan_text.isdigit() else None,
                port=port_by_index.get(if_index) or "",
                entry_type=_FDB_STATUS_MAP.get(str(q_status.get(key) or "").strip(), ""),
            ))
        return entries

    raw2 = _resolve_raw(credential, ip, [
        {"metric_key": "dFdbPort", "oid": _DOT1D_TP_FDB_PORT_OID, "full_index": True},
        {"metric_key": "dFdbStatus", "oid": _DOT1D_TP_FDB_STATUS_OID, "full_index": True},
    ], timeout or 10, raw)
    d_status = raw2.get("dFdbStatus") or {}
    for key, bridge_port in (raw2.get("dFdbPort") or {}).items():
        if str(d_status.get(key) or "").strip() in _FDB_STATUS_SKIP:
            continue                         # invalid：跳过（M2）
        mac = _normalize_mac_by_dotted(str(key)) or _normalize_mac(str(key))
        if not mac:
            continue
        if_index = str(base_port.get(str(bridge_port).strip()) or "").strip()
        entries.append(ParsedMacEntry(
            mac_address=mac,
            vlan=None,                                   # BRIDGE-MIB 无 VLAN（如实留空）
            port=port_by_index.get(if_index) or "",
            entry_type=_FDB_STATUS_MAP.get(
                str((raw2.get("dFdbStatus") or {}).get(key) or "").strip(), ""),
        ))
    return entries


def _normalize_mac_by_dotted(dotted: str) -> str | None:
    """``0.17.34.51.68.85``（点分十进制的 6 段 MAC）→ ``0011-2233-4455``。

    BRIDGE-MIB 的 FdbAddress 索引常以点分十进制出现；先把每段转成 2 位十六进制，
    再交给 snmp_port_collector 的归一函数（保证与 CLI 的格式完全一致）。
    """
    parts = [p for p in str(dotted or "").split(".") if p.strip() != ""]
    if len(parts) != 6:
        return None
    try:
        hexes = [f"{int(p):02x}" for p in parts]
    except ValueError:
        return None
    from app.services.monitoring.snmp_port_collector import _normalize_mac

    return _normalize_mac("".join(hexes))


_LLDP_REM_PREFIX = "1.0.8802.1.1.2.1.4.1.1"
_LLDP_REM_LOCAL_PORT_NUM_OID = f"{_LLDP_REM_PREFIX}.2"   # lldpRemLocalPortNum（索引列）
_LLDP_REM_CHASSIS_ID_OID = f"{_LLDP_REM_PREFIX}.5"       # lldpRemChassisId
_LLDP_REM_PORT_ID_OID = f"{_LLDP_REM_PREFIX}.7"          # lldpRemPortId
_LLDP_REM_SYS_NAME_OID = f"{_LLDP_REM_PREFIX}.9"         # lldpRemSysName

_LLDP_REM_MAN_ADDR_PREFIX = "1.0.8802.1.1.2.1.4.2.1"
_LLDP_REM_MAN_ADDR_IF_SUBTYPE_OID = f"{_LLDP_REM_MAN_ADDR_PREFIX}.2"
_LLDP_MAN_ADDR_SUBTYPE_IPV4 = 1

_LLDP_LOC_PORT_ID_OID = "1.0.8802.1.1.2.1.3.7.1.3"
_SYS_DESCR_OID = "1.3.6.1.2.1.1.1.0"
_SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"
_SYS_UPTIME_OID = "1.3.6.1.2.1.1.3.0"
_ENT_PHYSICAL_CLASS_OID = "1.3.6.1.2.1.47.1.1.1.1.5"     # 3 = chassis
_ENT_PHYSICAL_SERIAL_NUM_OID = "1.3.6.1.2.1.47.1.1.1.1.11"
_ENT_PHYSICAL_NAME_OID = "1.3.6.1.2.1.47.1.1.1.1.7"      # entPhysicalName

_ENT_CLASS_CHASSIS = "3"
_ENT_CLASS_MODULE = "9"

_BRAND_PATTERNS = (
    ("huawei", "Huawei"),
    ("h3c", "H3C"),
    ("cisco", "Cisco"),
    ("ruijie", "Ruijie"),
    ("juniper", "Juniper"),
    ("hp", "HPE"),
    ("arista", "Arista"),
)


def _parse_sysdescr(text: str) -> tuple[str, str, str]:
    """从 ``sysDescr`` 启发式解析 ``(brand, model, version)``。

    [WARN] sysDescr 在标准 MIB 里是**自由文本**，各厂商格式不一 —— 这里只做保守
    识别：**认不出就留空**。型号/版本会被写进台账，解析错比留空更难发现
    （错误的型号会让人以为设备是另一台）。

    这也是 DEVICE_INFO 在 SNMP 侧标 PARTIAL 的直接依据。
    """
    import re

    raw = (text or "").strip()
    if not raw:
        return "", "", ""

    if raw.lower().startswith("0x"):
        try:
            raw = bytes.fromhex(raw[2:]).decode("utf-8", errors="replace").strip()
        except ValueError:
            pass
    if not raw:
        return "", "", ""

    lowered = raw.lower()
    brand = ""
    for needle, label in _BRAND_PATTERNS:
        if needle in lowered:
            brand = label
            break

    version = ""
    m_v = re.search(r"\b(V\d+R\d+[A-Z]?\w*)\b", raw)
    if m_v:
        version = m_v.group(1)
    else:
        m = re.search(r"(?:version|vrp version|software version)\s*[v:]?\s*([\w.]+)", lowered)
        if m:
            version = m.group(1)

    model = ""
    m2 = re.search(r"\(([A-Za-z][\w-]*)\s+V\d+", raw)
    if m2:
        model = m2.group(1)
    else:
        stop_words = {
            "software", "platform", "version", "system", "series", "ios", "vrp", "comware",
            "cisco", "huawei", "h3c", "ruijie", "juniper", "networks", "technology",
        }
        for token in re.findall(r"\b([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+)\b", raw):
            first = token.split("-")[0].lower()
            if first in stop_words:
                continue
            if not any(ch.isdigit() for ch in token):
                continue          # 型号必含数字，纯字母串不作数
            model = token
            break
    return brand, model, version


def parse_lldp_man_addr_index(index: str) -> tuple[str, str]:
    """``lldpRemManAddrEntry`` 索引 → ``(邻居键, IPv4 管理地址)``。

    索引形态：``timeMark.localPort.remIndex.manAddrSubtype.a.b.c.d``（IPv4 共 8 段）

    - **邻居键取前三段**：与 ``lldpRemTable`` 的索引对齐，用于把地址回填给同一条邻居。
    - 仅接受 ``manAddrSubtype == 1``（ipv4）且地址恰好 4 段、每段 0~255。
      IPv6（subtype 2）**刻意返回空**：``neighbor_mgmt_ip`` 的消费方是
      ``_resolve_peer_device``（与 ``devices.management_ip`` 比对），现场管理地址是 v4；
      混入 v6 只会让匹配与去重语义变复杂 —— 需要时另开，不在这里"顺手支持"。

    解析不出返回 ``("", "")``（调用方跳过，不猜）。
    """
    parts = str(index or "").split(".")
    if len(parts) != 8:
        return "", ""
    if parts[3] != str(_LLDP_MAN_ADDR_SUBTYPE_IPV4):
        return "", ""
    octets = parts[4:]
    if not all(o.isdigit() and 0 <= int(o) <= 255 for o in octets):
        return "", ""
    return ".".join(parts[:3]), ".".join(octets)


def _lldp_mgmt_addr_by_neighbor(credential: dict, ip: str, timeout: int,
                                raw: dict[str, dict] | None = None) -> dict[str, str]:
    """walk ``lldpRemManAddrTable`` → ``{邻居键: IPv4}``（同邻居多地址取首个 IPv4）。"""
    raw = _resolve_raw(credential, ip, [
        {"metric_key": "lldpManAddr", "oid": _LLDP_REM_MAN_ADDR_IF_SUBTYPE_OID,
         "full_index": True},
    ], timeout, raw).get("lldpManAddr") or {}
    out: dict[str, str] = {}
    for idx, value in raw.items():
        if str(value).strip() == "":
            continue
        neighbor_key, addr = parse_lldp_man_addr_index(str(idx))
        if neighbor_key and addr and neighbor_key not in out:
            out[neighbor_key] = addr
    return out


def collect_lldp_local_port_count(credential: dict, ip: str, timeout: int | None = None,
                                  raw: dict[str, dict] | None = None) -> int | None:
    """本机 LLDP 端口表（``lldpLocPortTable``）条目数 —— "这台设备到底开没开 LLDP"。

    为什么要它：``lldpRemTable`` 为空（无邻居）有两类完全不同的原因，用户在现场
    分不清 —— 一类是"对端没开 LLDP / 不是 LLDP 设备"，另一类是"本机压根没开
    LLDP"。本机表为空 ⇒ 后者（或 SNMP 视图未放行 ``1.0.8802`` 子树）。

    [WARN] 注入语义的边界：直采路径下"walk 失败"（{} 无键）返回 **None**（未判定）；
    快照注入路径下 ``lldpLocPortId`` 键存在（哪怕空）即信任为 **0** —— 快照层把
    "单表失败"也写成空 dict，"采到但空"与"没采到"在快照里无法区分（快照层约定，
    见 snmp_snapshot.collect_snapshot）。这是快照路径的已知精度损耗，换取键齐全。

    Returns:
        条目数（0 表示本机表为空）；**无法判定时返回 None**（采集失败）——
        调用方据此给出"未判定"而不是把"没采到"说成"没启用"。
    """
    raw = _resolve_raw(credential, ip, [
        {"metric_key": "lldpLocPortId", "oid": _LLDP_LOC_PORT_ID_OID},
    ], int(timeout or 0) or 10, raw)
    if not raw:
        return None
    table = raw.get("lldpLocPortId")
    if table is None:
        return None
    return len(table)


def collect_lldp_entries(credential: dict, ip: str, timeout: int | None = None,
                         raw: dict[str, dict] | None = None) -> list[Any]:
    """LLDP 邻居表（索引 = timeMark.localPort.remIndex **多段** → full_index）。

    与 CLI 侧一样**不做 CDP 回退**（那是拓扑服务的编排行为，`protocol` 字段已预留
    来源标注）。

    2026-10-07 补采 ``lldpRemManAddrTable`` 填 ``neighbor_mgmt_ip``（此前为空）：
    对端匹配由此从 sysname 升级为管理 IP。**剩余差异**：只取 IPv4 管理地址
    （IPv6 见 ``parse_lldp_man_addr_index``），故矩阵档位仍为 PARTIAL。
    """
    from app.adapters.base_adapter import ParsedLldpNeighbor

    timeout = int(timeout or 0) or None
    raw = _resolve_raw(credential, ip, [
        {"metric_key": "lldpLocalPort", "oid": _LLDP_REM_LOCAL_PORT_NUM_OID,
         "full_index": True},
        {"metric_key": "lldpChassisId", "oid": _LLDP_REM_CHASSIS_ID_OID,
         "full_index": True},
        {"metric_key": "lldpPortId", "oid": _LLDP_REM_PORT_ID_OID, "full_index": True},
        {"metric_key": "lldpSysName", "oid": _LLDP_REM_SYS_NAME_OID, "full_index": True},
    ], timeout or 10, raw)
    local_port = raw.get("lldpLocalPort") or {}
    if not local_port:
        return []

    mgmt_by_neighbor = _lldp_mgmt_addr_by_neighbor(credential, ip, timeout or 10, raw)

    port_by_index = _ifindex_to_port(credential, ip, timeout or 10, raw)
    raw = _resolve_raw(credential, ip, [
        {"metric_key": "basePortIfIndex", "oid": _DOT1D_BASE_PORT_IF_INDEX_OID},
    ], timeout or 10, raw)
    base_port = raw.get("basePortIfIndex") or {}

    entries: list[Any] = []
    for key, port_num in local_port.items():
        port_num = str(port_num).strip()
        local_name = port_by_index.get(port_num) or port_by_index.get(
            str(base_port.get(port_num) or "").strip(), ""
        )
        if not local_name:
            continue
        entries.append(ParsedLldpNeighbor(
            local_port=local_name,
            neighbor_sysname=str((raw.get("lldpSysName") or {}).get(key) or "").strip(),
            neighbor_port=str((raw.get("lldpPortId") or {}).get(key) or "").strip(),
            neighbor_mgmt_ip=mgmt_by_neighbor.get(str(key), ""),
            chassis_id=str((raw.get("lldpChassisId") or {}).get(key) or "").strip(),
            protocol="lldp",
        ))
    return entries


def _model_prefix(model: str) -> str:
    """型号的前导"字母+数字"主干（``CE6850HI`` → ``CE6850``），用于实体名比对。

    为什么不去比完整型号：同一台设备在 sysDescr 里叫 ``CE6850HI``，在
    ``entPhysicalName`` 里叫 ``CE6850-48S6Q-HI``（带端口规格），二者不可能全等。
    前导主干是唯一稳定的交集。取不出主干（型号里没有数字）就返回空，调用方据此
    放弃匹配 —— 保守优于猜。
    """
    import re

    m = re.match(r"^([A-Za-z]+\d+)", (model or "").strip())
    return m.group(1).upper() if m else ""


def _pick_chassis_serial(
    classes: dict, serials: dict, names: dict, model: str = ""
) -> str:
    """从 ``entPhysicalTable`` 挑**整机**序列号。宁空勿错。

    两级判据：

    1. **标准优先**：``entPhysicalClass == 3``（chassis）且序列号非空的那一行的值。
    2. **堆叠/虚拟框回退**：chassis 行存在但序列号为**空白**时，退到
       ``entPhysicalClass == 9``（module）。

    为什么需要第 2 级（2026-10-07 实测，设备 178 华为 CE6850HI）：堆叠场景下
    chassis 是 ``virtual frame``（虚拟框）**没有序列号**，整机 ESN 挂在唯一的
    module 行上（``class=9``，name=``CE6850-48S6Q-HI 1``，serial=``210235…0667``）。
    只看 chassis 会让这类设备的序列号永远为空 —— 而 SSH 侧靠 ``display esn``
    拿得到，SNMP 因此对不齐。

    回退的**两道闸**（缺一即留空，理由与当初删掉"取第一个非空序列号"兜底相同：
    电源/风扇/板卡各有序列号，写错比留空更难发现）：

    - module 行**必须唯一**：框式交换机（S12700 一类）有多块业务板，多于一行时
      无从判断哪块是整机 —— 宁空。
    - 该行 name 必须**含型号主干**：单行的也可能是板卡（如 ``LPUF-100``），
      型号对不上就不认。
    """

    def _text(v: object) -> str:
        return str(v or "").strip()

    chassis_seen = False
    for index, value in (serials or {}).items():
        text = _text(value)
        if _text((classes or {}).get(index)) != _ENT_CLASS_CHASSIS:
            continue
        chassis_seen = True
        if text:
            return text
    if not chassis_seen:
        return ""

    prefix = _model_prefix(model)
    if not prefix:
        return ""
    candidates = [
        (index, _text(value))
        for index, value in (serials or {}).items()
        if _text(value) and _text((classes or {}).get(index)) == _ENT_CLASS_MODULE
    ]
    if len(candidates) != 1:
        return ""
    index, text = candidates[0]
    import re

    label = re.sub(r"[^0-9A-Za-z]", "", _text((names or {}).get(index))).upper()
    if prefix not in label:
        return ""
    return text


def collect_device_info_entry(credential: dict, ip: str, timeout: int | None = None,
                              raw: dict[str, dict] | None = None) -> Any:
    """设备信息：sysDescr（型号/版本/品牌）+ sysName（主机名）+ sysUpTime + 机箱序列号。

    ``sysUpTime`` 复用监控侧既有原语 ``_snmp_get_sysuptime``；序列号走 ENTITY-MIB 的
    ``entPhysicalSerialNum`` 并挑 ``entPhysicalClass == 3``（chassis）的那一行 ——
    不挑会有多个模块序列号，选错会写进台账。堆叠/虚拟框的回退见
    ``_pick_chassis_serial``。

    ``sysUpTime`` 的注入：快照清单里是**标量 get**（OID 带 .0，walk 原语对 .0 标量
    自动降级为 get_cmd，产出 ``{"0": 值}``），键存在即直接取值（零触网）；
    缺键（keys 子集没带 / 旧版本快照）回落 GET 原语。两条路径产出**同一个字符串**
    （TimeTicks 的 prettyPrint 与 str(int) 逐字相同，2026-10-09 实测 pysnmp 7.1.27）。
    """
    from app.adapters.base_adapter import ParsedDeviceInfo

    timeout = int(timeout or 0) or None
    raw = _resolve_raw(credential, ip, [
        {"metric_key": "sysDescr", "oid": _SYS_DESCR_OID},
        {"metric_key": "sysName", "oid": _SYS_NAME_OID},
        {"metric_key": "entClass", "oid": _ENT_PHYSICAL_CLASS_OID},
        {"metric_key": "entSerial", "oid": _ENT_PHYSICAL_SERIAL_NUM_OID},
        {"metric_key": "entName", "oid": _ENT_PHYSICAL_NAME_OID},
    ], timeout or 10, raw)

    descr = str((raw.get("sysDescr") or {}).get("0") or "").strip()
    brand, model, version = _parse_sysdescr(descr)

    serial = _pick_chassis_serial(
        raw.get("entClass") or {}, raw.get("entSerial") or {},
        raw.get("entName") or {}, model,
    )
    uptime = ""
    if "sysUpTime" in raw:
        uptime = str((raw.get("sysUpTime") or {}).get("0") or "").strip()
    else:
        try:
            from app.services.monitoring.adapters.snmp_adapter import _snmp_get_sysuptime

            ok, uptime_val, _err = _snmp_get_sysuptime(credential, ip, timeout or 10)
            if ok and uptime_val:
                uptime = str(uptime_val).strip()
        except Exception:  # noqa: BLE001 —— uptime 取不到不影响其它字段
            uptime = ""

    return ParsedDeviceInfo(
        model=model,
        version=version,
        serial=serial,
        uptime=uptime,
        hostname=str((raw.get("sysName") or {}).get("0") or "").strip(),
        brand=brand,
    )


_IP_CIDR_ROUTE_PREFIX = "1.3.6.1.2.1.4.24.4.1"
_IP_CIDR_ROUTE_DEST_OID = f"{_IP_CIDR_ROUTE_PREFIX}.1"
_IP_CIDR_ROUTE_MASK_OID = f"{_IP_CIDR_ROUTE_PREFIX}.2"
_IP_CIDR_ROUTE_NEXT_HOP_OID = f"{_IP_CIDR_ROUTE_PREFIX}.4"
_IP_CIDR_ROUTE_IF_INDEX_OID = f"{_IP_CIDR_ROUTE_PREFIX}.5"
_IP_CIDR_ROUTE_PROTO_OID = f"{_IP_CIDR_ROUTE_PREFIX}.7"
_IP_ROUTE_PREFIX = "1.3.6.1.2.1.4.21.1"
_IP_ROUTE_DEST_OID = f"{_IP_ROUTE_PREFIX}.1"
_IP_ROUTE_NEXT_HOP_OID = f"{_IP_ROUTE_PREFIX}.7"
_IP_ROUTE_TYPE_OID = f"{_IP_ROUTE_PREFIX}.8"
_IP_ROUTE_PROTO_OID = f"{_IP_ROUTE_PREFIX}.9"
_IP_ROUTE_MASK_OID = f"{_IP_ROUTE_PREFIX}.11"

_ROUTE_PROTO_MAP = {
    "1": "other", "2": "local", "3": "netmgmt", "4": "icmp", "5": "egp",
    "6": "ggp", "7": "hello", "8": "rip", "9": "isIs", "10": "esIs",
    "11": "ciscoIgrp", "12": "bbnSpfIgp", "13": "ospf", "14": "bgp",
    "15": "idpr", "16": "ciscoEigrp", "17": "dvmrp",
}


def _cidr(dest: str, mask: str) -> str:
    """``目的地址 + 掩码`` → CIDR 串（拼不出来就返回原目的地址）。"""
    import ipaddress

    dest = (dest or "").strip()
    mask = (mask or "").strip()
    if not dest or not mask:
        return dest
    try:
        return str(ipaddress.IPv4Network(f"{dest}/{mask}", strict=False))
    except ValueError:
        return dest


def collect_route_entries(credential: dict, ip: str, timeout: int | None = None,
                          raw: dict[str, dict] | None = None) -> list[Any]:
    """路由表（一次 walk 采全），产出 ``ParsedRoute``（与 CLI 共用 translate_routes）。

    主用 ``ipCidrRouteTable``（索引 = dest.mask.tos.nexthop **多段** → full_index）；
    设备不实现时兜底 RFC1213 ``ipRouteTable``（索引 = dest，同样是多段）。
    """
    from app.adapters.base_adapter import ParsedRoute

    timeout = int(timeout or 0) or None
    raw = _resolve_raw(credential, ip, [
        {"metric_key": "cidrDest", "oid": _IP_CIDR_ROUTE_DEST_OID, "full_index": True},
        {"metric_key": "cidrMask", "oid": _IP_CIDR_ROUTE_MASK_OID, "full_index": True},
        {"metric_key": "cidrNextHop", "oid": _IP_CIDR_ROUTE_NEXT_HOP_OID, "full_index": True},
        {"metric_key": "cidrIfIndex", "oid": _IP_CIDR_ROUTE_IF_INDEX_OID, "full_index": True},
        {"metric_key": "cidrProto", "oid": _IP_CIDR_ROUTE_PROTO_OID, "full_index": True},
    ], timeout or 10, raw)
    cidr_dest = raw.get("cidrDest") or {}

    port_by_index: dict = {}
    if cidr_dest:
        port_by_index = _ifindex_to_port(credential, ip, timeout or 10, raw)

    entries: list[Any] = []
    if cidr_dest:
        for key in cidr_dest:
            dest = str((raw.get("cidrDest") or {}).get(key) or "").strip()
            mask = str((raw.get("cidrMask") or {}).get(key) or "").strip()
            if_index = str((raw.get("cidrIfIndex") or {}).get(key) or "").strip()
            proto = str((raw.get("cidrProto") or {}).get(key) or "").strip()
            entries.append(ParsedRoute(
                network=_cidr(dest, mask),
                nexthop=str((raw.get("cidrNextHop") or {}).get(key) or "").strip(),
                interface=port_by_index.get(if_index) or "",
                flags=_ROUTE_PROTO_MAP.get(proto, ""),
                protocol=_ROUTE_PROTO_MAP.get(proto, ""),
            ))
        return entries

    raw2 = _resolve_raw(credential, ip, [
        {"metric_key": "rDest", "oid": _IP_ROUTE_DEST_OID, "full_index": True},
        {"metric_key": "rNextHop", "oid": _IP_ROUTE_NEXT_HOP_OID, "full_index": True},
        {"metric_key": "rType", "oid": _IP_ROUTE_TYPE_OID, "full_index": True},
        {"metric_key": "rProto", "oid": _IP_ROUTE_PROTO_OID, "full_index": True},
        {"metric_key": "rMask", "oid": _IP_ROUTE_MASK_OID, "full_index": True},
    ], timeout or 10, raw)
    r_dest = raw2.get("rDest") or {}
    if r_dest:
        port_by_index = _ifindex_to_port(credential, ip, timeout or 10, raw2)
        for key in r_dest:
            dest = str((raw2.get("rDest") or {}).get(key) or "").strip()
            mask = str((raw2.get("rMask") or {}).get(key) or "").strip()
            proto = str((raw2.get("rProto") or {}).get(key) or "").strip()
            entries.append(ParsedRoute(
                network=_cidr(dest, mask),
                nexthop=str((raw2.get("rNextHop") or {}).get(key) or "").strip(),
                interface="",
                flags=_ROUTE_PROTO_MAP.get(proto, ""),
                protocol=_ROUTE_PROTO_MAP.get(proto, ""),
            ))
    return entries


def collect_logical_port_names(credential: dict, ip: str,
                               timeout: int | None = None,
                               raw: dict[str, dict] | None = None) -> dict:
    """从 ``ifName`` 全表里筛出 **Vlanif / Eth-Trunk** 这类逻辑端口名。

    为什么需要：SNMP 的端口采集会**主动跳过**逻辑端口（它们的 link_status 不代表
    物理链路），于是接管路径拿不到 `Vlanif100`、`Eth-Trunk1` 这类名字 —— 而
    `_sync_vlan_trunk_bases` 正是靠**端口名**建 vlans / link_aggregation_groups
    基础记录的。逻辑端口名只需再筛一次 ifName 表（walk 已有开销，这里不新增请求）。

    判据复用：正则直接引自 `switch_info_service.VLAN_PORT_NAME_RE` /
    `LAG_PORT_NAME_RE` —— 与 CLI 路径同一份，不抄第二份。
    """
    from app.services.switch_info_service import (
        LAG_PORT_NAME_RE,
        VLAN_PORT_NAME_RE,
    )

    timeout = int(timeout or 0) or None
    names = _ifindex_to_port(credential, ip, timeout or 10, raw).values()
    vlan_names, lag_names = [], []
    for name in names:
        if not name:
            continue
        if VLAN_PORT_NAME_RE.match(name):
            vlan_names.append(name)
        elif LAG_PORT_NAME_RE.match(name):
            lag_names.append(name)
    return {"vlan_names": sorted(set(vlan_names)), "lag_names": sorted(set(lag_names))}


_SYS_OBJ_ID_OID = "1.3.6.1.2.1.1.2.0"
_ENT_PHYSICAL_MODEL_NAME_OID = "1.3.6.1.2.1.47.1.1.1.1.13"   # 3 = chassis
_ENT_PHYSICAL_HW_REV_OID = "1.3.6.1.2.1.47.1.1.1.1.9"

_SYS_OBJECT_ID_BRAND = (
    ("1.3.6.1.4.1.2011", "Huawei"),
    ("1.3.6.1.4.1.25506", "H3C"),
    ("1.3.6.1.4.1.9", "Cisco"),
    ("1.3.6.1.4.1.48690", "Ruijie"),
    ("1.3.6.1.4.1.2636", "Juniper"),
)


def enrich_device_identity(info: Any, credential: dict, ip: str,
                           timeout: int | None = None,
                           raw: dict[str, dict] | None = None) -> Any:
    """用 **sysObjectID + ENTITY-MIB 型号名** 增强设备身份（比 sysDescr 启发式可靠）。

    - brand：sysObjectID 的企业号前缀（权威，驱动回填就用它）；
    - model：ENTITY-MIB ``entPhysicalModelName``（chassis 行，结构化），
      空时回落到既有 sysDescr 启发式结果。

    依赖 `collect_device_info_entry` 先跑过（提供 sysDescr 初值与序列号基数）。
    """
    timeout = int(timeout or 0) or None
    raw = _resolve_raw(credential, ip, [
        {"metric_key": "sysObjectID", "oid": _SYS_OBJ_ID_OID},
        {"metric_key": "entModelName", "oid": _ENT_PHYSICAL_MODEL_NAME_OID},
        {"metric_key": "entClass2", "oid": _ENT_PHYSICAL_CLASS_OID},
    ], timeout or 10, raw)

    obj_id = str((raw.get("sysObjectID") or {}).get("0") or "").strip()
    for prefix, label in _SYS_OBJECT_ID_BRAND:
        if obj_id.startswith(prefix):
            info.brand = label
            break

    classes = raw.get("entClass2") or {}
    for index, value in (raw.get("entModelName") or {}).items():
        name = str(value or "").strip()
        if name and str(classes.get(index, "")).strip() in ("3", "chassis"):
            if not info.model:
                info.model = name
            break
    return info



_DOT1Q_VLAN_STATIC_PREFIX = "1.3.6.1.2.1.17.7.1.4.3.1"
_DOT1Q_VLAN_STATIC_NAME_OID = f"{_DOT1Q_VLAN_STATIC_PREFIX}.1"      # dot1qVlanStaticName
_DOT1Q_VLAN_STATIC_EGRESS_OID = f"{_DOT1Q_VLAN_STATIC_PREFIX}.2"    # dot1qVlanStaticEgressPorts
_DOT1Q_VLAN_CURRENT_EGRESS_OID = "1.3.6.1.2.1.17.7.1.4.2.1.4"



def parse_vlan_port_bitmap(value: Any) -> list[int]:
    """``dot1qVlan*EgressPorts`` 的端口位图 → ifIndex 列表（**bit 0 对应 ifIndex 1**）。

    实测形态（设备 178）：pysnmp 对 OctetString 的 prettyPrint 给
    ``0xffffffffffff0000...`` —— 与 sysDescr 一样带 ``0x`` 前缀，必须先剥掉再解
    hex，否则 ``bytes.fromhex`` 直接 ValueError、整个能力静默退化成 EMPTY。
    """
    text = str(value or "").strip()
    if text.lower().startswith("0x"):
        text = text[2:]
    if not text:
        return []
    try:
        raw = bytes.fromhex(text)
    except ValueError:
        import logging

        logging.getLogger(__name__).warning(
            "VLAN 端口位图无法解析（非 hex 形态）: %r", str(value)[:48]
        )
        return []
    ifindexes: list[int] = []
    for byte_idx, byte in enumerate(raw):
        for bit in range(8):
            if byte & (0x80 >> bit):
                ifindexes.append(byte_idx * 8 + bit + 1)
    return ifindexes


def collect_vlan_entries(credential: dict, ip: str,
                         timeout: int | None = None,
                         raw: dict[str, dict] | None = None) -> list[dict]:
    """VLAN 及其成员端口：``[{"vlan_id", "name", "members": [端口名]}]``。

    位图给出的是 **ifIndex 集合**，再经 ifName 表换成端口名 —— 与 CLI 侧
    ``display vlan`` 的产出同语义（成员=端口名），Phase 0d 的 ``sync_vlan_members``
    可直接消费。

    两张表都采：``dot1qVlanCurrentEgressPorts``（含动态学到的）优先，
    ``dot1qVlanStaticEgressPorts`` 补齐只有配置的那些。两者索引形态不同
    （current 带 timeMark 前缀），统一取**末段**作 vlan id。
    """
    timeout = int(timeout or 0) or None
    raw = _resolve_raw(credential, ip, [
        {"metric_key": "vlanName", "oid": _DOT1Q_VLAN_STATIC_NAME_OID},
        {"metric_key": "vlanStaticEgress", "oid": _DOT1Q_VLAN_STATIC_EGRESS_OID,
         "full_index": True},
        {"metric_key": "vlanCurrentEgress", "oid": _DOT1Q_VLAN_CURRENT_EGRESS_OID,
         "full_index": True},
    ], timeout or 10, raw)

    egress: dict[str, Any] = {}
    for key, val in (raw.get("vlanCurrentEgress") or {}).items():
        egress.setdefault(str(key).split(".")[-1], val)
    for key, val in (raw.get("vlanStaticEgress") or {}).items():
        egress.setdefault(str(key).split(".")[-1], val)
    if not egress:
        return []

    names = raw.get("vlanName") or {}
    port_by_index = _ifindex_to_port(credential, ip, timeout or 10, raw)

    entries: list[dict] = []
    for key, bitmap in egress.items():
        try:
            vlan_id = int(key)
        except (TypeError, ValueError):
            continue
        members = [
            name for name in (
                port_by_index.get(str(idx)) for idx in parse_vlan_port_bitmap(bitmap)
            ) if name
        ]
        entries.append({
            "vlan_id": vlan_id,
            "name": str(names.get(key) or "").strip(),
            "members": members,
        })
    entries.sort(key=lambda item: item["vlan_id"])
    return entries



_LAG_MIB_PREFIX = "1.2.840.10006.300.43"
_DOT3AD_AGG_PORT_PREFIX = f"{_LAG_MIB_PREFIX}.1.2.1.1"
_DOT3AD_AGG_PORT_ATTACHED_AGG_ID_OID = f"{_DOT3AD_AGG_PORT_PREFIX}.13"   # → 聚合器 ifIndex
_DOT3AD_AGG_PORT_ACTOR_OPER_STATE_OID = f"{_DOT3AD_AGG_PORT_PREFIX}.21"  # LacpState
_DOT3AD_AGG_PORT_PARTNER_OPER_STATE_OID = f"{_DOT3AD_AGG_PORT_PREFIX}.23"
_DOT3AD_AGG_PORT_LIST_OID = f"{_LAG_MIB_PREFIX}.1.1.1.1.10"
_IF_STACK_STATUS_OID = "1.3.6.1.2.1.31.1.2.1.3"
_IF_HIGH_SPEED_OID = "1.3.6.1.2.1.31.1.1.1.15"
_IF_OPER_STATUS_OID = "1.3.6.1.2.1.2.2.1.8"

_LACP_STATE_BITS = (
    ("activity", 0x80),
    ("timeout", 0x40),
    ("aggregation", 0x20),
    ("synchronized", 0x10),
    ("collecting", 0x08),
    ("distributing", 0x04),
    ("defaulted", 0x02),
    ("expired", 0x01),
)


def parse_lacp_state(value: Any) -> dict[str, bool]:
    """LACP ``LacpState`` 位图 → 具名字段。

    形态兼容两种：pysnmp 的 ``0x3d``（hex 串）与裸整数 ``61``。多字节取**首字节**
    （LacpState 定义为 OCTET STRING，状态在第一个字节）。解析不出返回空 dict ——
    状态是附加信息，缺了不影响成员关系落地。
    """
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        if text.lower().startswith("0x"):
            body = text[2:]
            byte = int(body[:2], 16) if len(body) >= 2 else int(body or "0", 16)
        else:
            byte = int(text)
    except ValueError:
        return {}
    return {name: bool(byte & mask) for name, mask in _LACP_STATE_BITS}


def _finalize_lag_groups(groups: dict, high_speed: dict, oper_status: dict) -> list[dict]:
    """补速率/状态、排序并输出（两条路径共用，避免收尾逻辑抄两份）。"""
    entries: list[dict] = []
    for agg_idx, group in groups.items():
        speed = high_speed.get(agg_idx)
        try:
            group["speed_mbps"] = int(str(speed).strip()) if speed is not None else None
        except (TypeError, ValueError):
            group["speed_mbps"] = None
        status = oper_status.get(agg_idx)
        group["oper_status"] = str(status).strip() if status is not None else None
        group["members"].sort()
        entries.append(group)
    entries.sort(key=lambda e: (e["lag_index"] is None, e["lag_index"] or 0))
    return entries


def collect_lag_entries(credential: dict, ip: str,
                        timeout: int | None = None,
                        raw: dict[str, dict] | None = None) -> list[dict]:
    """链路聚合组与成员：**不需要 SSH**（IEEE8023-LAG-MIB + ifName/ifXTable）。

    成员关系来自 ``dot3adAggPortAttachedAggID``：索引是**成员端口** ifIndex，值是
    **聚合器** ifIndex（``0`` = 该端口未加入任何聚合组）。两侧 ifIndex 都经 ifName
    换成端口名 —— 于是得到「聚合口名 → [成员端口名]」，与 CLI 侧 ``display eth-trunk``
    的产出同语义，``sync_trunk_members`` 可直接消费。

    聚合口名**直接取设备自报的 ifName**（Eth-Trunk1 / Bridge-Aggregation1…），
    不按编号反推 —— 反推会与厂商命名漂移。

    返回每行：``{"lag_index", "lag_name", "members", "member_states",
    "speed_mbps", "oper_status"}``。
    """
    timeout = int(timeout or 0) or None
    raw = _resolve_raw(credential, ip, [
        {"metric_key": "ifName", "oid": _IF_NAME_OID},
        {"metric_key": "attachedAggID", "oid": _DOT3AD_AGG_PORT_ATTACHED_AGG_ID_OID},
        {"metric_key": "actorState", "oid": _DOT3AD_AGG_PORT_ACTOR_OPER_STATE_OID},
        {"metric_key": "partnerState", "oid": _DOT3AD_AGG_PORT_PARTNER_OPER_STATE_OID},
        {"metric_key": "ifHighSpeed", "oid": _IF_HIGH_SPEED_OID},
        {"metric_key": "ifOperStatus", "oid": _IF_OPER_STATUS_OID},
        {"metric_key": "aggPortList", "oid": _DOT3AD_AGG_PORT_LIST_OID},
    ], timeout or 10, raw)

    attached = raw.get("attachedAggID") or {}
    port_list = raw.get("aggPortList") or {}

    names = {str(k): str(v).strip()
             for k, v in (raw.get("ifName") or {}).items() if str(v).strip()}
    actor = raw.get("actorState") or {}
    from app.services.switch_info_service import LAG_PORT_NAME_RE

    has_lag_port = any(LAG_PORT_NAME_RE.match(v) for v in names.values())
    if not attached and not port_list and not has_lag_port:
        return []  # 连聚合口都没有 / 未开放 1.2.840 子树 ⇒ EMPTY

    partner = raw.get("partnerState") or {}
    high_speed = raw.get("ifHighSpeed") or {}
    oper_status = raw.get("ifOperStatus") or {}

    groups: dict[str, dict] = {}
    for idx, agg in attached.items():
        agg_idx = str(agg).strip()
        if agg_idx in ("", "0"):
            continue
        member = names.get(str(idx))
        if not member:
            continue  # 宁缺勿错：不拿 ifIndex 冒充端口名
        group = groups.setdefault(agg_idx, {
            "lag_index": int(agg_idx) if agg_idx.isdigit() else None,
            "lag_name": names.get(agg_idx) or "",
            "members": [],
            "member_states": {},
            "speed_mbps": None,
            "oper_status": None,
        })
        group["members"].append(member)
        group["member_states"][member] = {
            "actor": parse_lacp_state(actor.get(str(idx))),
            "partner": parse_lacp_state(partner.get(str(idx))),
        }

    for agg_idx, bitmap in port_list.items():
        key = str(agg_idx).strip()
        if key in groups:
            continue  # LACP 路径已建组，不重复
        members = sorted(
            name for name in (names.get(str(i)) for i in parse_vlan_port_bitmap(bitmap))
            if name
        )
        if not members:
            continue
        groups[key] = {
            "lag_index": int(key) if key.isdigit() else None,
            "lag_name": names.get(key) or "",
            "members": members,
            "member_states": {},
            "speed_mbps": None,
            "oper_status": None,
        }

    if_stack: dict = {}
    if has_lag_port:
        if_stack = (
            _resolve_raw(credential, ip, [
                {"metric_key": "ifStack", "oid": _IF_STACK_STATUS_OID, "full_index": True},
            ], timeout or 10, raw).get("ifStack") or {}
        )
    for key, status in if_stack.items():
        parts = str(key).split(".")
        if len(parts) < 2:
            continue
        higher, lower = parts[0], parts[1]
        if lower in ("", "0") or higher in ("", "0"):
            continue
        if str(status).strip() != "1":
            continue
        higher_name = names.get(higher) or ""
        if not LAG_PORT_NAME_RE.match(higher_name):
            continue  # 上层不是聚合口（多半是普通接口的层级关系）
        member = names.get(lower)
        if not member:
            continue
        group = groups.get(higher)
        if group is None:
            group = {
                "lag_index": int(higher) if higher.isdigit() else None,
                "lag_name": higher_name,
                "members": [],
                "member_states": {},
                "speed_mbps": None,
                "oper_status": None,
            }
            groups[higher] = group
        if member not in group["members"]:
            group["members"].append(member)

    return _finalize_lag_groups(groups, high_speed, oper_status)



SNAPSHOT_TABLES: tuple[dict, ...] = (
    {"metric_key": "ifName", "oid": _IF_NAME_OID},
    {"metric_key": "arpIfIndex", "oid": _IP_NET_IF_INDEX_OID, "full_index": True},
    {"metric_key": "arpPhysAddr", "oid": _IP_NET_PHYS_ADDR_OID, "full_index": True},
    {"metric_key": "arpNetAddr", "oid": _IP_NET_NET_ADDR_OID, "full_index": True},
    {"metric_key": "qFdbPort", "oid": _DOT1Q_TP_FDB_PORT_OID, "full_index": True},
    {"metric_key": "qFdbStatus", "oid": _DOT1Q_TP_FDB_STATUS_OID, "full_index": True},
    {"metric_key": "dFdbPort", "oid": _DOT1D_TP_FDB_PORT_OID, "full_index": True},
    {"metric_key": "dFdbStatus", "oid": _DOT1D_TP_FDB_STATUS_OID, "full_index": True},
    {"metric_key": "basePortIfIndex", "oid": _DOT1D_BASE_PORT_IF_INDEX_OID},
    {"metric_key": "lldpLocalPort", "oid": _LLDP_REM_LOCAL_PORT_NUM_OID, "full_index": True},
    {"metric_key": "lldpChassisId", "oid": _LLDP_REM_CHASSIS_ID_OID, "full_index": True},
    {"metric_key": "lldpPortId", "oid": _LLDP_REM_PORT_ID_OID, "full_index": True},
    {"metric_key": "lldpSysName", "oid": _LLDP_REM_SYS_NAME_OID, "full_index": True},
    {"metric_key": "lldpManAddr", "oid": _LLDP_REM_MAN_ADDR_IF_SUBTYPE_OID, "full_index": True},
    {"metric_key": "lldpLocPortId", "oid": _LLDP_LOC_PORT_ID_OID},
    {"metric_key": "vlanName", "oid": _DOT1Q_VLAN_STATIC_NAME_OID},
    {"metric_key": "vlanStaticEgress", "oid": _DOT1Q_VLAN_STATIC_EGRESS_OID, "full_index": True},
    {"metric_key": "vlanCurrentEgress", "oid": _DOT1Q_VLAN_CURRENT_EGRESS_OID, "full_index": True},
    {"metric_key": "attachedAggID", "oid": _DOT3AD_AGG_PORT_ATTACHED_AGG_ID_OID},
    {"metric_key": "actorState", "oid": _DOT3AD_AGG_PORT_ACTOR_OPER_STATE_OID},
    {"metric_key": "partnerState", "oid": _DOT3AD_AGG_PORT_PARTNER_OPER_STATE_OID},
    {"metric_key": "aggPortList", "oid": _DOT3AD_AGG_PORT_LIST_OID},
    {"metric_key": "ifStack", "oid": _IF_STACK_STATUS_OID, "full_index": True},
    {"metric_key": "ifHighSpeed", "oid": _IF_HIGH_SPEED_OID},
    {"metric_key": "ifOperStatus", "oid": _IF_OPER_STATUS_OID},
    {"metric_key": "cidrDest", "oid": _IP_CIDR_ROUTE_DEST_OID, "full_index": True},
    {"metric_key": "cidrMask", "oid": _IP_CIDR_ROUTE_MASK_OID, "full_index": True},
    {"metric_key": "cidrNextHop", "oid": _IP_CIDR_ROUTE_NEXT_HOP_OID, "full_index": True},
    {"metric_key": "cidrIfIndex", "oid": _IP_CIDR_ROUTE_IF_INDEX_OID, "full_index": True},
    {"metric_key": "cidrProto", "oid": _IP_CIDR_ROUTE_PROTO_OID, "full_index": True},
    {"metric_key": "rDest", "oid": _IP_ROUTE_DEST_OID, "full_index": True},
    {"metric_key": "rNextHop", "oid": _IP_ROUTE_NEXT_HOP_OID, "full_index": True},
    {"metric_key": "rType", "oid": _IP_ROUTE_TYPE_OID, "full_index": True},
    {"metric_key": "rProto", "oid": _IP_ROUTE_PROTO_OID, "full_index": True},
    {"metric_key": "rMask", "oid": _IP_ROUTE_MASK_OID, "full_index": True},
    {"metric_key": "sysDescr", "oid": _SYS_DESCR_OID},
    {"metric_key": "sysName", "oid": _SYS_NAME_OID},
    {"metric_key": "sysUpTime", "oid": _SYS_UPTIME_OID},
    {"metric_key": "sysObjectID", "oid": _SYS_OBJ_ID_OID},
    {"metric_key": "entClass", "oid": _ENT_PHYSICAL_CLASS_OID},
    {"metric_key": "entSerial", "oid": _ENT_PHYSICAL_SERIAL_NUM_OID},
    {"metric_key": "entName", "oid": _ENT_PHYSICAL_NAME_OID},
    {"metric_key": "entModelName", "oid": _ENT_PHYSICAL_MODEL_NAME_OID},
    {"metric_key": "entClass2", "oid": _ENT_PHYSICAL_CLASS_OID},
)
