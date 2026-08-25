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
    """上联端口识别：仅依据 N2N 连接记录 + 聚合口，不再使用 MAC 密度阈值

    通过 N2N 连接记录识别互联端口，聚合口直接标记为上联。
    必须在 MacIndexBuilder.build() 之前调用，填充 ParsedMacEntry.is_uplink。

    Args:
        ctx: 交换机采集上下文

    Returns:
        set[str]: 识别为上联的端口集合
    """
    uplinks = {m.port for m in ctx.macs if is_aggregate_interface(m.port)}

    interconnect_ports = _get_interconnect_ports(ctx.sw_id)
    uplinks |= interconnect_ports

    for m in ctx.macs:
        m.is_uplink = m.port in uplinks

    return uplinks


def _get_interconnect_ports(sw_id: int) -> set[str]:
    """查询交换机的 N2N 互联端口名集合

    通过 NetworkConnection 表查询该交换机参与的网络互联端口，
    这些端口连接其他交换机，不应作为终端定位候选。

    对于 LAG 聚合口（如 Eth-Trunk），仅返回 N2N 连接中记录的端口名，
    不展开物理成员端口名。

    Args:
        sw_id: 交换机 device_id

    Returns:
        set[str]: 互联端口名集合
    """
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
    """MAC 倒排索引构建器

    构建正向索引（MAC→端口）和反向索引（端口→MAC）。
    上联端口识别基于 N2N 连接记录 + 聚合口，不再使用 MAC 密度阈值。
    """

    def build(self, ctx: SwitchContext, scan_redis) -> None:
        """构建 MAC 倒排索引（自动执行上联端口识别）

        内部自动调用 detect_uplink_ports，调用方无需关心顺序。
        同时构建正向索引（MAC→端口）和反向索引（端口→MAC）。

        Args:
            ctx: 交换机采集上下文
            scan_redis: ScanRedis 实例
        """
        detect_uplink_ports(ctx)
        for m in ctx.macs:
            scan_redis.mac_index_set(
                ctx.scope, m.mac, ctx.sw_id, m.port
            )
            if not m.is_uplink:
                scan_redis.port_mac_add(
                    ctx.scope, ctx.sw_id, m.port, m.mac
                )
