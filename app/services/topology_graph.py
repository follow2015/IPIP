# -*- coding: utf-8 -*-
"""扫描期拓扑图构建与查询

核心数据结构：以交换机为节点、端口为边属性的图，
显式记录"谁连谁、通过哪个端口"，定位时做图遍历而非猜测。
"""
from __future__ import annotations

from app.utils.logging import get_logger
from collections import deque
from dataclasses import dataclass, field
from app.core.enums import LAGStatus

logger = get_logger(__name__)

UNREACHABLE_DEPTH = 999


@dataclass
class SwitchNode:
    sw_id: int
    room_id: int
    layer: int
    is_core: bool
    management_ip: str | None
    gateway_ips: set[str] = field(default_factory=set)
    lag_members: dict[str, set[str]] = field(default_factory=dict)
    _member_to_lag: dict[str, str] = field(default_factory=dict, repr=False)

    def add_lag(self, lag_name: str, member_ports: set[str]) -> None:
        self.lag_members[lag_name] = member_ports
        for p in member_ports:
            self._member_to_lag[p] = lag_name

    def resolve_lag_port(self, port: str) -> str:
        return self._member_to_lag.get(port, port)


@dataclass
class TopologyLink:
    sw_a: int
    port_a: str
    sw_b: int
    port_b: str
    is_trunk: bool
    lag_group_id: int | None = None


@dataclass
class LocationResult:
    sw_id: int | None
    port: str | None
    room_id: int | None
    kind: str
    confidence: str


class TopologyGraph:

    def __init__(self):
        self.nodes: dict[int, SwitchNode] = {}
        self.links: list[TopologyLink] = []
        self._adjacency: dict[int, list[TopologyLink]] = {}
        self.scope: str = ""
        self._gateway_ip_map: dict[str, SwitchNode] = {}
        self._management_ip_map: dict[str, SwitchNode] = {}
        self._depth_cache: dict[int, int] | None = None

    def add_node(self, node: SwitchNode) -> None:
        self.nodes[node.sw_id] = node
        if node.management_ip:
            self._management_ip_map[node.management_ip] = node
        for ip in node.gateway_ips:
            self._gateway_ip_map[ip] = node
        self._depth_cache = None

    def add_link(self, link: TopologyLink) -> None:
        self.links.append(link)
        self._adjacency.setdefault(link.sw_a, []).append(link)
        self._adjacency.setdefault(link.sw_b, []).append(link)
        self._depth_cache = None

    def add_gateway_ip(self, sw_id: int, ip: str) -> None:
        node = self.nodes.get(sw_id)
        if node and ip not in node.gateway_ips:
            node.gateway_ips.add(ip)
            self._gateway_ip_map[ip] = node

    def get_uplink_ports(self, sw_id: int) -> set[str]:
        ports = set()
        node = self.nodes.get(sw_id)
        for link in self._adjacency.get(sw_id, []):
            if link.sw_a == sw_id:
                port_name = link.port_a
            elif link.sw_b == sw_id:
                port_name = link.port_b
            else:
                continue
            ports.add(port_name)
            if node:
                if port_name in node.lag_members:
                    ports.update(node.lag_members[port_name])
                lag_name = node._member_to_lag.get(port_name)
                if lag_name:
                    ports.add(lag_name)
        return ports

    def get_peer(self, sw_id: int, port: str) -> tuple[int, str] | None:
        for link in self._adjacency.get(sw_id, []):
            if link.sw_a == sw_id and link.port_a == port:
                return link.sw_b, link.port_b
            if link.sw_b == sw_id and link.port_b == port:
                return link.sw_a, link.port_a
        return None

    def find_gateway_owner(self, ip: str) -> SwitchNode | None:
        return self._gateway_ip_map.get(ip)

    def find_management_owner(self, ip: str) -> SwitchNode | None:
        return self._management_ip_map.get(ip)

    def depth_from_core(self, sw_id: int) -> int:
        if self._depth_cache is None:
            self._depth_cache = self._compute_depth_map()
        return self._depth_cache.get(sw_id, UNREACHABLE_DEPTH)

    def _compute_depth_map(self) -> dict[int, int]:
        core_ids = {n.sw_id for n in self.nodes.values() if n.is_core}
        depth_map: dict[int, int] = {}
        if not core_ids:
            for sw_id in self.nodes:
                depth_map[sw_id] = 0
            return depth_map

        queue = deque()
        for cid in core_ids:
            depth_map[cid] = 0
            queue.append(cid)

        while queue:
            cur = queue.popleft()
            cur_depth = depth_map[cur]
            for link in self._adjacency.get(cur, []):
                peer = link.sw_b if link.sw_a == cur else link.sw_a
                if peer not in depth_map:
                    depth_map[peer] = cur_depth + 1
                    queue.append(peer)

        return depth_map


def _is_interconnect_port(port: str, sw_id: int, graph: TopologyGraph) -> bool:
    return port in graph.get_uplink_ports(sw_id)


def resolve_terminal_ip(ip: str, mac: str, graph: TopologyGraph,
                        candidates: list[tuple[int, str]]) -> LocationResult:
    if not candidates:
        return LocationResult(sw_id=None, port=None, room_id=None,
                               kind="unresolved", confidence="none")

    terminal_candidates = [
        (sw_id, port) for sw_id, port in candidates
        if not _is_interconnect_port(port, sw_id, graph)
    ]

    if terminal_candidates:
        best = max(terminal_candidates, key=lambda c: graph.depth_from_core(c[0]))
        sw_id, port = best
        node = graph.nodes.get(sw_id)
        resolved_port = node.resolve_lag_port(port) if node else port
        return LocationResult(sw_id=sw_id, port=resolved_port,
                               room_id=node.room_id if node else None,
                               kind="terminal_exact", confidence="high")

    def _segment_sort_key(c):
        sw_id, port = c
        depth = graph.depth_from_core(sw_id)
        is_lag = 1 if ("eth-trunk" in port.lower() or "port-channel" in port.lower()) else 0
        return (depth, -is_lag)

    best = max(candidates, key=_segment_sort_key)
    sw_id, port = best
    node = graph.nodes.get(sw_id)
    resolved_port = node.resolve_lag_port(port) if node else port
    return LocationResult(sw_id=sw_id, port=resolved_port,
                           room_id=node.room_id if node else None,
                           kind="segment_estimate", confidence="low")


def resolve_terminal_ip_with_redis(ip: str, mac: str, graph: TopologyGraph,
                                    initial_candidates: list[tuple[int, str]],
                                    mac_index_lookup) -> LocationResult:
    result = resolve_terminal_ip(ip, mac, graph, initial_candidates)

    if result.kind == "terminal_exact":
        return result

    deeper = _search_deeper_for_mac_with_redis(graph, initial_candidates, mac, mac_index_lookup)
    if deeper:
        sw_id, port = deeper
        node = graph.nodes.get(sw_id)
        return LocationResult(sw_id=sw_id, port=port,
                               room_id=node.room_id if node else None,
                               kind="terminal_via_trunk_trace", confidence="medium")

    return result


def _search_deeper_for_mac_with_redis(graph: TopologyGraph,
                                       current_candidates: list[tuple[int, str]],
                                       mac: str,
                                       mac_index_lookup) -> tuple[int, str] | None:
    all_mac_candidates = mac_index_lookup(graph.scope, mac)
    mac_by_sw: dict[int, list[tuple[int, str]]] = {}
    for s, p in all_mac_candidates:
        mac_by_sw.setdefault(s, []).append((s, p))

    visited = set()
    frontier = [sw_id for sw_id, _ in current_candidates]
    while frontier:
        next_frontier = []
        for sw_id in frontier:
            if sw_id in visited:
                continue
            visited.add(sw_id)
            for link in graph._adjacency.get(sw_id, []):
                downstream_sw = link.sw_b if link.sw_a == sw_id else link.sw_a
                if downstream_sw in visited:
                    continue
                downstream_matches = mac_by_sw.get(downstream_sw, [])
                for s, p in downstream_matches:
                    if not _is_interconnect_port(p, s, graph):
                        ds_node = graph.nodes.get(s)
                        resolved_p = ds_node.resolve_lag_port(p) if ds_node else p
                        return s, resolved_p
                next_frontier.append(downstream_sw)
        frontier = next_frontier

    best: tuple[int, str] | None = None
    best_depth = -1
    for s, p in all_mac_candidates:
        if _is_interconnect_port(p, s, graph):
            continue
        depth = graph.depth_from_core(s)
        if depth > best_depth:
            best_depth = depth
            best = (s, p)
    if best:
        s, p = best
        ds_node = graph.nodes.get(s)
        resolved_p = ds_node.resolve_lag_port(p) if ds_node else p
        return s, resolved_p

    return None


def resolve_ip_location(ip: str, mac: str | None, graph: TopologyGraph,
                        mac_candidates: list[tuple[int, str]]) -> LocationResult:
    owner = graph.find_management_owner(ip)
    if owner:
        return LocationResult(sw_id=owner.sw_id, port=None, room_id=owner.room_id,
                               kind="management_ip", confidence="exact")

    owner = graph.find_gateway_owner(ip)
    if owner:
        return LocationResult(sw_id=owner.sw_id, port=None, room_id=owner.room_id,
                               kind="gateway_ip", confidence="exact")

    if mac and mac_candidates:
        return resolve_terminal_ip(ip, mac, graph, mac_candidates)

    return LocationResult(sw_id=None, port=None, room_id=None,
                           kind="unresolved", confidence="none")


def build_topology_graph(scope: str, switch_metas: list, db_session) -> TopologyGraph:
    from app.models.network_connection import NetworkConnection
    from app.models.network_port import NetworkPort
    from app.models.link_aggregation import LinkAggregationGroup
    from app.utils.port_name_utils import normalize_port as _np

    graph = TopologyGraph()
    graph.scope = scope

    sw_ids = [m.id for m in switch_metas]

    for m in switch_metas:
        graph.add_node(SwitchNode(
            sw_id=m.id,
            room_id=m.room_id,
            layer=m.layer,
            is_core=m.is_core,
            management_ip=m.ip,
            gateway_ips=set(),
        ))

    if sw_ids:
        lag_groups = db_session.query(LinkAggregationGroup).filter(
            LinkAggregationGroup.device_id.in_(sw_ids),
            LinkAggregationGroup.status == LAGStatus.ACTIVE,
        ).all()
        for lag in lag_groups:
            node = graph.nodes.get(lag.device_id)
            if not node:
                continue
            member_names = set()
            for mp in lag.member_port_list:
                if mp.port_name:
                    member_names.add(_np(mp.port_name))
            if member_names:
                node.add_lag(_np(lag.lag_name), member_names)

    if sw_ids:
        conns = db_session.query(NetworkConnection).join(
            NetworkPort, NetworkConnection.local_port_id == NetworkPort.id
        ).filter(NetworkPort.device_id.in_(sw_ids)).all()

        external_sw_ids = set()
        for conn in conns:
            if not conn.local_port or not conn.peer_port:
                continue
            sw_a = conn.local_port.device_id
            sw_b = conn.peer_port.device_id
            if sw_a not in graph.nodes:
                external_sw_ids.add(sw_a)
            if sw_b not in graph.nodes:
                external_sw_ids.add(sw_b)

        if external_sw_ids:
            from app.models.device import Device
            external_devices = db_session.query(Device).filter(
                Device.id.in_(external_sw_ids),
                Device.deleted_at.is_(None),
            ).all()
            for dev in external_devices:
                room_id = dev.cabinet.room_id if dev.cabinet else None
                ext = dev.switch_ext if hasattr(dev, 'switch_ext') else None
                graph.add_node(SwitchNode(
                    sw_id=dev.id,
                    room_id=room_id or 0,
                    layer=ext.layer if ext and ext.layer else 3,
                    is_core=(ext.switch_role == 0) if ext and ext.switch_role is not None else False,
                    management_ip=None,
                    gateway_ips=set(),
                ))
            logger.info("拓扑图添加 %d 个外部节点（虚拟机房跨机房连接对端）",
                        len(external_devices),
                        extra={"phase": "topology_build", "scope": scope})

            if external_sw_ids:
                from app.models.switch_route import IPNetwork
                from app.utils.port_name_utils import is_vlan_interface
                gw_rows = db_session.query(
                    IPNetwork.switch_id, IPNetwork.gateway, IPNetwork.port
                ).filter(
                    IPNetwork.switch_id.in_(external_sw_ids),
                    IPNetwork.gateway.isnot(None),
                ).all()
                backfill_count = 0
                for sw_id, gateway, port in gw_rows:
                    if gateway and is_vlan_interface(port or ""):
                        graph.add_gateway_ip(sw_id, gateway)
                        backfill_count += 1
                if backfill_count:
                    logger.info("外部节点网关IP回填: %d 条（来自 ip_networks 历史数据）",
                                backfill_count,
                                extra={"phase": "topology_build", "scope": scope})

            if external_sw_ids:
                ext_lag_groups = db_session.query(LinkAggregationGroup).filter(
                    LinkAggregationGroup.device_id.in_(external_sw_ids),
                    LinkAggregationGroup.status == LAGStatus.ACTIVE,
                ).all()
                for lag in ext_lag_groups:
                    node = graph.nodes.get(lag.device_id)
                    if not node:
                        continue
                    member_names = set()
                    for mp in lag.member_port_list:
                        if mp.port_name:
                            member_names.add(_np(mp.port_name))
                    if member_names:
                        node.add_lag(_np(lag.lag_name), member_names)

        lag_merged: dict[tuple, TopologyLink] = {}

        for conn in conns:
            if not conn.local_port or not conn.peer_port:
                continue
            sw_a = conn.local_port.device_id
            sw_b = conn.peer_port.device_id
            if sw_a not in graph.nodes or sw_b not in graph.nodes:
                continue

            port_a = _np(conn.local_port.port_name)
            port_b = _np(conn.peer_port.port_name)

            node_a = graph.nodes[sw_a]
            node_b = graph.nodes[sw_b]
            lag_a = node_a._member_to_lag.get(port_a)
            lag_b = node_b._member_to_lag.get(port_b)

            if lag_a and lag_b:
                merge_key = (sw_a, lag_a, sw_b, lag_b)
                if merge_key not in lag_merged:
                    link = TopologyLink(
                        sw_a=sw_a, port_a=lag_a,
                        sw_b=sw_b, port_b=lag_b,
                        is_trunk=conn.connection_type == "trunk" if hasattr(conn, "connection_type") else True,
                        lag_group_id=conn.lag_group_id,
                    )
                    lag_merged[merge_key] = link
                    graph.add_link(link)
            else:
                graph.add_link(TopologyLink(
                    sw_a=sw_a, port_a=port_a,
                    sw_b=sw_b, port_b=port_b,
                    is_trunk=conn.connection_type == "trunk" if hasattr(conn, "connection_type") else True,
                ))

    logger.info("拓扑图构建完成: %d 节点, %d 连接",
                len(graph.nodes), len(graph.links),
                extra={"phase": "topology_build", "scope": scope})

    return graph
