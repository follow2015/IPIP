# -*- coding: utf-8 -*-
"""MAC 倒排索引构建服务

Phase 2：构建 MAC→端口 的倒排索引到 Redis，
同时构建端口→MAC 的反向索引，供 Phase 5 L2 降级使用。
"""
from app.utils.logging import get_logger

from app.services.scan_context import SwitchContext
from app.utils.port_name_utils import is_aggregate_interface

logger = get_logger(__name__)


def detect_uplink_ports(ctx: SwitchContext) -> set[str]:
    uplinks = {m.port for m in ctx.macs if is_aggregate_interface(m.port)}

    interconnect_ports = _get_interconnect_ports(ctx.sw_id)
    uplinks |= interconnect_ports

    for m in ctx.macs:
        m.is_uplink = m.port in uplinks

    return uplinks


def _get_interconnect_ports(sw_id: int) -> set[str]:
    try:
        from app.models.network_connection import NetworkConnection
        from app.models.network_port import NetworkPort
        from app.utils.port_name_utils import normalize_port
        from extensions import db

        ports = set()
        conns = NetworkConnection.query.filter(
            db.or_(
                NetworkConnection.local_port.has(NetworkPort.device_id == sw_id),
                NetworkConnection.peer_port.has(NetworkPort.device_id == sw_id),
            )
        ).all()
        for conn in conns:
            if conn.local_port and conn.local_port.device_id == sw_id:
                ports.add(normalize_port(conn.local_port.port_name))
            if conn.peer_port and conn.peer_port.device_id == sw_id:
                ports.add(normalize_port(conn.peer_port.port_name))

        return ports
    except Exception:
        return set()


class MacIndexBuilder:

    def build(self, ctx: SwitchContext, scan_redis) -> None:
        detect_uplink_ports(ctx)
        for m in ctx.macs:
            scan_redis.mac_index_set(
                ctx.scope, m.mac, ctx.sw_id, m.port
            )
            if not m.is_uplink:
                scan_redis.port_mac_add(
                    ctx.scope, ctx.sw_id, m.port, m.mac
                )
