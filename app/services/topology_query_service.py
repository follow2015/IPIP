# -*- coding: utf-8 -*-
"""
AI 拓扑遍历查询服务（只读）

面向"客户服务器连到哪些交换机 / 核心宕机影响谁 / 上行链路是什么 / 两点间路径"等
**拓扑遍历类问题**。与 topology_service（给前端渲染 nodes/edges）不同，本服务直接
构建可遍历的图索引并提供高层查询，输出即 JSON-ready 的链路/影响面结构，供
AI capability 层直接返回给 LLM。

数据模型约定（与 topology_service 保持一致）：
- 网络设备: Device.device_type == "network"（交换机/路由器/防火墙，含 switch_ext 与否）
- D2N:      DeviceConnection（server → switch，含两端端口名）
- N2N:      NetworkConnection（网络设备间互联，对称 local/peer）
- 上行方向: DeviceSwitchExt.uplink_device_id 优先，core_device_id 兜底；两者皆缺时
            退化为"从核心(role=0)出发的 N2N 最短路径森林"，保证无显式上行的
            路由器/防火墙也能向上找到归属（结果链路标注推断来源，不混淆数据）。
"""
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set

from app.utils.logging import get_logger

logger = get_logger(__name__)

MAX_PATH_HOPS = 16
MAX_IMPACT_NODES = 500
MAX_SERVER_PATHS = 3

_STATUS_MAP = {}


def _status_label(status: Optional[int]) -> str:
    """设备状态数字 → 可读标签（与 topology_service 同口径，缺省映射 unknown）。"""
    if not _STATUS_MAP:
        from app.core.enums import DeviceStatus
        _STATUS_MAP.update({
            DeviceStatus.ONLINE: "online",
            DeviceStatus.OFFLINE: "offline",
            DeviceStatus.AVAILABLE: "available",
            DeviceStatus.MAINTENANCE: "maintenance",
            DeviceStatus.RESERVED: "reserved",
        })
    return _STATUS_MAP.get(status, "unknown")


class TopologyIndex:
    """一次性装载后的可遍历图索引。

    构造后可安全用于纯内存遍历（测试可直接注入 dicts 验证算法，不依赖 DB）。
    """

    def __init__(
        self,
        devices: Dict[int, Dict[str, Any]],
        n2n_edges: List[Dict[str, Any]],
        d2n_edges: List[Dict[str, Any]],
        switch_ext: Dict[int, Dict[str, Any]],
        customers: Optional[Dict[int, str]] = None,
    ):
        """
        Args:
            devices: {id: {id,name,device_type,device_subtype,status,ip,hostname,
                            customer_id,customer_name}}
            n2n_edges: [{a,b,a_port,b_port,conn_id}]（a/b 均为网络设备 id，无向）
            d2n_edges: [{server_id,switch_id,switch_port,nic_port,conn_id}]
            switch_ext: {id: {switch_role,layer,uplink_device_id,core_device_id}} 网络设备扩展
            customers: {客户 id: 客户名}（downstream 影响客户汇总展示用）
        """
        self.devices = devices
        self.n2n_edges = n2n_edges
        self.d2n_edges = d2n_edges
        self.switch_ext = switch_ext
        self.customers = customers or {}

        self.network_ids: Set[int] = {
            did for did, d in devices.items() if d["device_type"] == "network"
        }

        self._adj: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for e in n2n_edges:
            self._adj[e["a"]].append(e)
            self._adj[e["b"]].append(e)
        for e in d2n_edges:
            self._adj[e["server_id"]].append(e)
            self._adj[e["switch_id"]].append(e)

        self._d2n_by_switch: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for e in d2n_edges:
            self._d2n_by_switch[e["switch_id"]].append(e)
        self._d2n_by_server: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for e in d2n_edges:
            self._d2n_by_server[e["server_id"]].append(e)

        self._explicit_parent: Dict[int, Optional[int]] = {}
        for nid in self.network_ids:
            ext = self.switch_ext.get(nid) or {}
            uplink = ext.get("uplink_device_id")
            core = ext.get("core_device_id")
            parent: Optional[int] = None
            if uplink and uplink != nid and uplink in self.network_ids:
                parent = uplink
            elif core and core != nid and core in self.network_ids:
                parent = core
            self._explicit_parent[nid] = parent
        self._forest_parent: Optional[Dict[int, int]] = None
        self._parent_cache: Dict[int, Optional[int]] = {}


    def is_network(self, device_id: int) -> bool:
        """是否为网络设备（交换机/路由器/防火墙等）。"""
        return device_id in self.network_ids

    def device_brief(self, device_id: int) -> Optional[Dict[str, Any]]:
        """设备精简信息（未收录返回 None）。"""
        d = self.devices.get(device_id)
        return d

    def _node_label(self, device_id: int) -> str:
        """节点显示名：名称（主机名）兜底。"""
        d = self.devices.get(device_id)
        if not d:
            return f"#{device_id}"
        name = d.get("name")
        return f"{name}（{d.get('hostname')}）" if d.get("hostname") else name

    def _build_forest(self) -> Dict[int, int]:
        """构建兜底上行森林：核心(role=0)为根，沿 N2N 的 BFS 树。

        仅对**无显式上行**的网络设备赋父；已有显式父的不覆盖。
        无核心时按 N2N 连通分量取最小 id 为根，保证每台设备都能向上收敛。
        """
        n2n_adj: Dict[int, List[int]] = defaultdict(set)
        for e in self.n2n_edges:
            n2n_adj[e["a"]].add(e["b"])
            n2n_adj[e["b"]].add(e["a"])

        seeds: List[int] = [
            nid for nid in self.network_ids
            if (self.switch_ext.get(nid) or {}).get("switch_role") == 0
        ]
        if not seeds:
            seen: Set[int] = set()
            for nid in sorted(self.network_ids):
                if nid in seen:
                    continue
                comp: List[int] = []
                queue = deque([nid])
                seen.add(nid)
                while queue:
                    cur = queue.popleft()
                    comp.append(cur)
                    for nb in n2n_adj.get(cur, ()):
                        if nb not in seen:
                            seen.add(nb)
                            queue.append(nb)
                seeds.append(min(comp))

        parent: Dict[int, int] = {}
        visited: Set[int] = set()
        queue: deque = deque()
        for s in seeds:
            if s in self.network_ids:
                visited.add(s)
                queue.append(s)
        while queue:
            cur = queue.popleft()
            for nb in n2n_adj.get(cur, ()):
                if nb in visited:
                    continue
                visited.add(nb)
                if nb not in self._explicit_parent or self._explicit_parent[nb] is None:
                    parent[nb] = cur  # 仅无显式父的节点使用兜底父
                queue.append(nb)
        return parent

    def parent_of(self, device_id: int) -> Optional[int]:
        """设备在"上行方向"上的父节点（网络设备间）。

        显式上行(uplink_device_id → core_device_id) 优先；
        缺失时用核心 BFS 森林兜底。服务器等非网络设备无父。
        """
        if device_id not in self.network_ids:
            return None
        if device_id in self._parent_cache:
            return self._parent_cache[device_id]
        if self._forest_parent is None:
            self._forest_parent = self._build_forest()
        parent = self._explicit_parent.get(device_id)
        if parent is None:
            parent = self._forest_parent.get(device_id)
        self._parent_cache[device_id] = parent
        return parent

    def _via_kind(self, child: int, parent: int) -> str:
        """上行边的来源标注：显式 uplink / core 记录 / 森林推断 n2n。"""
        ext = self.switch_ext.get(child) or {}
        if ext.get("uplink_device_id") == parent:
            return "uplink"
        if ext.get("core_device_id") == parent:
            return "core_record"
        return "n2n_inferred"

    def _n2n_port(self, child: int, parent: int) -> tuple:
        """child↔parent 的 N2N 物理端口名（有多条时取第一条），无则 (None, None)。"""
        for e in self.n2n_edges:
            if e["a"] == child and e["b"] == parent:
                return e["a_port"], e["b_port"]
            if e["a"] == parent and e["b"] == child:
                return e["b_port"], e["a_port"]
        return None, None


    def uplink_path(self, device_id: int) -> Dict[str, Any]:
        """设备 → 最上级核心 的完整上行路径。

        服务器按接入交换机拆多条独立路径；交换机从自身起算。
        Returns:
            {"reachable": bool, "reason": str,
             "paths": [{"hops": [...], "end": {...}, "ends_at_core": bool}]}
        """
        paths: List[Dict[str, Any]] = []
        reachable = False
        reason = ""

        def _finalize(start_id: int, hops: List[Dict[str, Any]]) -> Dict[str, Any]:
            """为一条上行链附加端部信息（root/核心判定）。"""
            end_id = hops[-1]["to"]["id"] if hops else start_id
            ext = self.switch_ext.get(end_id) or {}
            is_root = self.parent_of(end_id) is None
            return {
                "hops": hops,
                "end": self._hop_node(end_id),
                "ends_at_core": ext.get("switch_role") == 0,
                "ends_at_root": is_root,
            }

        if not self.is_network(device_id):
            d2n_list = self._d2n_by_server.get(device_id)
            if not d2n_list:
                return {
                    "reachable": False,
                    "reason": "未找到该服务器的接入记录（device_connections 无该设备）",
                    "paths": [],
                }
            switch_ids = list(dict.fromkeys(e["switch_id"] for e in d2n_list))
            for sw in switch_ids[:MAX_SERVER_PATHS]:
                hops = [{
                    "from": self._hop_node(device_id),
                    "to": self._hop_node(sw),
                    "via": "d2n",
                    "ports": {
                        "server": next(
                            (e.get("nic_port") for e in d2n_list
                             if e["switch_id"] == sw and e.get("nic_port")), None),
                        "switch": next(
                            (e.get("switch_port") for e in d2n_list
                             if e["switch_id"] == sw and e.get("switch_port")), None),
                    },
                }]
                hops.extend(self._walk_up(sw))
                paths.append(_finalize(device_id, hops))
            reachable = True
        elif device_id not in self.network_ids:
            return {
                "reachable": False,
                "reason": "设备不存在于拓扑索引中",
                "paths": [],
            }
        else:
            hops = self._walk_up(device_id)
            paths.append(_finalize(device_id, hops))
            reachable = True

        return {
            "reachable": reachable,
            "reason": reason,
            "paths": paths,
            "truncated": len(paths) > MAX_SERVER_PATHS,
        }

    def _walk_up(self, device_id: int) -> List[Dict[str, Any]]:
        """从某网络设备逐级上行到根，返回上行 hops。

        设备即根（无父）时返回空列表——顶层调用方据此判定"已到最上级"。
        """
        hops: List[Dict[str, Any]] = []
        cur = device_id
        while True:
            parent = self.parent_of(cur)
            if parent is None or len(hops) >= MAX_PATH_HOPS:
                break
            my_port, peer_port = self._n2n_port(cur, parent)
            hops.append({
                "from": self._hop_node(cur),
                "to": self._hop_node(parent),
                "via": self._via_kind(cur, parent),
                "ports": {"switch": my_port, "peer": peer_port},
            })
            cur = parent
        return hops

    def _hop_node(self, device_id: int) -> Dict[str, Any]:
        """hop 中的设备节点描述（name/type/layer/role/status）。"""
        d = self.devices.get(device_id) or {"name": f"#{device_id}"}
        ext = self.switch_ext.get(device_id) or {}
        return {
            "id": device_id,
            "name": d.get("name"),
            "device_type": d.get("device_type"),
            "status": _status_label(d.get("status")),
            "layer": ext.get("layer"),
            "switch_role": ext.get("switch_role"),
        }

    def path_between(self, a: int, b: int) -> Dict[str, Any]:
        """两设备（任意类型）间最短路径（无向 BFS：N2N + D2N 均可通行）。

        Returns:
            {"reachable": bool, "reason": str,
             "hops": [{"from": node, "to": node, "via": ..., "ports": {...}}]}
        """
        if a not in self.devices or b not in self.devices:
            return {
                "reachable": False,
                "reason": "起点或终点不在拓扑索引中",
                "hops": [],
            }
        if a == b:
            return {"reachable": True, "reason": "", "hops": []}

        def _neighbor(edge: Dict[str, Any], cur: int) -> Optional[int]:
            """返回边另一端的节点 id（cur 必须为边端点，否则 None）。"""
            if edge.get("server_id") is not None:
                if edge["server_id"] == cur:
                    return edge["switch_id"]
                if edge["switch_id"] == cur:
                    return edge["server_id"]
                return None
            return edge["b"] if edge["a"] == cur else (
                edge["a"] if edge["b"] == cur else None
            )

        prev: Dict[int, Any] = {}
        queue: deque = deque([a])
        prev[a] = None
        found = False
        while queue and not found:
            cur = queue.popleft()
            if len(prev) >= MAX_IMPACT_NODES * 2:
                break  # 防超大图内存爆炸（BFS 节点数护栏）
            for e in self._adj.get(cur, ()):
                nb = _neighbor(e, cur)
                if nb is None or nb in prev:
                    continue
                prev[nb] = e
                if nb == b:
                    found = True
                    break
                queue.append(nb)

        if not found:
            return {
                "reachable": False,
                "reason": "两设备间无连通路径（连接表无链路）",
                "hops": [],
            }

        edges_rev: List[Dict[str, Any]] = []
        cur = b
        while prev.get(cur) is not None:
            e = prev[cur]
            edges_rev.append(e)
            cur = _neighbor(e, cur)  # type: ignore[arg-type]
        edges = list(reversed(edges_rev))

        hops: List[Dict[str, Any]] = []
        cur = a
        for e in edges:
            if e.get("server_id") is not None:
                s1, s2 = e["server_id"], e["switch_id"]
                p1, p2 = e.get("nic_port"), e.get("switch_port")
                via = "d2n"
            else:
                s1, s2 = e["a"], e["b"]
                p1, p2 = e.get("a_port"), e.get("b_port")
                via = "n2n"
            if cur == s2:
                src, dst, src_port, dst_port = s2, s1, p2, p1
            else:
                src, dst, src_port, dst_port = s1, s2, p1, p2
            hops.append({
                "from": self._hop_node(src),
                "to": self._hop_node(dst),
                "via": via,
                "ports": {"from_port": src_port, "to_port": dst_port},
            })
            cur = dst
        return {
            "reachable": True,
            "reason": "",
            "hops": hops,
            "truncated": len(hops) > MAX_PATH_HOPS,
        }

    def downstream(self, device_id: int) -> Dict[str, Any]:
        """以某网络设备为根的**下行子树**：其宕机将影响的设备面。

        影响面 = 沿上行父指针反向可达的交换机/路由器（root 自身除外）
               + 这些设备 D2N 直连的服务器（含客户归属）。
        服务器不作为影响面根（语义上它是叶子）；root 必须为网络设备。
        """
        if not self.is_network(device_id):
            return {
                "supported_root": False,
                "reason": "影响面分析的根设备必须是网络设备（交换机/路由器/防火墙）",
                "switches": [], "servers": [], "customers": [],
            }
        children: Dict[int, List[int]] = defaultdict(list)
        for nid in self.network_ids:
            p = self.parent_of(nid)
            if p is not None and p != nid:
                children[p].append(nid)

        affected_switches: List[int] = []
        queue: deque = deque([device_id])
        while queue and len(affected_switches) < MAX_IMPACT_NODES:
            cur = queue.popleft()
            for nid in children.get(cur, ()):
                affected_switches.append(nid)
                queue.append(nid)

        servers: List[Dict[str, Any]] = []
        customer_ids: Set[int] = set()
        affected_ids = {device_id, *affected_switches}
        for sw in affected_ids:
            for e in self._d2n_by_switch.get(sw, ()):
                srv = self.devices.get(e["server_id"])
                if not srv:
                    continue
                servers.append(srv)
                if srv.get("customer_id"):
                    customer_ids.add(srv["customer_id"])

        seen_srv: Set[int] = set()
        servers_dedup = []
        for s in servers:
            if s["id"] not in seen_srv:
                seen_srv.add(s["id"])
                servers_dedup.append(s)
        servers = servers_dedup

        customers = [
            {"id": cid, "name": self.customers.get(cid, f"客户{cid}")}
            for cid in sorted(customer_ids)
        ]
        return {
            "supported_root": True,
            "root": self._hop_node(device_id),
            "affected_switches": [self._hop_node(n) for n in affected_switches],
            "affected_servers": servers,
            "affected_customer_count": len(customers),
            "affected_customers": customers,
            "truncated": len(affected_switches) >= MAX_IMPACT_NODES,
        }

    def customer_connectivity(self, customer_id: int) -> Dict[str, Any]:
        """客户接入拓扑：客户所有服务器 → 接入交换机 → 各自上联核心链路。

        Returns:
            {"reachable": bool, "entries": [{"server": {...}, "switch": {...},
                                              "ports": {...}, "uplink": [...hops]}]}
        """
        servers = [
            d for d in self.devices.values()
            if d.get("device_type") == "server" and d.get("customer_id") == customer_id
        ]
        if not servers:
            return {"reachable": False, "reason": "该客户没有服务器设备", "entries": []}

        entries: List[Dict[str, Any]] = []
        for srv in sorted(servers, key=lambda x: x["id"])[:MAX_IMPACT_NODES]:
            for e in self._d2n_by_server.get(srv["id"], []):
                sw_id = e["switch_id"]
                uplink_hops = self._walk_up(sw_id)
                entries.append({
                    "server": self._hop_node(srv["id"]),
                    "switch": self._hop_node(sw_id),
                    "ports": {
                        "server": e.get("nic_port"),
                        "switch": e.get("switch_port"),
                    },
                    "uplink": uplink_hops,
                })
        return {
            "reachable": True,
            "reason": "",
            "entry_count": len(entries),
            "server_count": len(servers),
            "entries": entries,
        }




def load_topology_index(visible_ids: Optional[Set[int]] = None) -> TopologyIndex:
    """从数据库装载全量/可见域拓扑索引。

    Args:
        visible_ids: 数据域可见设备 ID 集合；None 表示不裁剪（无限制）；
            集合表示只装载其中设备，跨出集合的边被丢弃——保证返回的
            任何链路/节点都不泄露不可见设备的存在性。

    Returns:
        TopologyIndex：已按可见域裁剪的图索引。
    """
    from app.models.device import Device
    from app.models.device_switch_ext import DeviceSwitchExt
    from app.models.device_connection import DeviceConnection
    from app.models.network_connection import NetworkConnection
    from sqlalchemy.orm import joinedload

    query = (
        Device.query
        .filter(Device.device_type.in_(["network", "server"]))
        .filter(Device.deleted_at.is_(None))
        .options(joinedload(Device.switch_ext), joinedload(Device.customer))
    )
    if visible_ids is not None:
        if not visible_ids:
            return TopologyIndex({}, [], [], {}, {})
        query = query.filter(Device.id.in_(visible_ids))
    dev_rows = query.all()

    customers: Dict[int, str] = {}
    for d in dev_rows:
        if d.customer:
            customers.setdefault(d.customer_id, d.customer.customer_name)

    devices: Dict[int, Dict[str, Any]] = {}
    switch_ext: Dict[int, Dict[str, Any]] = {}
    for d in dev_rows:
        devices[d.id] = {
            "id": d.id,
            "name": d.device_name,
            "hostname": d.hostname,
            "device_type": d.device_type,
            "device_subtype": d.device_subtype,
            "status": d.status,
            "ip": d.management_ip,
            "customer_id": d.customer_id,
            "customer_name": d.customer.customer_name if d.customer else None,
        }
        if d.device_type == "network" and d.switch_ext:
            switch_ext[d.id] = {
                "switch_role": d.switch_ext.switch_role,
                "layer": d.switch_ext.layer,
                "uplink_device_id": d.switch_ext.uplink_device_id,
                "core_device_id": d.switch_ext.core_device_id,
            }
    network_ids = {did for did, d in devices.items() if d["device_type"] == "network"}
    if not network_ids:
        return TopologyIndex(devices, [], [], switch_ext, customers)

    d2n_rows = (
        DeviceConnection.query
        .filter(DeviceConnection.switch_device_id.in_(network_ids))
        .options(
            joinedload(DeviceConnection.nics_port),
            joinedload(DeviceConnection.switch_port),
        )
        .all()
    )
    d2n_edges: List[Dict[str, Any]] = []
    for c in d2n_rows:
        if c.device_id not in devices:
            continue
        if c.switch_device_id not in network_ids:
            continue
        d2n_edges.append({
            "server_id": c.device_id,
            "switch_id": c.switch_device_id,
            "switch_port": c.switch_port.port_name if c.switch_port else None,
            "nic_port": (c.nics_port.display_name or c.nics_port.port_number)
            if c.nics_port else None,
            "conn_id": c.id,
        })

    n2n_rows = (
        NetworkConnection.query
        .filter(
            NetworkConnection.local_device_id.in_(network_ids),
            NetworkConnection.peer_device_id.in_(network_ids),
        )
        .options(
            joinedload(NetworkConnection.local_port),
            joinedload(NetworkConnection.peer_port),
        )
        .all()
    )
    n2n_edges: List[Dict[str, Any]] = []
    for c in n2n_rows:
        n2n_edges.append({
            "a": c.local_device_id,
            "b": c.peer_device_id,
            "a_port": c.local_port.port_name if c.local_port else None,
            "b_port": c.peer_port.port_name if c.peer_port else None,
            "conn_id": c.id,
        })

    return TopologyIndex(devices, n2n_edges, d2n_edges, switch_ext, customers)
