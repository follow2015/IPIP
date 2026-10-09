# -*- coding: utf-8 -*-
"""多通道采集 · SNMP 通道（T0.6 / G9）。

规格：``docs/spec/多通道采集-契约层规格-T0.3.md`` §3.4、决策 4；
ADR-004：L1 单向复用 ``snmp_adapter`` / ``snmp_port_collector`` 原语。

能力矩阵**只声明 PORTS**（``PARTIAL``）：

- ``SnmpPortCollector`` 已采 IF-MIB 五表 + 四条静态属性表（``ifAlias`` /
  ``ifPhysAddress`` / ``dot1qPvid`` / ``ipAdEntIfIndex``）→ ``port_rows`` 的 11 键
  **均可填实**（2026-10-05 补齐；此前 description/vlan/mac/ip 恒 None，台账因此
  近乎无用 —— 运维认端口靠描述、判断网络归属靠 PVID、定位对端靠 MAC/IP）。
- **为何仍是 ``PARTIAL`` 而不是 ``FULL``**（补齐后按守卫原指引重新评估的结论）：
  产出与 CLI **仍不等价**，三条证据 ——
  ① **行集合**：逻辑端口（Vlanif / Eth-Trunk / LoopBack / NULL）被主动跳过，而 CLI 的
  ``display interface`` 会包含它们 → 本通道的行集合是 CLI 的子集；
  ② **``speed`` 口径**：CLI 原样取设备文本（如 ``1000M``），本通道标签化为 ``1G``；
  ③ **多 IP 取值规则**：CLI 取显示顺序首个，本通道取字典序最小。
  三条由 ``tests/services/collector/test_capability_matrix.py::TestPartialHonesty`` 钉住 ——
  任一条消失即应重新定档（含升 ``FULL`` 的可能）。
- ARP / MAC / routes 的 SNMP 侧现役原语**不存在**（监控侧只做指标采集）；
  声明即谎称。设备信息的 sysDescr 补齐归 T0.7 评估。
- 其余能力由 ``ChannelSelector`` 按能力降级给 CLI（O2=A 混合形态被期待）。

凭据：只接受 :class:`SnmpCredential`（决策 4），由 :class:`SnmpCredentialProvider`
自取；payload 必带 ``version`` 键，``_resolve_snmp_version`` 的回退分支走不到，
v3→v2c 静默降级被结构性切断（T-V3-1）。

线程与 app context：``BaseChannel.collect()`` 的 worker 线程里取凭据需要 app
context；无 context 时 provider 抛 ``RuntimeError`` → 落 ``FAILED``（明确报错，
不静默）。常驻线程/线程池的 context 携带由 T0.9 统一收口。

缓存（T0.10）：两类，边界**刻意不同** ——

- 凭据 / 管理 IP：``(channel, device)`` 级 TTL 缓存（E4）。TTL 兜底 + 显式
  ``invalidate_availability()``；异常不落缓存。
- IF-MIB walk 结果：**仅单次采集批次内**复用（E1），由 ``_begin_collect`` /
  ``_end_collect`` 界定边界。绝不能跨批次 —— stale 端口数据落库会让增量更新
  误删真实端口（设计文档 §705 / AC-21）。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, ClassVar

from app.core.enums import CollectCapability, QualityLevel
from app.services.collector.base_channel import BaseChannel
from app.services.collector.capability import implements
from app.services.collector import snmp_tables
from app.services.collector.contract import META_KEY_SNMP_SECURITY
from app.services.collector.credentials.snmp_credential import (
    SnmpCredential,
    SnmpCredentialProvider,
)
from app.services.collector.facts import CollectedFacts
from app.services.monitoring.adapters.snmp_adapter import _snmp_get_sysuptime
from app.services.monitoring.snmp_port_collector import SnmpPortCollector

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_SECONDS = 5

_DEFAULT_COLLECT_TIMEOUT_SECONDS = 30

_SNAPSHOT_KEYS_PORTS = (
    "ifName", "ifDescr", "ifOperStatus", "ifAdminStatus", "ifSpeed",
    "ifHighSpeed", "ifAlias", "ifPhysAddress", "dot1qPvid",
    "ipAdEntIfIndex", "ipAdEntNetMask",
)
_SNAPSHOT_KEYS_ARPS = ("arpNetAddr", "arpPhysAddr", "arpIfIndex", "ifName")
_SNAPSHOT_KEYS_MACS = (
    "qFdbPort", "qFdbStatus", "dFdbPort", "dFdbStatus", "basePortIfIndex", "ifName",
)
_SNAPSHOT_KEYS_LLDP_LOCAL = ("lldpLocPortId",)
_SNAPSHOT_KEYS_LLDP = (
    "lldpLocalPort", "lldpChassisId", "lldpPortId", "lldpSysName",
    "lldpManAddr", "basePortIfIndex", "ifName",
)
_SNAPSHOT_KEYS_VLANS = ("vlanName", "vlanStaticEgress", "vlanCurrentEgress", "ifName")
_SNAPSHOT_KEYS_LAGS = (
    "ifName", "attachedAggID", "actorState", "partnerState",
    "ifHighSpeed", "ifOperStatus", "aggPortList", "ifStack",
)
_SNAPSHOT_KEYS_ROUTES = (
    "cidrDest", "cidrMask", "cidrNextHop", "cidrIfIndex", "cidrProto",
    "rDest", "rNextHop", "rType", "rProto", "rMask",
)
_SNAPSHOT_KEYS_LOGICAL_PORTS = ("ifName",)
_SNAPSHOT_KEYS_DEVICE_INFO = (
    "sysDescr", "sysName", "sysUpTime", "entClass", "entSerial", "entName",
    "sysObjectID", "entModelName", "entClass2",
)

_AVAILABILITY_CACHE_TTL_SECONDS = 60

_AVAILABILITY_CACHE_MAX_ENTRIES = 1024

_WALK_WAIT_SLACK_SECONDS = 2


class _WalkSlot:
    """单次采集批次内 IF-MIB walk 的 single-flight 占位（E1）。

    同批次内多个能力（现在只有 PORTS，未来 ARP/MAC 复用同一份 IF-MIB 结果）
    并发请求时，只有第一个真正发网络 I/O，其余等它的 ``done`` 事件。
    等待有上界：持有者若挂死或被取消，等待者自己再 walk 一次 —— 复用是优化，
    不能变成"一个能力挂死拖死其余能力"。
    """

    __slots__ = ("rows", "done")

    def __init__(self) -> None:
        self.rows: list[dict] | None = None
        self.done = threading.Event()


class SnmpChannel(BaseChannel):
    """SNMP 采集通道（IF-MIB 端口 + SNMPv3/v2c 双版本）。"""

    code: ClassVar[str] = "snmp"

    def __init__(
        self,
        credential_provider: SnmpCredentialProvider | None = None,
        port_collector: SnmpPortCollector | None = None,
        device_repo: Any | None = None,
        availability_cache_ttl: float | None = None,
        snapshot_enabled: bool = False,
    ) -> None:
        self._provider = credential_provider
        self._port_collector = port_collector
        self._device_repo = device_repo
        self._security_lock = threading.Lock()
        self._security_by_device: dict[int, dict] = {}

        self._availability_ttl = (
            _AVAILABILITY_CACHE_TTL_SECONDS
            if availability_cache_ttl is None
            else float(availability_cache_ttl)
        )
        self._avail_lock = threading.Lock()
        self._cred_cache: dict[tuple[str, int], tuple[float, SnmpCredential | None]] = {}
        self._ip_cache: dict[int, tuple[float, str | None]] = {}

        self._walk_lock = threading.Lock()
        self._walk_slots: dict[int, _WalkSlot] = {}
        self._walk_batch_active = False

        self._snapshot_enabled = bool(snapshot_enabled)

    def _ensure_provider(self) -> SnmpCredentialProvider:
        if self._provider is None:
            self._provider = SnmpCredentialProvider()
        return self._provider

    def _ensure_collector(self) -> SnmpPortCollector:
        if self._port_collector is None:
            self._port_collector = SnmpPortCollector()
        return self._port_collector

    def _ensure_device_repo(self):
        if self._device_repo is None:
            from app.persistence.device_repository import DeviceRepository

            self._device_repo = DeviceRepository()
        return self._device_repo

    def is_available(self, device_id: int) -> bool:
        """凭据齐备（snmp 凭据启用且可解析）+ 设备有管理 IP。

        无 app context 时 provider 的 ``RuntimeError`` **上抛不吞** —— 与
        CliChannel 的「repo 异常抛」同口径：把环境错误伪装成 False 会让
        selector 永远跳过该通道，故障以"功能不可用"形态存在。

        凭据与 IP 均按 ``(channel, device)`` 缓存（E4）：一次采集里的多次判定
        只解一次凭据、只查一次库。异常**不入缓存** —— 缓存"取凭据失败"会把
        一次环境抖动固化成"该设备长期不可用"。
        """
        if self._cached_credential(device_id) is None:
            return False
        return bool(self._cached_management_ip(device_id))

    def health_probe(self, device_id: int) -> bool:
        """轻量健康检查：sysUptime 单 OID get（L1 原语 ``_snmp_get_sysuptime``）。"""
        cred = self._cached_credential(device_id)
        if cred is None:
            return False
        ip = self._cached_management_ip(device_id)
        if not ip:
            return False
        payload, _version = cred.to_adapter_payload()
        ok, res, _error = _snmp_get_sysuptime(payload, ip, _PROBE_TIMEOUT_SECONDS)
        return bool(ok and res is not None)

    @implements(CollectCapability.PORTS, QualityLevel.PARTIAL)
    def collect_ports(self, device_id: int, timeout: float | None = None) -> list[dict]:
        """IF-MIB 五表并发 walk → ``port_rows``（与 CLI 侧字段对齐，不含 device_id）。

        同一次采集批次内只 walk 一次（E1，见 :meth:`_walk_port_rows`）：
        现在只有 PORTS 一个 SNMP 能力，收益要到 ARP/MAC 落到 SNMP 侧才显现，
        但去重基础设施必须先就位 —— 否则届时是"边加能力边改缓存"，重演
        "文档先于代码"的漂移（R13）。
        """
        cred = self._require_credential(device_id)
        ip = self._require_management_ip(device_id)
        payload, _version = cred.to_adapter_payload()
        snmp_timeout = (
            int(timeout) if timeout is not None else _DEFAULT_COLLECT_TIMEOUT_SECONDS
        )
        raw = self._snapshot_raw(
            device_id, payload, ip, _SNAPSHOT_KEYS_PORTS, snmp_timeout,
        )
        rows = self._walk_port_rows(device_id, payload, ip, snmp_timeout, raw=raw)
        self._remember_security(device_id, cred)
        return rows

    @implements(CollectCapability.ARP, QualityLevel.PARTIAL)
    def collect_arps(self, device_id: int, timeout: float | None = None) -> list[dict]:
        """ARP 表（IP-MIB `ipNetToMediaTable`，**一次 walk 采全**）。

        为什么现在就做：SSH 侧要 `display arp` 单独一条命令，所以"按需获取"是 SSH 的
        约束；SNMP 是整表 walk，边际成本极低 —— 能一次采全的就不该留给用户点一下才拿。

        档位为什么是 PARTIAL：IP-MIB 的 ARP 表**不含 VLAN**（华为 `display arp` 有
        VLAN 列），故 `vlan` 如实留空。这是能力差异，不是 bug。
        """
        from .cli_translate import translate_arps   # 与 CLI 共用同一份规则（防双真源）

        cred = self._require_credential(device_id)
        ip = self._require_management_ip(device_id)
        payload, _version = cred.to_adapter_payload()
        snmp_timeout = (
            int(timeout) if timeout is not None else _DEFAULT_COLLECT_TIMEOUT_SECONDS
        )
        raw = self._snapshot_raw(
            device_id, payload, ip, _SNAPSHOT_KEYS_ARPS, snmp_timeout,
        )
        entries = snmp_tables.collect_arp_entries(payload, ip, snmp_timeout, raw=raw)
        self._remember_security(device_id, cred)
        return translate_arps(entries)

    @implements(CollectCapability.MAC, QualityLevel.PARTIAL)
    def collect_macs(self, device_id: int, timeout: float | None = None) -> list[dict]:
        """MAC 转发表（Q-BRIDGE `dot1qTpFdbTable`，BRIDGE-MIB 兜底，**一次 walk 采全**）。

        `is_uplink` 不在此产出：它由下游 Phase 2 的 `detect_uplink_ports()` 填充，
        通道层不知道拓扑（与 CLI 侧 `translate_macs` 同一条纪律）。
        """
        from .cli_translate import translate_macs   # 与 CLI 共用同一份规则（防双真源）

        cred = self._require_credential(device_id)
        ip = self._require_management_ip(device_id)
        payload, _version = cred.to_adapter_payload()
        snmp_timeout = (
            int(timeout) if timeout is not None else _DEFAULT_COLLECT_TIMEOUT_SECONDS
        )
        raw = self._snapshot_raw(
            device_id, payload, ip, _SNAPSHOT_KEYS_MACS, snmp_timeout,
        )
        entries = snmp_tables.collect_mac_entries(payload, ip, snmp_timeout, raw=raw)
        self._remember_security(device_id, cred)
        return translate_macs(entries)

    def lldp_local_status(self, device_id: int,
                          timeout: float | None = None) -> int | None:
        """只读探针：本机 LLDP 端口表条目数 —— "这台设备到底开没开 LLDP"。

        **不声明为能力**：它不产出业务数据，只用于在"邻居为空"时把原因说清楚
        （对端没开 LLDP vs 本机没开）。故不加 ``@implements``、不进能力矩阵 ——
        矩阵只登记"能被消费的数据"，诊断探针混进去会让档位语义失真。

        Returns:
            本机端口条目数；**采集失败返回 None**（无法判定 ≠ 未启用）。
        """
        cred = self._require_credential(device_id)
        ip = self._require_management_ip(device_id)
        payload, _version = cred.to_adapter_payload()
        snmp_timeout = (
            int(timeout) if timeout is not None else _DEFAULT_COLLECT_TIMEOUT_SECONDS
        )
        raw = self._snapshot_raw(
            device_id, payload, ip, _SNAPSHOT_KEYS_LLDP_LOCAL, snmp_timeout,
        )
        count = snmp_tables.collect_lldp_local_port_count(
            payload, ip, snmp_timeout, raw=raw,
        )
        self._remember_security(device_id, cred)
        return count

    @implements(CollectCapability.LLDP, QualityLevel.PARTIAL)
    def collect_lldp_neighbors(self, device_id: int,
                               timeout: float | None = None) -> list[dict]:
        """LLDP 邻居表（LLDP-MIB `lldpRemTable`，一次 walk 采全）。

        与 CLI 侧同形态：``[asdict(ParsedLldpNeighbor)]``，且同样**不做 CDP 回退**
        （那是拓扑服务的编排行为；`protocol` 字段已预留来源标注）。

        PARTIAL 的依据（2026-10-07 更新）：管理地址表 `lldpRemManAddrTable` 已采，
        但**只取 IPv4**（IPv6 索引刻意跳过，见 snmp_tables.parse_lldp_man_addr_index）
        —— 与 CLI 侧相比仍少一类地址，故档位保持 PARTIAL，而不是趁补采顺手升 FULL。
        """
        from dataclasses import asdict

        cred = self._require_credential(device_id)
        ip = self._require_management_ip(device_id)
        payload, _version = cred.to_adapter_payload()
        snmp_timeout = (
            int(timeout) if timeout is not None else _DEFAULT_COLLECT_TIMEOUT_SECONDS
        )
        raw = self._snapshot_raw(
            device_id, payload, ip, _SNAPSHOT_KEYS_LLDP, snmp_timeout,
        )
        entries = snmp_tables.collect_lldp_entries(payload, ip, snmp_timeout, raw=raw)
        self._remember_security(device_id, cred)
        return [asdict(entry) for entry in entries]

    @implements(CollectCapability.VLANS, QualityLevel.PARTIAL)
    def collect_vlan_members(self, device_id: int,
                             timeout: float | None = None) -> list[dict]:
        """VLAN 及其成员端口（Q-BRIDGE-MIB 端口位图，一次 walk 采全）。

        产出 ``[{"vlan_id", "name", "members": [端口名]}]`` —— 与 CLI 侧
        ``display vlan`` 解析出的 ``{vlan_id: [成员端口名]}`` 同语义，Phase 0d 的
        ``sync_vlan_members`` 可直接消费（无 SSH 设备因此也能建 VLAN 成员关系）。

        PARTIAL 的依据：**只覆盖 VLAN 成员**，链路聚合（LAG）成员由独立的
        ``CollectCapability.LAGS`` 负责（IEEE8023-LAG-MIB）。
        另：成员由端口位图还原，依赖 ifName 表给出端口名 —— 取不到名字的 ifIndex
        直接跳过（宁缺勿错，不拿 ifIndex 冒充端口名）。
        """
        cred = self._require_credential(device_id)
        ip = self._require_management_ip(device_id)
        payload, _version = cred.to_adapter_payload()
        snmp_timeout = (
            int(timeout) if timeout is not None else _DEFAULT_COLLECT_TIMEOUT_SECONDS
        )
        raw = self._snapshot_raw(
            device_id, payload, ip, _SNAPSHOT_KEYS_VLANS, snmp_timeout,
        )
        entries = snmp_tables.collect_vlan_entries(payload, ip, snmp_timeout, raw=raw)
        self._remember_security(device_id, cred)
        return entries

    @implements(CollectCapability.LAGS, QualityLevel.PARTIAL)
    def collect_lag_members(self, device_id: int,
                            timeout: float | None = None) -> list[dict]:
        """链路聚合组：成员端口 + LACP 状态（IEEE8023-LAG-MIB，**不需要 SSH**）。

        一次 walk 拿全：``dot3adAggPortAttachedAggID`` 建「端口 → 聚合器」关系，
        ifName 把两侧 ifIndex 换成端口名，ifXTable 补聚合口的速率与状态。

        PARTIAL 的依据：只覆盖**静态 LACP 运行态**（成员归属 + 本端/对端 LacpState）。
        不含 LACP 统计（``dot3adAggPortStatsTable`` 的 LACPDUs 收发计数）—— 那是
        排障时才看的量，且监控侧已有别的采集口径，不重复引入。
        """
        cred = self._require_credential(device_id)
        ip = self._require_management_ip(device_id)
        payload, _version = cred.to_adapter_payload()
        snmp_timeout = (
            int(timeout) if timeout is not None else _DEFAULT_COLLECT_TIMEOUT_SECONDS
        )
        raw = self._snapshot_raw(
            device_id, payload, ip, _SNAPSHOT_KEYS_LAGS, snmp_timeout,
        )
        entries = snmp_tables.collect_lag_entries(payload, ip, snmp_timeout, raw=raw)
        self._remember_security(device_id, cred)
        if not entries:
            self._warn_lag_members_unreadable(device_id)
        return entries

    def _warn_lag_members_unreadable(self, device_id: int) -> None:
        """读不到聚合成员时给**可操作**的原因提示（对齐 LLDP 自检的诚实原则）。

        为什么需要：实测（178）把 trunk 配成静态/手工模式后，标准 IEEE8023-LAG-MIB
        的两条路（``dot3adAggPortAttachedAggID`` / ``dot3adAggPortList``）都拿不到
        成员，而**静态 Eth-Trunk 本就不往标准 MIB 写成员关系** —— 只能读厂商私有
        MIB，可私有子树 ``1.3.6.1.4.1`` 在该设备 v3 视图里整棵未开放（实测 0 条）。
        不做提示的话，用户只会看到"没有聚合组"，无从判断是没配、模式不对还是视图
        没开。

        前提是**确实存在聚合口**（ifName 里的 Eth-Trunk/Bridge-Aggregation…）：
        连聚合口都没有就是没配置，不该拿这段话打扰。
        """
        try:
            logical = self.collect_logical_port_names(device_id)
            lags = list((logical or {}).get("lag_names") or [])
        except Exception:  # noqa: BLE001 —— 诊断失败不影响主结论
            return
        if not lags:
            return
        logger.warning(
            "[LAG] 设备 %s 存在聚合口 %s，但读不到成员：标准 IEEE8023-LAG-MIB 对"
            "**静态 Eth-Trunk** 不输出成员关系（只能读厂商私有 MIB，而该设备未开放"
            "私有子树 1.3.6.1.4.1）**，或该 trunk 尚未加入成员端口。"
            "处理：① 改用 LACP 动态模式（标准 MIB 即有）；② 或在设备侧把私有子树"
            "加入 SNMP v3 读视图",
            device_id, lags[:5],
        )

    @implements(CollectCapability.ROUTES, QualityLevel.PARTIAL)
    def collect_routes(self, device_id: int, timeout: float | None = None) -> list[dict]:
        """路由表（`ipCidrRouteTable`，一次 walk 采全；老设备兜底 RFC1213）。

        PARTIAL 的依据：兜底路径（RFC1213 `ipRouteTable`）**没有 ifIndex 列**，
        出接口只能留空。
        """
        from .cli_translate import translate_routes   # 与 CLI 共用同一份规则（防双真源）

        cred = self._require_credential(device_id)
        ip = self._require_management_ip(device_id)
        payload, _version = cred.to_adapter_payload()
        snmp_timeout = (
            int(timeout) if timeout is not None else _DEFAULT_COLLECT_TIMEOUT_SECONDS
        )
        raw = self._snapshot_raw(
            device_id, payload, ip, _SNAPSHOT_KEYS_ROUTES, snmp_timeout,
        )
        entries = snmp_tables.collect_route_entries(payload, ip, snmp_timeout, raw=raw)
        self._remember_security(device_id, cred)
        return translate_routes(entries)

    def collect_logical_port_names(self, device_id: int,
                                   timeout: float | None = None) -> dict:
        """**公开辅助**：筛出 Vlanif / Eth-Trunk 这类逻辑端口名。

        不是 `CollectCapability`（契约里没有"逻辑端口"这一项），而是给接管路径用的
        辅助方法 —— 因为 `_sync_vlan_trunk_bases` 靠**端口名**建 vlans /
        link_aggregation_groups 基础记录，而本通道的 PORTS 产出会主动跳过逻辑端口
        （它们的 link_status 不代表物理链路）。一次 ifName 筛选即可，不新增 walk。
        """
        cred = self._require_credential(device_id)
        ip = self._require_management_ip(device_id)
        payload, _version = cred.to_adapter_payload()
        snmp_timeout = (
            int(timeout) if timeout is not None else _DEFAULT_COLLECT_TIMEOUT_SECONDS
        )
        return snmp_tables.collect_logical_port_names(
            payload, ip, snmp_timeout,
            raw=self._snapshot_raw(
                device_id, payload, ip, _SNAPSHOT_KEYS_LOGICAL_PORTS, snmp_timeout,
            ),
        )

    @implements(CollectCapability.DEVICE_INFO, QualityLevel.PARTIAL)
    def collect_device_information(self, device_id: int,
                                   timeout: float | None = None) -> dict:
        """设备信息（sysDescr + sysName + sysUpTime + 机箱序列号，一次 walk 采全）。

        PARTIAL 的依据：`sysDescr` 是**自由文本**，型号/版本靠保守启发式解析
        （认不出就留空 —— 写错型号比留空更难发现）；序列号取 ENTITY-MIB 中
        `entPhysicalClass == 3` 的机箱行。
        """
        from .cli_translate import translate_device_info  # 与 CLI 共用出口（防双真源）

        cred = self._require_credential(device_id)
        ip = self._require_management_ip(device_id)
        payload, _version = cred.to_adapter_payload()
        snmp_timeout = (
            int(timeout) if timeout is not None else _DEFAULT_COLLECT_TIMEOUT_SECONDS
        )
        raw = self._snapshot_raw(
            device_id, payload, ip, _SNAPSHOT_KEYS_DEVICE_INFO, snmp_timeout,
        )
        info = snmp_tables.collect_device_info_entry(payload, ip, snmp_timeout, raw=raw)
        info = snmp_tables.enrich_device_identity(
            info, payload, ip, snmp_timeout, raw=raw,
        )
        self._remember_security(device_id, cred)
        return translate_device_info(info)

    def _require_credential(self, device_id: int) -> SnmpCredential:
        cred = self._cached_credential(device_id)
        if cred is None:
            raise RuntimeError(f"设备 {device_id} 无启用的 SNMP 凭据，无法采集")
        return cred

    def _require_management_ip(self, device_id: int) -> str:
        ip = self._cached_management_ip(device_id)
        if not ip:
            raise RuntimeError(f"设备 {device_id} 缺少管理 IP，SNMP 通道无法采集")
        return ip

    def _snapshot_raw(
        self, device_id: int, payload: dict, ip: str, keys: tuple[str, ...],
        timeout: int,
    ) -> dict | None:
        """取本能力的快照注入（步 4）；开关关/快照不可用/意外失败一律 ``None``。

        ``None`` 是**合法退化值**：解析层与端口采集器收到 ``raw=None`` 逐字走
        改造前的直采路径 —— 快照层的任何问题（Redis 没配、没命中、代码炸了）
        都只会让本轮变慢，绝不会让采集失败。``keys`` 是本能力的 metric_key
        子集（见模块头 ``_SNAPSHOT_KEYS_*``），命中未遂现采时只采这些表；
        ``timeout`` 透传给快照层的单表 walk（与能力自身的超时同口径）。
        """
        if not self._snapshot_enabled:
            return None
        from app.services.collector import snmp_snapshot   # 延迟导入：非必需路径

        try:
            return snmp_snapshot.snapshot_for(
                device_id, payload, ip, timeout=timeout, keys=keys,
            )
        except Exception as exc:  # noqa: BLE001 —— 快照故障退化为直采，不拖垮采集
            logger.warning(
                "SNMP 快照获取失败（退化为直采）device_id=%s: %s", device_id, exc,
            )
            return None

    def _management_ip(self, device_id: int) -> str | None:
        """未缓存的管理 IP 查询（仅 :meth:`_cached_management_ip` 与测试使用）。"""
        device = self._ensure_device_repo().find_by_id(device_id)
        if device is None:
            return None
        return device.management_ip or None

    def _cached_credential(self, device_id: int) -> SnmpCredential | None:
        """``(channel, device)`` 级凭据缓存：TTL 内只解一次（E4）。"""
        if self._availability_ttl <= 0:
            return self._ensure_provider().get(device_id)
        key = (self.code, device_id)
        now = time.monotonic()
        with self._avail_lock:
            hit = self._cred_cache.get(key)
            if hit is not None and hit[0] > now:
                return hit[1]
        cred = self._ensure_provider().get(device_id)
        with self._avail_lock:
            if len(self._cred_cache) >= _AVAILABILITY_CACHE_MAX_ENTRIES:
                self._cred_cache.clear()
            self._cred_cache[key] = (now + self._availability_ttl, cred)
        return cred

    def _cached_management_ip(self, device_id: int) -> str | None:
        """``device`` 级管理 IP 缓存；``None``（设备无 IP）同样缓存。"""
        if self._availability_ttl <= 0:
            return self._management_ip(device_id)
        now = time.monotonic()
        with self._avail_lock:
            hit = self._ip_cache.get(device_id)
            if hit is not None and hit[0] > now:
                return hit[1]
        ip = self._management_ip(device_id)
        with self._avail_lock:
            if len(self._ip_cache) >= _AVAILABILITY_CACHE_MAX_ENTRIES:
                self._ip_cache.clear()
            self._ip_cache[device_id] = (now + self._availability_ttl, ip)
        return ip

    def invalidate_availability(self, device_id: int | None = None) -> None:
        """显式失效可用性缓存（凭据 / 管理 IP 变更后调用）。

        ``device_id`` 为 None 时清空全部。TTL 只是兜底：**凭据被撤下的即时性**
        必须由调用方在这里保证，不能靠把 TTL 调到很小。
        """
        with self._avail_lock:
            if device_id is None:
                self._cred_cache.clear()
                self._ip_cache.clear()
                return
            self._cred_cache.pop((self.code, device_id), None)
            self._ip_cache.pop(device_id, None)

    def _begin_collect(self, device_id: int) -> None:
        """单次采集开始：开启 walk 复用并清空上一批次的残留。"""
        with self._walk_lock:
            self._walk_slots = {}
            self._walk_batch_active = True

    def _end_collect(self, device_id: int) -> None:
        """单次采集结束：walk 结果一律作废（stale 数据落库会误删端口，AC-21）。"""
        with self._walk_lock:
            self._walk_slots = {}
            self._walk_batch_active = False

    def _walk_port_rows(
        self, device_id: int, payload: dict, ip: str, timeout: int,
        raw: dict | None = None,
    ) -> list[dict]:
        """同批次内同一设备只 walk 一次 IF-MIB（E1 的 single-flight 实现）。

        ``raw``（步 4）为快照注入：快照命中时 ``collect`` 是纯本地解析，single-flight
        退化为"同设备只解析一次"（无害）；快照不可用时为 ``None``，语义与改造前
        逐字一致。raw 按 owner/waiter 共享：waiter 直接复用 owner 的行结果。
        """
        with self._walk_lock:
            if not self._walk_batch_active:
                return self._call_port_collector(payload, ip, timeout, raw=raw)
            slot = self._walk_slots.get(device_id)
            if slot is None:
                slot = _WalkSlot()
                self._walk_slots[device_id] = slot
                owner = True
            else:
                owner = False

        if not owner:
            budget = timeout + _WALK_WAIT_SLACK_SECONDS
            if slot.done.wait(timeout=budget) and slot.rows is not None:
                return list(slot.rows)     # 行列表拷贝：避免下游 mutate 命中缓存
            return self._call_port_collector(payload, ip, timeout, raw=raw)

        try:
            rows = self._call_port_collector(payload, ip, timeout, raw=raw)
            slot.rows = rows
            return list(rows)
        finally:
            slot.done.set()

    def _call_port_collector(
        self, payload: dict, ip: str, timeout: int, raw: dict | None = None,
    ) -> list[dict]:
        return self._ensure_collector().collect(payload, ip, timeout=timeout, raw=raw)

    def _remember_security(self, device_id: int, cred: SnmpCredential) -> None:
        with self._security_lock:
            self._security_by_device[device_id] = cred.audit_info()

    def snmp_security_meta(self, device_id: int) -> dict | None:
        """返回最近一次采集的 ``meta[META_KEY_SNMP_SECURITY]`` 形状审计信息。"""
        with self._security_lock:
            return self._security_by_device.get(device_id)

    def _report(self, facts: CollectedFacts, device_id: int) -> None:
        """批次收尾：把本次 SNMP 安全审计**写进 facts.meta**（决策 4 第 4 点）。

        [WARN] 原先审计只落在实例字典 ``_security_by_device`` 里、由
        ``snmp_security_meta()`` 读，而那个出口**零调用方** —— 信息从未进入
        ``facts``，落库侧（决策 5）也就无从取用（2026-10-05 评审 I-3）。
        写入点选在批次收尾：handler 在 worker 线程记录，这里由主线程统一落盘，
        避免 worker 直接并发写 facts。
        """
        info = self.snmp_security_meta(device_id)
        if info:
            facts.meta[META_KEY_SNMP_SECURITY] = info
        super()._report(facts, device_id)


__all__ = ["SnmpChannel"]
