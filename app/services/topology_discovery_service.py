# -*- coding: utf-8 -*-
"""
LLDP/CDP 拓扑发现服务（P2-1）

通过 SSH 在交换机上执行 LLDP（Cisco 老设备回退 CDP）邻居查询，解析邻居表，
与系统内设备/端口做匹配，产出**连接建议列表**。

铁律（规划文档 P2-1 卡片）：
    发现结果仅作建议，**绝不自动覆盖手工录入的连接关系**。
    - discover_* 全程只读，不写库；
    - apply_suggestions 只接受 match_status == "matched"（两端设备、端口全部
      唯一解析成功，且两端端口当前均未被任何 N2N 连接占用）的条目；
    - 落库用"先查后插"，**不复用** NetworkConnectionRepository.create_connection
      （其语义是"端口被占用则改写既有连接"，与本铁律冲突）；
    - 任一端口已被其它连接占用 → 标记 port_occupied，应用时跳过并如实报告。
"""
import re
from typing import Any, Dict, List, Optional


from app.adapters.adapter_factory import get_adapter
from app.exceptions.business import DeviceNotSupported
from app.models.network_connection import NetworkConnection
from app.models.switch_credentials import SwitchCredentials
from app.utils.logging import get_logger

logger = get_logger(__name__)

STATUS_EXISTING = "existing"        # 连接已存在（本机端口-对端端口已有 N2N）
STATUS_MATCHED = "matched"          # 两端设备+端口全部解析成功，可应用
STATUS_PARTIAL = "partial"          # 设备已匹配但端口缺失/歧义
STATUS_UNKNOWN_PEER = "unknown_peer"  # 对端设备不在系统内
STATUS_PORT_OCCUPIED = "port_occupied"  # 端口已被其它连接占用

MAX_BATCH_SWITCHES = 10

_PORT_EXPANSIONS = [
    ("GE", ["GigabitEthernet"]),
    ("GI", ["GigabitEthernet"]),
    ("XGE", ["Ten-GigabitEthernet", "XGigabitEthernet"]),
    ("10GE", ["Ten-GigabitEthernet", "XGigabitEthernet"]),
    ("TE", ["TenGigabitEthernet", "Ten-GigabitEthernet"]),
    ("FA", ["FastEthernet"]),
    ("ETH", ["Ethernet"]),
    ("ME", ["MEth", "Management Ethernet"]),
]

_PORT_SN_RE = re.compile(r"^([A-Za-z\-]+?)(\d+(?:/\d+)*)$")


def _port_candidates(raw: str) -> List[str]:
    """生成端口名的候选写法集合（原样 + 缩写展开），供库内匹配。

    例：GE0/0/1 → ["GE0/0/1", "GigabitEthernet0/0/1"]
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    candidates = [raw]
    m = _PORT_SN_RE.match(raw)
    if m:
        prefix, suffix = m.group(1), m.group(2)
        for abbr, fulls in _PORT_EXPANSIONS:
            if prefix.upper() == abbr:
                for full in fulls:
                    candidates.append(f"{full}{suffix}")
            elif prefix.upper() in (full.upper() for full in fulls):
                pass
    return list(dict.fromkeys(candidates))  # 去重保序


def _normalize_sysname_candidates(sysname: str) -> List[str]:
    """生成对端系统名的候选写法（原样 + 去 DNS 域后缀 + 大写）。

    Cisco CDP 的 Device ID 常为 FQDN（如 SW-CORE-01.corp.local），
    而系统内 device_name 通常为短名。
    """
    s = (sysname or "").strip()
    if not s:
        return []
    candidates = [s]
    short = s.split(".")[0]
    if short and short != s:
        candidates.append(short)
    return list(dict.fromkeys(candidates))


class TopologyDiscoveryService:
    """LLDP/CDP 拓扑发现（只读探测 + 建议式落库）"""

    def __init__(self):
        self._ssh_manager = None

    @property
    def ssh_manager(self):
        if self._ssh_manager is None:
            from app.infra import SSHManager
            self._ssh_manager = SSHManager()
        return self._ssh_manager


    def discover_switch(self, device_id: int) -> Dict[str, Any]:
        """对单台交换机做 LLDP/CDP 邻居发现并生成连接建议。

        Args:
            device_id: 交换机 Device ID（须有 SwitchCredentials）

        Returns:
            {"device_id", "source": "lldp"|"cdp", "suggestions": [...],
             "raw_count": int, "error": None|str}
        """
        from app.persistence.switch_ext_repository import SwitchExtRepository

        cred = SwitchExtRepository().get_by_device_id(device_id)
        if cred is None:
            return {"device_id": device_id, "source": None,
                    "suggestions": [], "error": "该设备没有交换机凭据记录"}

        adapter = self._get_adapter_for(cred)

        raw_text, err = self._run_show(cred, adapter.get_lldp_neighbor_command())
        source = "lldp"
        neighbors: list = []
        if not err:
            neighbors = adapter.parse_lldp_neighbors(raw_text)
            if not neighbors:
                cdp_cmd = adapter.get_cdp_neighbor_command()
                if cdp_cmd:
                    raw2, err2 = self._run_show(cred, cdp_cmd)
                    if not err2:
                        cdp_rows = adapter.parse_cdp_neighbors(raw2)
                        if cdp_rows:
                            neighbors, source = cdp_rows, "cdp"

        snmp_note = None
        if not neighbors:
            neighbors, snmp_note = self._discover_lldp_via_snmp(cred)
            if neighbors:
                source = "lldp(snmp)"

        if err and not neighbors:
            return {"device_id": device_id, "source": source,
                    "suggestions": [], "error": snmp_note or err}

        suggestions = [self._build_suggestion(device_id, n) for n in neighbors]
        return {"device_id": device_id, "source": source,
                "suggestions": suggestions, "raw_count": len(neighbors),
                "error": None if neighbors else snmp_note}

    def discover_batch(self, device_ids: List[int]) -> Dict[str, Any]:
        """批量发现（≤10 台，逐台串行，单台失败不阻断其余）"""
        ids = list(device_ids or [])[:MAX_BATCH_SWITCHES]
        results = []
        for did in ids:
            try:
                results.append(self.discover_switch(did))
            except Exception as e:  # noqa: BLE001 -- 单台设备发现失败隔离：单台失败不阻断其余，记入 results 后继续下一台
                logger.warning("[topo-discovery] 设备 %s 发现失败: %s", did, e)
                results.append({"device_id": did, "source": None,
                                "suggestions": [], "error": str(e)})
        return {"results": results,
                "total_suggestions": sum(
                    len(r.get("suggestions") or []) for r in results)}


    def apply_suggestions(self, device_id: int,
                          suggestions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """将勾选的 matched 建议落库为 N2N 连接。

        纪律：只建全新连接；两端端口任一已被占用即跳过（不自作聪明改写
        既有连接）；对端设备不在系统内的条目拒绝应用。
        """
        from extensions import db

        created, skipped = [], []
        for item in suggestions or []:
            if item.get("match_status") != STATUS_MATCHED:
                skipped.append({"item": item, "reason": "仅 matched 状态可应用"})
                continue
            local_port_id = item.get("local_port_id")
            peer_port_id = item.get("peer_port_id")
            local_device_id = item.get("local_device_id")
            peer_device_id = item.get("peer_device_id")
            if not all((local_port_id, peer_port_id, local_device_id, peer_device_id)):
                skipped.append({"item": item, "reason": "关键字段缺失"})
                continue
            if local_device_id != device_id:
                skipped.append({
                    "item": item,
                    "reason": f"建议来源不符（local_device_id={local_device_id} "
                              f"≠ 源设备 {device_id}）"})
                continue

            from app.persistence.network_connection_repository import (
                NetworkConnectionRepository,
            )

            _conns = NetworkConnectionRepository().find_by_port_ids_orm(
                [local_port_id, peer_port_id]
            )
            occupied = _conns[0] if _conns else None
            if occupied:
                skipped.append({"item": item,
                                "reason": "端口已被其它连接占用（拒绝改写既有连接）"})
                continue

            conn = NetworkConnection(
                local_port_id=local_port_id,
                peer_port_id=peer_port_id,
                local_device_id=local_device_id,
                peer_device_id=peer_device_id,
                status="active",
                description=f"LLDP/CDP 发现建立（源设备 #{device_id}）",
            )
            db.session.add(conn)
            db.session.flush()
            created.append(conn.id)

        return {"created_count": len(created), "created_ids": created,
                "skipped": skipped}


    def _get_adapter_for(self, cred: SwitchCredentials):
        try:
            return get_adapter(cred.get_netmiko_device_type())
        except DeviceNotSupported:
            raise

    def _run_show(self, cred, command: str):
        """执行只读 show 命令。返回 (output, error)"""
        try:
            output = self.ssh_manager.send_show_command(cred, command, timeout=60)
            return output or "", None
        except Exception as e:  # noqa: BLE001 - SSH 执行失败时返回 (None, 错误信息) 交调用方处理（已回传）
            return None, f"SSH 执行失败 [{command}]: {e}"

    def _discover_lldp_via_snmp(self, cred) -> tuple[list, Optional[str]]:
        """CLI 拿不到 LLDP 邻居时的 SNMP 来源（无 SSH 设备的唯一路径）。

        设计要点：

        - **走 ``runtime.selector_for``，不直接 new SnmpChannel**：拓扑发现与扫描
          共用同一套灰度开关（``SCAN_CHANNEL_ENABLED``）与 SNMP 白名单，
          不需要为"只读建议"另开一条绕过开关的路。
        - 通道返回的是 ``[asdict(ParsedLldpNeighbor)]``（dict），而
          ``_build_suggestion`` 按属性访问 —— 这里转回 dataclass，**按字段名过滤**
          而不是硬编码键，SNMP 侧加字段时不会炸。
        - 诚实边界：SNMP 不采 ``lldpRemManAddrTable`` ⇒ ``neighbor_mgmt_ip`` 为空，
          对端匹配退化为 sysname，建议可能落在 UNKNOWN_PEER —— 不编造地址。

        Returns:
            ``(neighbors, note)``：neighbors 为空时 note 是给用户的原因说明。
        """
        from dataclasses import fields as _dc_fields

        from app.adapters.base_adapter import ParsedLldpNeighbor
        from app.core.enums import CollectCapability
        from app.services.collector import runtime

        try:
            selector = runtime.selector_for(cred)
        except Exception as exc:  # noqa: BLE001 —— 装配异常不得让发现接口 500
            logger.warning("[topo-discovery] 通道装配失败 device=%s: %s", cred.device_id, exc)
            return [], f"通道层装配失败: {exc}"
        if selector is None:
            return [], ("通道层未启用，或该设备不在 SNMP 白名单内"
                        "（无 SSH 设备需先放行才可走 SNMP 发现）")

        try:
            facts = selector.collect(cred.device_id, [CollectCapability.LLDP])
        except Exception as exc:  # noqa: BLE001 —— 同上：发现失败降级为提示
            logger.warning("[topo-discovery] SNMP 采集 LLDP 失败 device=%s: %s",
                           cred.device_id, exc)
            return [], f"SNMP 采集失败: {exc}"

        names = {f.name for f in _dc_fields(ParsedLldpNeighbor)}
        neighbors = [
            ParsedLldpNeighbor(**{k: v for k, v in row.items() if k in names})
            for row in (facts.lldp or [])
        ]
        if not neighbors:
            outcomes = {k: str(v) for k, v in (facts.outcomes or {}).items()}
            return [], (f"SNMP 未返回 LLDP 邻居（outcomes={outcomes}）"
                        + self._lldp_local_hint(selector, cred))
        logger.info("[topo-discovery] 设备 %s 经 SNMP 取得 %d 条 LLDP 邻居",
                    cred.device_id, len(neighbors))
        return neighbors, None

    @staticmethod
    def _lldp_local_hint(selector, cred) -> str:
        """邻居为空时补一句"为什么"：本机 LLDP 端口表为空 ⇒ 设备未启用。

        现场最常见的困惑就是"点了几次都没有建议" —— 本机表为空的两种成因
        （设备没开 LLDP / SNMP 视图未放行 ``1.0.8802`` 子树）用户都不该靠猜。
        探测失败（返回 None）时**只说未判定**，不把"没采到"说成"没启用"。
        """
        snmp_ch = next(
            (c for c in (getattr(selector, "channels", None) or [])
             if getattr(c, "code", "") == "snmp"),
            None,
        )
        probe = getattr(snmp_ch, "lldp_local_status", None)  # 非 SNMP 通道没有此探针
        if probe is None:
            return ""
        try:
            count = probe(cred.device_id)
        except Exception as exc:  # noqa: BLE001 —— 诊断探针失败不影响主结论
            logger.debug("[topo-discovery] LLDP 本机状态探测失败 device=%s: %s",
                         cred.device_id, exc)
            return ""
        if count is None:
            return "（本机 LLDP 状态未判定：探测失败）"
        if count == 0:
            return ("（本机 LLDP 端口表为空 ⇒ 设备侧 LLDP 未启用，"
                    "或 SNMP 视图未开放 1.0.8802 子树）")
        return "（本机 LLDP 已启用，但未学到邻居 ⇒ 对端未开 LLDP 或非 LLDP 设备）"

    def _build_suggestion(self, switch_device_id: int,
                          neighbor) -> Dict[str, Any]:
        """将一条 LLDP/CDP 邻居解析结果与系统内数据匹配为建议条目"""
        local_port_id, local_amb = self._resolve_port(switch_device_id,
                                                      neighbor.local_port)
        peer_device_id, peer_reason = self._resolve_peer_device(
            neighbor.neighbor_mgmt_ip, neighbor.neighbor_sysname)

        item = {
            "local_port_name": neighbor.local_port,
            "local_port_id": local_port_id,
            "local_device_id": switch_device_id,
            "peer_name": neighbor.neighbor_sysname,
            "peer_mgmt_ip": neighbor.neighbor_mgmt_ip,
            "peer_port_name": neighbor.neighbor_port,
            "peer_port_id": None,
            "peer_device_id": peer_device_id,
            "chassis_id": neighbor.chassis_id,
            "protocol": neighbor.protocol,
            "match_status": STATUS_UNKNOWN_PEER,
            "reason": "",
        }

        if peer_device_id is None:
            item["match_status"] = STATUS_UNKNOWN_PEER
            item["reason"] = peer_reason or "对端设备不在系统内"
            return item

        peer_port_id, peer_amb = self._resolve_port(peer_device_id,
                                                    neighbor.neighbor_port)
        item["peer_port_id"] = peer_port_id

        if local_amb or peer_amb:
            item["match_status"] = STATUS_PARTIAL
            item["reason"] = local_amb or peer_amb
            return item
        if local_port_id is None or peer_port_id is None:
            missing = "本机" if local_port_id is None else "对端"
            item["match_status"] = STATUS_PARTIAL
            peer_port = (neighbor.local_port if local_port_id is None
                         else neighbor.neighbor_port)
            item["reason"] = f"{missing}端口未录入（{peer_port}）"
            return item

        existing = self._find_connection(local_port_id, peer_port_id)
        if existing is not None:
            item["match_status"] = STATUS_EXISTING
            item["reason"] = f"连接已存在（N2N #{existing.id}）"
            return item
        from app.persistence.network_connection_repository import (
            NetworkConnectionRepository,
        )

        _conns = NetworkConnectionRepository().find_by_port_ids_orm(
            [local_port_id, peer_port_id]
        )
        occupied = _conns[0] if _conns else None
        if occupied:
            item["match_status"] = STATUS_PORT_OCCUPIED
            item["reason"] = f"端口已被连接 #{occupied.id} 占用"
            return item

        item["match_status"] = STATUS_MATCHED
        item["reason"] = "两端设备与端口均匹配，可建立 N2N 连接"
        return item

    @staticmethod
    def _resolve_port(device_id: int, port_name: str):
        """端口名 → NetworkPort。返回 (port_id|None, 歧义原因|None)"""
        if not port_name:
            return None, None
        candidates = _port_candidates(port_name)
        from app.persistence.switch_port_repository import NetworkPortRepository

        ports = NetworkPortRepository().list_by_port_names(device_id, candidates)
        if len(ports) == 1:
            return ports[0].id, None
        if len(ports) > 1:
            ids = [p.id for p in ports]
            return None, f"端口名歧义（{port_name} 命中 #{ids}）"
        return None, None

    @staticmethod
    def _resolve_peer_device(mgmt_ip: Optional[str], sysname: str):
        """对端设备解析：管理 IP 精确 → 名称精确（含去域后缀）。

        Returns:
            (device_id|None, 原因|None)
        """
        from app.persistence.device_repository import DeviceRepository

        if mgmt_ip:
            by_ip = DeviceRepository().list_by_management_ip(mgmt_ip)
            if len(by_ip) == 1:
                return by_ip[0].id, None
            if len(by_ip) > 1:
                ids = [d.id for d in by_ip]
                return None, f"管理 IP {mgmt_ip} 命中多台设备 #{ids}"

        for name in _normalize_sysname_candidates(sysname):
            by_name = DeviceRepository().list_by_name(name)
            if len(by_name) == 1:
                return by_name[0].id, None
            if len(by_name) > 1:
                ids = [d.id for d in by_name]
                return None, f"名称 {name} 命中多台设备 #{ids}"
        return None, None

    @staticmethod
    def _find_connection(local_port_id: int, peer_port_id: int):
        """两端端口（含反向）的既有 N2N 连接"""
        from app.persistence.network_connection_repository import (
            NetworkConnectionRepository,
        )

        return NetworkConnectionRepository().find_pair_connection_orm(
            local_port_id, peer_port_id
        )
