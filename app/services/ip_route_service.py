from __future__ import annotations

"""
路由表同步服务（Phase 1 + Phase 4）

Phase 1 RouteSync：路由表写入 ip_network + Redis 直连索引
Phase 4 NexthopResolver：nexthop 关联推断补充 switch_id/port
"""
import ipaddress
from app.utils.logging import get_logger
import re
import struct
import socket as _socket

from sqlalchemy import text

from app.core.enums import RouteNotes
from app.models.switch_route import _cidr_to_ints

logger = get_logger(__name__)


def _ip_to_int(ip: str | None) -> int | None:
    if not ip:
        return None
    try:
        return struct.unpack("!I", _socket.inet_aton(ip))[0]
    except (OSError, struct.error):
        return None

_PORT_LOOPBACK_RE = re.compile(r'^loopback|^lo\d', re.IGNORECASE)
_PORT_VLANIF_RE   = re.compile(r'^vlan',            re.IGNORECASE)


class RouteSync:

    _FLAGS_MAPPING = {
        "direct": "C",
        "connected": "C",
        "local": "C",
        "static": "S",
        "ospf": "O",
        "bgp": "B",
        "rip": "R",
        "isis": "I",
    }

    def sync(self, ctx, db_session, scan_redis, topology_graph=None) -> None:
        from app.utils.port_name_utils import normalize_port, is_vlan_interface

        existing_keys = self._load_existing_keys(
            ctx.sw_id, ctx.room_id, db_session
        )
        to_upsert = []
        current_keys = set()

        for route in ctx.routes:
            route.flags = self._normalize_flags(route.flags)
            route.port = normalize_port(route.interface)
            if self._is_broadcast_host_route(route.network):
                continue
            key = (route.network, ctx.sw_id, route.port)
            current_keys.add(key)
            route_type = self._classify_route(route)
            gateway = self._get_real_gateway(ctx, route, scan_redis) if self._is_connected(route.flags) else None
            to_upsert.append({
                "ip_network": route.network,
                "switch_id":  ctx.sw_id,
                "port":       route.port,
                "flags":      route.flags,
                "nexthop":    route.nexthop,
                "route_type": route_type,
                "gateway":    gateway,
                "room_id":    ctx.room_id,
            })
            if topology_graph and route_type in (RouteNotes.GATEWAY, RouteNotes.SUBNET) and is_vlan_interface(route.port):
                if gateway:
                    topology_graph.add_gateway_ip(ctx.sw_id, gateway)

        try:
            self._resolve_unknown_ports(to_upsert, scan_redis, ctx.scope)
        except Exception as e:
            logger.warning("推断Unknown端口失败（不影响路由同步）: %s", e)

        current_keys = {(r["ip_network"], r["switch_id"], r["port"]) for r in to_upsert}

        to_delete = existing_keys - current_keys

        self._batch_upsert(to_upsert, ctx.room_id, db_session)
        self._batch_delete(to_delete, ctx.sw_id, ctx.room_id, db_session)
        self._cleanup_broadcast_routes(ctx.sw_id, ctx.room_id, db_session)
        self._sync_switch_routes(ctx, to_upsert, db_session)

    @staticmethod
    def _resolve_unknown_ports(records: list[dict], scan_redis, scope: str) -> None:
        unknown_records = [r for r in records if r["port"] == "Unknown"]
        if not unknown_records:
            return

        for r in unknown_records:
            current_sw_id = r.get("switch_id")
            if r["flags"] != "C":
                nexthop = r.get("nexthop", "")
                if not nexthop or nexthop == "0.0.0.0":
                    continue
                result = scan_redis.port_ip_find_by_ip(scope, nexthop)
                if result:
                    matched_sw_id, port = result
                    if current_sw_id and matched_sw_id != current_sw_id:
                        logger.debug(
                            "推断Unknown端口跳过: nexthop=%s 匹配到 sw_id=%s 但当前路由 sw_id=%s (跨交换机不采用)",
                            nexthop, matched_sw_id, current_sw_id,
                            extra={"phase": "route_sync"}
                        )
                        continue
                    r["port"] = port
                    logger.debug(
                        "推断Unknown端口: nexthop=%s → port=%s (端口IP索引)",
                        nexthop, port,
                        extra={"phase": "route_sync"}
                    )
            else:
                try:
                    net = ipaddress.ip_network(r["ip_network"], strict=False)
                    hosts = list(net.hosts())
                    if not hosts:
                        continue
                    probe_ip = str(hosts[0])
                except ValueError:
                    continue
                result = scan_redis.port_ip_find_by_ip(scope, probe_ip)
                if result:
                    matched_sw_id, port = result
                    if current_sw_id and matched_sw_id != current_sw_id:
                        logger.debug(
                            "推断Unknown端口跳过: 直连网段=%s 匹配到 sw_id=%s 但当前路由 sw_id=%s (跨交换机不采用)",
                            r["ip_network"], matched_sw_id, current_sw_id,
                            extra={"phase": "route_sync"}
                        )
                        continue
                    r["port"] = port
                    logger.debug(
                        "推断Unknown端口: 直连网段=%s → port=%s (端口IP索引)",
                        r["ip_network"], port,
                        extra={"phase": "route_sync"}
                    )

    @staticmethod
    def _cleanup_broadcast_routes(sw_id, room_id, db_session):
        rows = db_session.execute(text(
            "SELECT id, network FROM ip_networks "
            "WHERE switch_id=:sid AND room_id=:rid AND network LIKE '%/32'"
        ), {"sid": sw_id, "rid": room_id}).fetchall()

        to_delete = []
        for row_id, network in rows:
            if RouteSync._is_broadcast_host_route(network):
                to_delete.append(row_id)

        if to_delete:
            db_session.execute(
                text("DELETE FROM ip_networks WHERE id = :id"),
                [{"id": rid} for rid in to_delete]
            )
            logger.info("清理广播地址路由", extra={"phase": "route_sync", "switch_id": sw_id, "deleted": len(to_delete)})

    @staticmethod
    def _get_real_gateway(ctx, route, scan_redis) -> str | None:
        port = route.port
        if port and port != "Unknown":
            try:
                ips = scan_redis.port_ip_get_ips_by_switch_port(
                    ctx.scope, ctx.sw_id, port
                )
                if ips:
                    net = ipaddress.ip_network(route.network, strict=False)
                    for ip_str in ips:
                        try:
                            if ipaddress.ip_address(ip_str) in net:
                                return ip_str
                        except ValueError:
                            continue
                    return ips[0]
            except Exception as e:
                logger.debug("从端口IP索引获取网关失败，回退到推断: %s", e,
                             extra={"phase": "route_sync", "switch_id": ctx.sw_id})
        return RouteSync._infer_gateway(route)

    @staticmethod
    def _infer_gateway(route) -> str | None:
        try:
            net = ipaddress.ip_network(route.network, strict=False)
            hosts = list(net.hosts())
            return str(hosts[0]) if hosts else None
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _normalize_flags(raw_flags: str) -> str:
        if not raw_flags:
            return "UNKNOWN"
        return RouteSync._FLAGS_MAPPING.get(
            raw_flags.lower(), raw_flags.upper()
        )

    @staticmethod
    def _is_connected(flags: str) -> bool:
        return flags == "C"

    @staticmethod
    def _is_blackhole(nexthop: str) -> bool:
        nh = nexthop.lower()
        return "null" in nh or "blackhole" in nh

    @staticmethod
    def _classify_connected_route(prefix_len: int, port: str) -> int:
        is_loopback = _PORT_LOOPBACK_RE.match(port) is not None
        is_vlanif   = _PORT_VLANIF_RE.match(port)   is not None

        if is_loopback:
            return RouteNotes.INTERCONNECT
        if prefix_len == 32:
            return RouteNotes.GATEWAY if is_vlanif else RouteNotes.INTERCONNECT
        if is_vlanif:
            return RouteNotes.SUBNET
        if prefix_len in (30, 31):
            return RouteNotes.INTERCONNECT
        return RouteNotes.SUBNET

    @staticmethod
    def _classify_route(route) -> int:
        network      = route.network
        nexthop      = route.nexthop or ""
        flags        = (route.flags or "").upper()
        port         = route.port or ""
        is_connected = flags == "C"

        if network == "0.0.0.0/0":
            return RouteNotes.DEFAULT

        if RouteSync._is_blackhole(nexthop):
            return RouteNotes.BLACKHOLE

        try:
            net = ipaddress.ip_network(network, strict=False)
            prefix_len = net.prefixlen
        except ValueError:
            return RouteNotes.NETWORK

        if not is_connected:
            if prefix_len == 32:
                return RouteNotes.NEXTHOP
            if prefix_len in (30, 31):
                return RouteNotes.INTERCONNECT
            return RouteNotes.NETWORK

        return RouteSync._classify_connected_route(prefix_len, port)

    @staticmethod
    def _is_broadcast_host_route(network: str) -> bool:
        try:
            net = ipaddress.ip_network(network, strict=False)
        except ValueError:
            return False
        if net.prefixlen != 32:
            return False
        host_ip = net.network_address
        for prefix in (30, 29, 28, 27, 26, 25, 24):
            try:
                parent = ipaddress.ip_network(f"{host_ip}/{prefix}", strict=False)
                if host_ip == parent.broadcast_address:
                    return True
            except ValueError:
                continue
        return False

    def _load_existing_keys(self, sw_id: int, room_id: int, db_session) -> set[tuple]:
        rows = db_session.execute(
            text("SELECT network, switch_id, port "
                 "FROM ip_networks WHERE switch_id=:sid AND room_id=:rid"),
            {"sid": sw_id, "rid": room_id}
        ).fetchall()
        return {(r[0], r[1], r[2] or "") for r in rows}

    def _batch_upsert(self, records: list[dict], room_id: int, db_session) -> None:
        if not records:
            return
        net_rows = []
        for r in records:
            net_rows.append({
                "ip_network": r["ip_network"],
                "switch_id":  r["switch_id"],
                "port":       r["port"],
                "gateway":    r.get("gateway"),
                "room_id":    r["room_id"],
            })
        db_session.execute(text("""
            INSERT INTO ip_networks
                (network, switch_id, port, gateway, room_id, updated_at)
            VALUES
                (:ip_network, :switch_id, :port, :gateway, :room_id, NOW())
            AS _new
            ON DUPLICATE KEY UPDATE
                gateway = _new.gateway,
                updated_at = NOW()
        """), net_rows)

    def _batch_delete(self, keys_to_delete: set[tuple], sw_id: int, room_id: int, db_session) -> None:
        if not keys_to_delete:
            return
        params_nullify = [
            {"net": net, "sid": sw_id, "port": port, "rid": room_id}
            for net, _, port in keys_to_delete
        ]
        db_session.execute(
            text("UPDATE switch_routes sr "
                 "INNER JOIN ip_networks ipn ON sr.network_id = ipn.id "
                 "SET sr.network_id = NULL "
                 "WHERE ipn.network=:net AND ipn.switch_id=:sid "
                 "AND ipn.port=:port AND ipn.room_id=:rid"),
            params_nullify
        )
        params = [
            {"net": net, "sid": sw_id, "port": port, "rid": room_id}
            for net, _, port in keys_to_delete
        ]
        db_session.execute(
            text("DELETE FROM ip_networks "
                 "WHERE network=:net AND switch_id=:sid "
                 "AND port=:port AND room_id=:rid"),
            params
        )

    def _sync_switch_routes(self, ctx, route_records, db_session):
        existing = db_session.execute(text("""
            SELECT destination, nexthop, route_type FROM switch_routes
            WHERE switch_id = :sid AND room_id = :rid
        """), {"sid": ctx.sw_id, "rid": ctx.room_id}).fetchall()
        existing_keys = {(r[0], r[1], r[2]) for r in existing}

        current_keys = set()
        upsert_rows = []
        for r in route_records:
            route_type = r["route_type"]
            key = (r["ip_network"], r["nexthop"], route_type)
            current_keys.add(key)
            dest_int, dest_prefix = _cidr_to_ints(r["ip_network"])
            nh_int = _ip_to_int(r["nexthop"])
            upsert_rows.append({
                "switch_id":   ctx.sw_id,
                "destination": r["ip_network"],
                "nexthop":     r["nexthop"],
                "route_type":  route_type,
                "port":        r["port"],
                "room_id":     ctx.room_id,
                "destination_int": dest_int,
                "destination_prefix": dest_prefix,
                "nexthop_int": nh_int,
            })

        if upsert_rows:
            db_session.execute(text("""
                INSERT INTO switch_routes
                    (switch_id, destination, nexthop, route_type, port, room_id,
                     destination_int, destination_prefix, nexthop_int, updated_at)
                VALUES
                    (:switch_id, :destination, :nexthop, :route_type, :port, :room_id,
                     :destination_int, :destination_prefix, :nexthop_int, NOW())
                AS _new
                ON DUPLICATE KEY UPDATE
                    route_type = _new.route_type,
                    port       = _new.port,
                    destination_int = _new.destination_int,
                    destination_prefix = _new.destination_prefix,
                    nexthop_int = _new.nexthop_int,
                    network_id = NULL,
                    updated_at = NOW()
            """), upsert_rows)

        stale = existing_keys - current_keys
        if stale:
            params = [
                {"sid": ctx.sw_id, "rid": ctx.room_id, "dest": dest, "nh": nh, "rt": rt}
                for dest, nh, rt in stale
            ]
            db_session.execute(
                text("DELETE FROM switch_routes "
                     "WHERE switch_id=:sid AND room_id=:rid "
                     "AND destination=:dest AND nexthop=:nh AND route_type=:rt"),
                params
            )


class NexthopResolver:

    def resolve(self, scope: str, db_session):
        if scope.startswith("r:"):
            room_ids = [int(scope[2:])]
        elif scope.startswith("vr:"):
            from app.services.virtual_room_service import VirtualRoomService
            from app.persistence.virtual_room_repository import VirtualRoomRepository
            room_ids = list(VirtualRoomService(VirtualRoomRepository()).get_covered_room_ids(int(scope[3:])))
        else:
            logger.warning("NexthopResolver.resolve: 无法解析 scope=%s", scope)
            return

        if not room_ids:
            return

        from sqlalchemy import bindparam
        dangling = db_session.execute(text("""
            UPDATE switch_routes sr
            LEFT JOIN ip_networks ipn ON sr.network_id = ipn.id
            SET sr.network_id = NULL, sr.updated_at = NOW()
            WHERE sr.room_id IN :room_ids
              AND sr.network_id IS NOT NULL
              AND ipn.id IS NULL
        """).bindparams(bindparam("room_ids", expanding=True)), {"room_ids": list(room_ids)})
        if dangling.rowcount:
            logger.info("修复悬空 network_id",
                        extra={"phase": "nexthop_resolve", "scope": scope,
                               "dangling_fixed": dangling.rowcount})

        if len(room_ids) == 1:
            result = db_session.execute(text("""
                UPDATE switch_routes sr
                INNER JOIN ip_networks ipn
                  ON ipn.network_int = sr.destination_int
                 AND ipn.prefix = sr.destination_prefix
                 AND ipn.room_id = sr.room_id
                 AND ipn.switch_id = sr.switch_id
                SET sr.network_id = ipn.id, sr.updated_at = NOW()
                WHERE sr.room_id = :rid AND sr.network_id IS NULL
                  AND sr.destination_int IS NOT NULL
            """), {"rid": room_ids[0]})
            result2 = db_session.execute(text("""
                UPDATE switch_routes sr
                INNER JOIN ip_networks ipn
                  ON ipn.network = sr.destination
                 AND ipn.room_id = sr.room_id
                 AND ipn.switch_id = sr.switch_id
                SET sr.network_id = ipn.id, sr.updated_at = NOW()
                WHERE sr.room_id = :rid AND sr.network_id IS NULL
            """), {"rid": room_ids[0]})
            updated = result.rowcount + result2.rowcount
        else:
            result = db_session.execute(text("""
                UPDATE switch_routes sr
                INNER JOIN ip_networks ipn
                  ON ipn.network_int = sr.destination_int
                 AND ipn.prefix = sr.destination_prefix
                 AND ipn.room_id = sr.room_id
                 AND ipn.switch_id = sr.switch_id
                SET sr.network_id = ipn.id, sr.updated_at = NOW()
                WHERE sr.room_id IN :room_ids AND sr.network_id IS NULL
                  AND sr.destination_int IS NOT NULL
            """).bindparams(bindparam("room_ids", expanding=True)), {"room_ids": list(room_ids)})
            result2 = db_session.execute(text("""
                UPDATE switch_routes sr
                INNER JOIN ip_networks ipn
                  ON ipn.network = sr.destination
                 AND ipn.room_id = sr.room_id
                 AND ipn.switch_id = sr.switch_id
                SET sr.network_id = ipn.id, sr.updated_at = NOW()
                WHERE sr.room_id IN :room_ids AND sr.network_id IS NULL
            """).bindparams(bindparam("room_ids", expanding=True)), {"room_ids": list(room_ids)})
            updated = result.rowcount + result2.rowcount
        if updated:
            logger.info("switch_routes.network_id 回填",
                        extra={"phase": "nexthop_resolve", "scope": scope, "updated": updated})
