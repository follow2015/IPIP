# -*- coding: utf-8 -*-
"""SNMP 端口采集器（SnmpPortCollector）

用 IF-MIB 通过 SNMP 采集网络设备的端口列表 + 链路状态，输出与 SSH 适配器
``parse_ports`` 相同结构的 ``port_rows``，供 ``NetworkPortRepository.incremental_update``
三步事务消费。

采集的 OID（均为 IF-MIB 标准表，pysnmp 自带）：
- ifName（1.3.6.1.2.1.31.1.1.1.1）：端口名，如 "GigabitEthernet0/0/1"
- ifOperStatus（1.3.6.1.2.1.2.2.1.8）：操作状态 up(1)/down(2)/testing(3)/unknown(4)/dormant(5)
- ifAdminStatus（1.3.6.1.2.1.2.2.1.7）：管理状态 up(1)/down(2)/testing(3)
- ifSpeed（1.3.6.1.2.1.2.2.1.5）：端口速率（bps）
- ifDescr（1.3.6.1.2.1.2.2.1.2）：端口描述（ifName 缺失时兜底）

所有 OID 以 ifIndex 为尾缀索引，跨表按 ifIndex 对齐。

设计要点：
- 复用 ``snmp_adapter._snmp_walk_table_async`` / ``_snmp_collect_metrics`` 的同步边界
  + 防挂死模式，避免重复实现。
- 采集失败静默降级返回空列表，不阻断主探测流程。
- 输出 ``port_rows`` 字段与 ``SwitchInfoService.collect_port_info`` 对齐，使
  ``incremental_update`` 消费方无感知。
"""
from __future__ import annotations

from app.utils.logging import get_logger

from app.services.monitoring.adapters.base_adapter import (
    monitor_timeout_seconds,
    run_with_timeout,
)
from app.services.monitoring.adapters.snmp_adapter import (
    _snmp_collect_metrics,
)
from app.utils.port_name_parser import parse_port_name

logger = get_logger(__name__)

_IF_NAME_OID = "1.3.6.1.2.1.31.1.1.1.1"        # ifName
_IF_DESCR_OID = "1.3.6.1.2.1.2.2.1.2"          # ifDescr
_IF_OPER_STATUS_OID = "1.3.6.1.2.1.2.2.1.8"    # ifOperStatus
_IF_ADMIN_STATUS_OID = "1.3.6.1.2.1.2.2.1.7"   # ifAdminStatus
_IF_SPEED_OID = "1.3.6.1.2.1.2.2.1.5"          # ifSpeed

_IF_ALIAS_OID = "1.3.6.1.2.1.31.1.1.1.18"       # ifAlias → description
_IF_PHYS_ADDRESS_OID = "1.3.6.1.2.1.2.2.1.6"    # ifPhysAddress → mac
_DOT1Q_PVID_OID = "1.3.6.1.2.1.17.7.1.4.5.1.1"  # dot1qPvid → vlan（Q-BRIDGE-MIB）
_IP_AD_ENT_IF_INDEX_OID = "1.3.6.1.2.1.4.20.1.2"  # ipAdEntIfIndex（索引=IP，值=ifIndex）
_IP_AD_ENT_NET_MASK_OID = "1.3.6.1.2.1.4.20.1.3"  # ipAdEntNetMask（索引=IP，值=掩码）
_IF_HIGH_SPEED_OID = "1.3.6.1.2.1.31.1.1.1.15"   # ifHighSpeed（Mbps，64 位，不受 ifSpeed 32 位溢出影响）


def _normalize_mac(raw: str | None) -> str | None:
    """``ifPhysAddress`` 归一到本项目的 MAC 格式 ``xxxx-xxxx-xxxx``。

    pysnmp 对 OctetString 的 prettyPrint 给的是 ``0x001122334455``，而 CLI 侧模板
    的 HARDWARE_ADDRESS 产出的是 ``0011-2233-4455`` —— 两条路径写同一列，
    格式必须统一，否则前端与关联逻辑会当成两个不同的 MAC。
    全零 MAC（设备未分配）归一为 None（列里已有 NULL 语义，不必制造 0000-0000-0000）。
    """
    if not raw:
        return None
    text = raw.strip()
    if text.lower().startswith("0x"):
        text = text[2:]
    text = "".join(ch for ch in text if ch.isalnum()).lower()
    if len(text) != 12 or any(ch not in "0123456789abcdef" for ch in text):
        return text or None
    if text == "0" * 12:
        return None
    return f"{text[0:4]}-{text[4:8]}-{text[8:12]}"


def _high_speed_to_label(high_speed_mbps: str) -> str:
    """``ifHighSpeed``（**Mbps**）→ 速率标签，优先于 ifSpeed。

    [WARN] ifSpeed 是 32 位计数器，≥40G 的端口会溢出（4.29Gbps 封顶）——
    真机 40GE 口因此全显示 1G（用户实测）。ifHighSpeed 单位是 Mbps 且 64 位，
    不受溢出影响，必须优先使用；0/缺失回退 ifSpeed（老设备只实现 ifSpeed）。
    """
    try:
        mbps = int(high_speed_mbps)
    except (ValueError, TypeError):
        return ""
    if mbps <= 0:
        return ""
    gbps = mbps / 1_000
    if gbps >= 200:
        return "200G"
    if gbps >= 100:
        return "100G"
    if gbps >= 50:
        return "50G"
    if gbps >= 40:
        return "40G"
    if gbps >= 25:
        return "25G"
    if gbps >= 10:
        return "10G"
    if gbps >= 1:
        return "1G"
    return f"{mbps}M"


def _ips_by_ifindex(ifindex_table: dict, netmask_table: dict | None = None) -> dict:
    """组装 ``{ifIndex: "10.0.0.1/24,10.0.0.2/24"}`` —— **保留全部 IP**。

    [WARN] 必须保留多值，不能只取一个：CLI 侧的 ``ParsedPort.ip_address`` 是
    ``display interface`` 的 ``INTERNET_ADDRESS``（TextFSM **List**）用 ``,`` 拼接的
    **全部 IP**（含掩码），下游 ``_sync_port_ips`` 逐条写 ``sw_info_ip``（第一个为主 IP）。
    只取一个会让"同一 VLAN 下配了多 IP"的端口在台账里**丢一半**（用户实测指出的缺陷）。

    三张 IP-MIB 表的协作（都以 IP 为多段索引，故 walk 时需 ``full_index=True``）：

    - ``ipAdEntIfIndex``：值 = ifIndex → 决定该 IP 属于哪个端口（反查的依据）
    - ``ipAdEntNetMask``：值 = 掩码 → 拼成 ``addr/prefixlen``，与 CLI 的 ``10.0.0.1/24`` 同形态
    - （``ipAdEntAddr`` 可选，值 = IP 本身，用于校核）

    同端口多 IP 按**字典序**拼接：稳定可复现，不随 walk 返回顺序漂移。
    """
    import ipaddress

    grouped: dict[str, list[str]] = {}
    for ip, idx in (ifindex_table or {}).items():
        address = str(ip).strip()
        key = str(idx).strip()
        if not address or not key:
            continue
        mask = str((netmask_table or {}).get(ip, "") or "").strip()
        entry = address
        if mask:
            try:
                prefixlen = ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
                entry = f"{address}/{prefixlen}"
            except ValueError:
                entry = address
        grouped.setdefault(key, []).append(entry)
    return {key: ",".join(sorted(values)) for key, values in grouped.items()}

_OPER_STATUS_MAP = {
    "1": "up",
    "2": "down",
    "3": "testing",
    "4": "unknown",
    "5": "dormant",
    "6": "notPresent",
    "7": "lowerLayerDown",
}
_ADMIN_STATUS_MAP = {
    "1": "up",
    "2": "down",
    "3": "testing",
}

def _speed_bps_to_label(speed_bps: str) -> str:
    """将 ifSpeed（bps 字符串）映射为速率标签。

    IF-MIB ifSpeed 单位是 bps，常见值：
    - 1000000000 → 1G
    - 10000000000 → 10G
    - 25000000000 → 25G
    - 40000000000 → 40G
    - 100000000000 → 100G
    - 0 → 端口未协商速率（返回空串）
    """
    try:
        bps = int(speed_bps)
    except (ValueError, TypeError):
        return ""
    if bps <= 0:
        return ""
    gbps = bps / 1_000_000_000
    if gbps >= 200:
        return "200G"
    if gbps >= 100:
        return "100G"
    if gbps >= 50:
        return "50G"
    if gbps >= 40:
        return "40G"
    if gbps >= 25:
        return "25G"
    if gbps >= 10:
        return "10G"
    if gbps >= 1:
        return "1G"
    if bps >= 100_000_000:
        return "100M"
    if bps >= 10_000_000:
        return "10M"
    return ""


def _resolve_link_status(oper_status: str, admin_status: str) -> str:
    """合并 ifOperStatus + ifAdminStatus 为 link_status 字符串。

    语义对齐 SSH 适配器输出的 link_status：
    - admin down → "admin_down"（管理关闭，与 NetworkPort.derive_usage_status 的
      admin_down / administratively down / *down 判定对齐）
    - admin up + oper up → "up"
    - admin up + oper down → "down"
    - 其余 → oper_status 原值
    """
    admin = _ADMIN_STATUS_MAP.get(admin_status, admin_status)
    oper = _OPER_STATUS_MAP.get(oper_status, oper_status)
    if admin == "down":
        return "admin_down"
    if admin == "up" and oper == "up":
        return "up"
    if admin == "up" and oper == "down":
        return "down"
    return oper


class SnmpPortCollector:
    """SNMP 端口采集器（IF-MIB → port_rows）。

    对非网管网络设备（has_ssh=false）但有 SNMP 凭据的设备，用 IF-MIB 采集端口
    列表 + 状态，输出 ``port_rows`` 供 ``incremental_update`` 消费。
    """

    def collect(self, credential: dict, ip: str, timeout: int | None = None,
                device=None, raw: dict | None = None) -> list[dict]:
        """采集设备端口列表，返回 port_rows（与 SSH 适配器输出对齐）。

        Args:
            credential: SNMP 凭据（community/version 等）
            ip: 设备管理 IP
            timeout: 采集超时（秒），缺省走 monitor_timeout_seconds()
            device: 设备 ORM 对象（SNMP 不需要，仅为统一 collector 接口）
            raw: 快照注入（``{metric_key: {index: value}}``，步 2 同语义：
                **有键哪怕空 = 信任，缺键 = 只补 walk 缺的那张**；None = 自己 walk）。

        Returns:
            list[dict]: port_rows，每个 dict 含 port_name / port_type / slot /
            card / port_number / link_status / speed 等字段。采集失败返回空列表。
        """
        snmp_timeout = timeout if timeout is not None else monitor_timeout_seconds()

        templates = [
            {"metric_key": "ifName", "oid": _IF_NAME_OID},
            {"metric_key": "ifDescr", "oid": _IF_DESCR_OID},
            {"metric_key": "ifOperStatus", "oid": _IF_OPER_STATUS_OID},
            {"metric_key": "ifAdminStatus", "oid": _IF_ADMIN_STATUS_OID},
            {"metric_key": "ifSpeed", "oid": _IF_SPEED_OID},
            {"metric_key": "ifHighSpeed", "oid": _IF_HIGH_SPEED_OID},
            {"metric_key": "ifAlias", "oid": _IF_ALIAS_OID},
            {"metric_key": "ifPhysAddress", "oid": _IF_PHYS_ADDRESS_OID},
            {"metric_key": "dot1qPvid", "oid": _DOT1Q_PVID_OID},
            {"metric_key": "ipAdEntIfIndex", "oid": _IP_AD_ENT_IF_INDEX_OID,
             "full_index": True},
            {"metric_key": "ipAdEntNetMask", "oid": _IP_AD_ENT_NET_MASK_OID,
             "full_index": True},
        ]

        if raw is None:
            ok, raw, _elapsed = run_with_timeout(
                lambda: _snmp_collect_metrics(credential, ip, templates, snmp_timeout),
                snmp_timeout + 3,
            )
            if not ok or not isinstance(raw, dict):
                return []
        else:
            missing = [t for t in templates if t.get("metric_key") not in raw]
            if missing:
                ok, fetched, _elapsed = run_with_timeout(
                    lambda: _snmp_collect_metrics(credential, ip, missing, snmp_timeout),
                    snmp_timeout + 3,
                )
                if ok and isinstance(fetched, dict):
                    merged = dict(raw)
                    merged.update(fetched)
                    raw = merged

        if_name_table = raw.get("ifName", {})
        if_descr_table = raw.get("ifDescr", {})
        if_oper_table = raw.get("ifOperStatus", {})
        if_admin_table = raw.get("ifAdminStatus", {})
        if_speed_table = raw.get("ifSpeed", {})
        if_high_speed_table = raw.get("ifHighSpeed", {})
        if_alias_table = raw.get("ifAlias", {})
        if_phys_table = raw.get("ifPhysAddress", {})
        dot1q_pvid_table = raw.get("dot1qPvid", {})
        ips_by_index = _ips_by_ifindex(
            raw.get("ipAdEntIfIndex", {}), raw.get("ipAdEntNetMask", {}),
        )

        if not if_name_table and not if_descr_table:
            return []

        name_table = dict(if_descr_table)
        name_table.update(if_name_table)

        port_rows: list[dict] = []
        for if_index, port_name in name_table.items():
            if not port_name:
                continue
            parsed = parse_port_name(port_name)
            port_type = parsed.get("port_type")
            if port_type in ("VLAN", "ETH-TRUNK", "LOOPBACK", "NULL"):
                continue
            if not parsed.get("parsed"):
                logger.debug(
                    "SNMP 端口采集：端口名无法解析，跳过 ifIndex=%s port_name=%s",
                    if_index, port_name,
                )
                continue

            oper_status = if_oper_table.get(if_index, "")
            admin_status = if_admin_table.get(if_index, "")
            link_status = _resolve_link_status(oper_status, admin_status)
            high = (if_high_speed_table.get(if_index) or "").strip()
            if high.isdigit() and int(high) > 0:
                speed = _high_speed_to_label(high)
            else:
                speed = _speed_bps_to_label(if_speed_table.get(if_index, ""))

            alias = (if_alias_table.get(if_index) or "").strip() or None
            pvid = (dot1q_pvid_table.get(if_index) or "").strip()

            port_rows.append({
                "port_name": port_name,
                "port_type": port_type,
                "slot": parsed["slot"],
                "card": parsed["card"],
                "port_number": parsed["port_number"],
                "link_status": link_status,
                "speed": speed,
                "description": alias,
                "vlan": int(pvid) if pvid.isdigit() else None,
                "mac": _normalize_mac(if_phys_table.get(if_index)),
                "ip_address": ips_by_index.get(if_index),
            })

        return port_rows



SNAPSHOT_TABLES: tuple[dict, ...] = (
    {"metric_key": "ifName", "oid": _IF_NAME_OID},
    {"metric_key": "ifDescr", "oid": _IF_DESCR_OID},
    {"metric_key": "ifOperStatus", "oid": _IF_OPER_STATUS_OID},
    {"metric_key": "ifAdminStatus", "oid": _IF_ADMIN_STATUS_OID},
    {"metric_key": "ifSpeed", "oid": _IF_SPEED_OID},
    {"metric_key": "ifHighSpeed", "oid": _IF_HIGH_SPEED_OID},
    {"metric_key": "ifAlias", "oid": _IF_ALIAS_OID},
    {"metric_key": "ifPhysAddress", "oid": _IF_PHYS_ADDRESS_OID},
    {"metric_key": "dot1qPvid", "oid": _DOT1Q_PVID_OID},
    {"metric_key": "ipAdEntIfIndex", "oid": _IP_AD_ENT_IF_INDEX_OID, "full_index": True},
    {"metric_key": "ipAdEntNetMask", "oid": _IP_AD_ENT_NET_MASK_OID, "full_index": True},
)
