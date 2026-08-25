# -*- coding: utf-8 -*-
"""
网络拓扑服务

聚合 DeviceSwitchExt / NetworkConnection / DeviceConnection 数据，
生成前端拓扑图所需的 nodes + edges 结构。
"""
from app.utils.logging import get_logger
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from app.models.device import Device
from app.models.device_switch_ext import DeviceSwitchExt
from app.models.device_connection import DeviceConnection
from app.models.network_connection import NetworkConnection

logger = get_logger(__name__)

MAX_TOPOLOGY_NODES = 500


class TopologyService:


    @staticmethod
    def _switch_query_base():
        from app.models.cabinet import Cabinet
        return (
            Device.query
            .filter(Device.device_type == "network")
            .outerjoin(DeviceSwitchExt, DeviceSwitchExt.device_id == Device.id)
            .options(
                joinedload(Device.switch_ext),
                joinedload(Device.cabinet).joinedload(Cabinet.room),
            )
        )

    @staticmethod
    def _device_query_base():
        from app.models.cabinet import Cabinet
        return (
            Device.query
            .filter(Device.device_type.in_(["network", "server"]))
            .options(
                joinedload(Device.switch_ext),
                joinedload(Device.cabinet).joinedload(Cabinet.room),
            )
        )


    @staticmethod
    def _serialize_node(d: Device) -> Dict[str, Any]:
        from app.core.enums import DeviceStatus
        STATUS_MAP = {
            DeviceStatus.ONLINE: "online",
            DeviceStatus.OFFLINE: "offline",
            DeviceStatus.AVAILABLE: "available",
            DeviceStatus.MAINTENANCE: "maintenance",
            DeviceStatus.RESERVED: "reserved",
        }
        status_str = STATUS_MAP.get(d.status, "unknown")
        node: Dict[str, Any] = {
            "id": d.id,
            "name": d.device_name,
            "device_type": d.device_type,
            "status": status_str,
            "ip": d.management_ip,
            "room_id": d.cabinet.room_id if d.cabinet else None,
            "room_name": d.cabinet.room.name if d.cabinet and d.cabinet.room else None,
            "cabinet_id": d.cabinet_id,
            "cabinet_name": d.cabinet.cabinet_number if d.cabinet else None,
        }
        if d.device_type == "network" and d.switch_ext:
            node.update({
                "switch_role": d.switch_ext.switch_role,
                "layer": d.switch_ext.layer,
                "port_num": d.switch_ext.port_num,
                "uplink_device_id": d.switch_ext.uplink_device_id,
                "core_device_id": d.switch_ext.core_device_id,
            })
        return node


    @staticmethod
    def _get_virtual_room_device_ids(virtual_room_id: int) -> Optional[Set[int]]:
        from app.models.virtual_room import VirtualRoom
        vr = VirtualRoom.query.get(virtual_room_id)
        if vr is None:
            return None
        return {m.device_id for m in vr.members.all()}

    def build_network_topology(
        self,
        room_id: Optional[int] = None,
        virtual_room_id: Optional[int] = None,
        layer: Optional[int] = None,
        include_offline: bool = False,
    ) -> Dict[str, Any]:
        query = self._switch_query_base()
        if virtual_room_id is not None:
            vr_device_ids = self._get_virtual_room_device_ids(virtual_room_id)
            if vr_device_ids is None:
                return {"nodes": [], "edges": [], "stats": self._empty_stats()}
            query = query.filter(Device.id.in_(vr_device_ids))
        elif room_id is not None:
            from app.models.cabinet import Cabinet
            query = query.filter(Device.cabinet.has(Cabinet.room_id == room_id))
        if layer is not None:
            query = query.filter(DeviceSwitchExt.layer == layer)
        if not include_offline:
            from app.core.enums import DeviceStatus
            query = query.filter(Device.status != DeviceStatus.OFFLINE)

        switches = query.all()

        if not switches:
            return {"nodes": [], "edges": [], "stats": self._empty_stats()}

        switch_ids: Set[int] = {s.id for s in switches}

        n2n_conns = (
            NetworkConnection.query
            .filter(
                or_(
                    NetworkConnection.local_device_id.in_(switch_ids),
                    NetworkConnection.peer_device_id.in_(switch_ids),
                )
            )
            .options(
                joinedload(NetworkConnection.local_port),
                joinedload(NetworkConnection.peer_port),
            )
            .all()
        )

        nodes = [self._serialize_node(s) for s in switches]

        edges = []
        seen_n2n_pairs: Set[frozenset] = set()

        for conn in n2n_conns:
            if conn.local_device_id not in switch_ids or conn.peer_device_id not in switch_ids:
                continue

            pair = frozenset([conn.local_device_id, conn.peer_device_id])
            seen_n2n_pairs.add(pair)

            local_port_name = conn.local_port.port_name if conn.local_port else None
            peer_port_name = conn.peer_port.port_name if conn.peer_port else None

            edges.append({
                "id": f"n2n_{conn.id}",
                "source": conn.local_device_id,
                "target": conn.peer_device_id,
                "edge_type": "n2n",
                "connection_type": conn.connection_type,
                "bandwidth": conn.bandwidth,
                "status": conn.status,
                "local_port": local_port_name,
                "peer_port": peer_port_name,
            })

        for s in switches:
            if not s.switch_ext or not s.switch_ext.uplink_device_id:
                continue
            uplink_id = s.switch_ext.uplink_device_id
            if uplink_id not in switch_ids:
                continue
            pair = frozenset([s.id, uplink_id])
            if pair in seen_n2n_pairs:
                continue
            seen_n2n_pairs.add(pair)

            edges.append({
                "id": f"uplink_{s.id}_{uplink_id}",
                "source": s.id,
                "target": uplink_id,
                "edge_type": "uplink",
                "uplink_port_ids": s.switch_ext.uplink_port_ids,
            })

        stats = self._compute_stats(nodes, edges)

        return {"nodes": nodes, "edges": edges, "stats": stats}

    def build_device_topology(
        self,
        room_id: Optional[int] = None,
        virtual_room_id: Optional[int] = None,
        cabinet_id: Optional[int] = None,
        switch_device_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if switch_device_id is not None:
            return self._build_star_topology(switch_device_id)

        query = self._device_query_base()
        if virtual_room_id is not None:
            vr_device_ids = self._get_virtual_room_device_ids(virtual_room_id)
            if vr_device_ids is None:
                return {"nodes": [], "edges": [], "stats": self._empty_stats()}
            query = query.filter(Device.id.in_(vr_device_ids))
        elif room_id is not None:
            from app.models.cabinet import Cabinet
            query = query.filter(Device.cabinet.has(Cabinet.room_id == room_id))
        if cabinet_id is not None:
            query = query.filter(Device.cabinet_id == cabinet_id)

        devices = query.all()
        if not devices:
            return {"nodes": [], "edges": [], "stats": self._empty_stats()}

        if len(devices) > MAX_TOPOLOGY_NODES:
            raise ValueError(
                f"节点数量 {len(devices)} 超过拓扑渲染上限 {MAX_TOPOLOGY_NODES}，"
                "请指定 room_id 或 cabinet_id 缩小范围"
            )

        device_ids: Set[int] = {d.id for d in devices}

        n2n_conns = (
            NetworkConnection.query
            .filter(
                or_(
                    NetworkConnection.local_device_id.in_(device_ids),
                    NetworkConnection.peer_device_id.in_(device_ids),
                )
            )
            .options(
                joinedload(NetworkConnection.local_port),
                joinedload(NetworkConnection.peer_port),
            )
            .all()
        )

        d2n_conns = (
            DeviceConnection.query
            .filter(
                or_(
                    DeviceConnection.device_id.in_(device_ids),
                    DeviceConnection.switch_device_id.in_(device_ids),
                )
            )
            .all()
        )

        nodes = [self._serialize_node(d) for d in devices]

        edges = []
        seen_pairs: Set[frozenset] = set()

        for conn in n2n_conns:
            if conn.local_device_id not in device_ids or conn.peer_device_id not in device_ids:
                continue
            pair = frozenset([conn.local_device_id, conn.peer_device_id])
            seen_pairs.add(pair)

            edges.append({
                "id": f"n2n_{conn.id}",
                "source": conn.local_device_id,
                "target": conn.peer_device_id,
                "edge_type": "n2n",
                "connection_type": conn.connection_type,
                "bandwidth": conn.bandwidth,
                "status": conn.status,
                "local_port": conn.local_port.port_name if conn.local_port else None,
                "peer_port": conn.peer_port.port_name if conn.peer_port else None,
            })

        for conn in d2n_conns:
            if conn.device_id not in device_ids or conn.switch_device_id not in device_ids:
                continue
            pair = frozenset([conn.device_id, conn.switch_device_id])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            edges.append({
                "id": f"d2n_{conn.id}",
                "source": conn.device_id,
                "target": conn.switch_device_id,
                "edge_type": "d2n",
                "connection_type": conn.connection_type,
                "bandwidth": conn.bandwidth,
                "status": conn.status,
                "switch_port": conn.switch_port.port_name if conn.switch_port else None,
            })

        stats = self._compute_device_stats(nodes, edges)
        return {"nodes": nodes, "edges": edges, "stats": stats}

    def _build_star_topology(self, switch_device_id: int) -> Dict[str, Any]:
        from app.models.cabinet import Cabinet

        switch = (
            Device.query
            .filter(Device.id == switch_device_id, Device.device_type == "network")
            .options(
                joinedload(Device.switch_ext),
                joinedload(Device.cabinet).joinedload(Cabinet.room),
            )
            .first()
        )
        if not switch:
            return {"nodes": [], "edges": [], "stats": self._empty_stats()}

        d2n_conns = (
            DeviceConnection.query
            .filter(DeviceConnection.switch_device_id == switch_device_id)
            .all()
        )

        n2n_conns = (
            NetworkConnection.query
            .filter(
                or_(
                    NetworkConnection.local_device_id == switch_device_id,
                    NetworkConnection.peer_device_id == switch_device_id,
                )
            )
            .options(
                joinedload(NetworkConnection.local_port),
                joinedload(NetworkConnection.peer_port),
            )
            .all()
        )

        peer_ids: Set[int] = (
            {c.device_id for c in d2n_conns}
            | {c.local_device_id for c in n2n_conns}
            | {c.peer_device_id for c in n2n_conns}
        ) - {switch_device_id}

        peers = (
            Device.query
            .options(
                joinedload(Device.switch_ext),
                joinedload(Device.cabinet).joinedload(Cabinet.room),
            )
            .filter(Device.id.in_(peer_ids))
            .all()
        ) if peer_ids else []

        all_devices = [switch] + peers
        nodes = [self._serialize_node(d) for d in all_devices]

        all_device_ids: Set[int] = {d.id for d in all_devices}
        edges = []
        for conn in d2n_conns:
            if conn.device_id in all_device_ids and conn.switch_device_id in all_device_ids:
                edges.append({
                    "id": f"d2n_{conn.id}",
                    "source": conn.device_id,
                    "target": conn.switch_device_id,
                    "edge_type": "d2n",
                    "connection_type": conn.connection_type,
                    "bandwidth": conn.bandwidth,
                    "status": conn.status,
                    "switch_port": conn.switch_port.port_name if conn.switch_port else None,
                })

        for conn in n2n_conns:
            if conn.local_device_id in all_device_ids and conn.peer_device_id in all_device_ids:
                edges.append({
                    "id": f"n2n_{conn.id}",
                    "source": conn.local_device_id,
                    "target": conn.peer_device_id,
                    "edge_type": "n2n",
                    "connection_type": conn.connection_type,
                    "bandwidth": conn.bandwidth,
                    "status": conn.status,
                    "local_port": conn.local_port.port_name if conn.local_port else None,
                    "peer_port": conn.peer_port.port_name if conn.peer_port else None,
                })

        stats = self._compute_device_stats(nodes, edges)
        return {"nodes": nodes, "edges": edges, "stats": stats}


    def auto_detect_topology(
        self,
        room_id: int,
        dry_run: bool = True,
        force: bool = False,
    ) -> Dict[str, Any]:
        from app.models.cabinet import Cabinet
        switches = (
            self._switch_query_base()
            .filter(Device.cabinet.has(Cabinet.room_id == room_id))
            .all()
        )
        if not switches:
            return {"changes": [], "dry_run": dry_run}

        switch_ids: Set[int] = {s.id for s in switches}

        n2n_conns = (
            NetworkConnection.query
            .filter(
                or_(
                    NetworkConnection.local_device_id.in_(switch_ids),
                    NetworkConnection.peer_device_id.in_(switch_ids),
                )
            )
            .all()
        )

        adjacency: Dict[int, Set[int]] = defaultdict(set)
        for conn in n2n_conns:
            if conn.local_device_id in switch_ids and conn.peer_device_id in switch_ids:
                adjacency[conn.local_device_id].add(conn.peer_device_id)
                adjacency[conn.peer_device_id].add(conn.local_device_id)

        degree: Dict[int, int] = {sid: len(adjacency.get(sid, set())) for sid in switch_ids}

        core_ids: Set[int] = set()
        for s in switches:
            if s.switch_ext and s.switch_ext.switch_role == 0:
                core_ids.add(s.id)

        if not core_ids and degree:
            max_degree = max(degree.values())
            if max_degree > 0:
                for threshold_factor in (0.6, 0.8, 1.0):
                    threshold = max_degree * threshold_factor
                    candidates = {sid for sid, d in degree.items() if d >= threshold}
                    if len(candidates) <= len(switch_ids) * 0.4:
                        core_ids = candidates
                        break
                else:
                    max_d = max(degree.values())
                    core_ids = {min(
                        (sid for sid, d in degree.items() if d == max_d),
                        key=lambda x: x,
                    )}

        if not core_ids and degree:
            max_d = max(degree.values())
            core_ids = {sid for sid, d in degree.items() if d == max_d}

        layer_map: Dict[int, int] = {}
        visited: Set[int] = set()
        queue = deque()

        for cid in sorted(core_ids, key=lambda x: -degree.get(x, 0)):
            layer_map[cid] = 1
            visited.add(cid)
            queue.append(cid)

        while queue:
            current = queue.popleft()
            current_layer = layer_map[current]
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    layer_map[neighbor] = current_layer + 1
                    visited.add(neighbor)
                    queue.append(neighbor)

        for sid in switch_ids:
            if sid not in layer_map:
                layer_map[sid] = 2

        uplink_map: Dict[int, int] = {}
        core_map: Dict[int, int] = {}

        for sid in switch_ids:
            if sid in core_ids:
                continue
            my_layer = layer_map.get(sid, 2)
            neighbors = adjacency.get(sid, set())
            candidates = [
                (nid, layer_map.get(nid, 999))
                for nid in neighbors
                if layer_map.get(nid, 999) < my_layer
            ]
            if candidates:
                candidates.sort(key=lambda x: (x[1], -degree.get(x[0], 0)))
                uplink_map[sid] = candidates[0][0]

            current = uplink_map.get(sid)
            visited_uplink: Set[int] = set()
            while current and current not in visited_uplink:
                visited_uplink.add(current)
                if current in core_ids:
                    core_map[sid] = current
                    break
                current = uplink_map.get(current)
            else:
                if current in visited_uplink:
                    logger.debug("uplink 追溯到环路，设备 %d 无法归属核心", sid)
                else:
                    logger.debug("uplink 链路断裂，设备 %d 无法追溯到核心", sid)

        changes = []
        switch_ext_map: Dict[int, DeviceSwitchExt] = {
            s.switch_ext.device_id: s.switch_ext
            for s in switches
            if s.switch_ext
        }

        for sid in switch_ids:
            ext = switch_ext_map.get(sid)
            if not ext:
                continue

            change: Dict[str, Any] = {
                "device_id": sid,
                "device_name": ext.device.device_name if ext.device else str(sid),
                "fields": {},
            }

            inferred_role = 0 if sid in core_ids else 1
            if force or ext.switch_role is None:
                if ext.switch_role != inferred_role:
                    change["fields"]["switch_role"] = {
                        "old": ext.switch_role,
                        "new": inferred_role,
                    }

            inferred_layer = layer_map.get(sid, 2)
            if force or ext.layer is None:
                if ext.layer != inferred_layer:
                    change["fields"]["layer"] = {
                        "old": ext.layer,
                        "new": inferred_layer,
                    }

            inferred_uplink = uplink_map.get(sid)
            if force or ext.uplink_device_id is None:
                if ext.uplink_device_id != inferred_uplink:
                    change["fields"]["uplink_device_id"] = {
                        "old": ext.uplink_device_id,
                        "new": inferred_uplink,
                    }

            inferred_core = core_map.get(sid)
            if force or ext.core_device_id is None:
                if ext.core_device_id != inferred_core:
                    change["fields"]["core_device_id"] = {
                        "old": ext.core_device_id,
                        "new": inferred_core,
                    }

            if change["fields"]:
                changes.append(change)

        if not dry_run and changes:
            for change in changes:
                ext = switch_ext_map.get(change["device_id"])
                if not ext:
                    continue
                for field, values in change["fields"].items():
                    setattr(ext, field, values["new"])
            logger.info(
                "自动推断拓扑完成，更新 %d 条记录 (room_id=%s)",
                len(changes), room_id,
            )

        return {"changes": changes, "dry_run": dry_run}


    @staticmethod
    def _empty_stats() -> Dict[str, int]:
        return {
            "total_nodes": 0,
            "total_edges": 0,
            "core_count": 0,
            "access_count": 0,
            "online_count": 0,
            "offline_count": 0,
        }

    @staticmethod
    def _compute_stats(nodes: List[Dict], edges: List[Dict]) -> Dict[str, int]:
        core_count = sum(1 for n in nodes if n.get("switch_role") == 0)
        access_count = sum(1 for n in nodes if n.get("switch_role") == 1)
        online_count = sum(1 for n in nodes if n.get("status") != "offline")
        offline_count = sum(1 for n in nodes if n.get("status") == "offline")
        return {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "core_count": core_count,
            "access_count": access_count,
            "online_count": online_count,
            "offline_count": offline_count,
        }

    @staticmethod
    def _compute_device_stats(nodes: List[Dict], edges: List[Dict]) -> Dict[str, Any]:
        switch_count = sum(1 for n in nodes if n.get("device_type") == "network")
        server_count = sum(1 for n in nodes if n.get("device_type") == "server")
        online_count = sum(1 for n in nodes if n.get("status") != "offline")
        offline_count = sum(1 for n in nodes if n.get("status") == "offline")
        n2n_count = sum(1 for e in edges if e.get("edge_type") == "n2n")
        d2n_count = sum(1 for e in edges if e.get("edge_type") == "d2n")
        return {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "switch_count": switch_count,
            "server_count": server_count,
            "online_count": online_count,
            "offline_count": offline_count,
            "n2n_count": n2n_count,
            "d2n_count": d2n_count,
        }
