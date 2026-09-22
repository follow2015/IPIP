# -*- coding: utf-8 -*-
"""无权限交换机降级处理

Phase 5：对无 SSH 权限的交换机后面的 IP 进行降级定位。
- L3 无权限：网段级降级，MAC 丢弃
- L2 无权限：端口级降级，MAC 保留
"""
import ipaddress
from app.utils.logging import get_logger

from sqlalchemy import text, bindparam

from app.services.topology_graph import LocationResult
from app.services.ip_arp_service import ArpSync

logger = get_logger(__name__)


def _resolve_room_ids(scope: str, db_session) -> list[int]:
    """从 scope 解析涉及的 room_id 列表

    Args:
        scope: 扫描范围标识，"r:{room_id}" 或 "vr:{virtual_room_id}"
        db_session: 数据库 session

    Returns:
        list[int]: room_id 列表
    """
    if scope.startswith("r:"):
        return [int(scope[2:])]
    elif scope.startswith("vr:"):
        from app.services.virtual_room_service import VirtualRoomService
        from app.persistence.virtual_room_repository import VirtualRoomRepository
        return list(VirtualRoomService(VirtualRoomRepository()).get_covered_room_ids(int(scope[3:])))
    return []


class NoAuthL3Degrader:
    """三层无权限交换机降级处理

    职责：对无权限 L3 交换机网段下的所有 IP 统一指向上游降级端口。
    """

    def degrade(self, no_auth_sw_ip: str, scope: str,
                db_session, scan_redis):
        """执行 L3 降级

        Args:
            no_auth_sw_ip: 无权限交换机的管理 IP
            scope: 扫描范围标识
            db_session: 数据库 session
            scan_redis: ScanRedis 实例
        """
        fallback = scan_redis.fallback_get(scope, no_auth_sw_ip)
        if not fallback:
            logger.error(f"[L3Degrader] {no_auth_sw_ip} 无降级映射，跳过")
            return
        upstream_sw_id, upstream_port = fallback

        room_ids = _resolve_room_ids(scope, db_session)

        target_networks = self._get_managed_networks(
            no_auth_sw_ip, room_ids, db_session
        )
        if not target_networks:
            logger.warning(f"[L3Degrader] {no_auth_sw_ip} 无管理网段，跳过")
            return

        for network in target_networks:
            ips_in_net = self._get_ips_in_network(
                network, room_ids, db_session
            )
            for ip, mac, ip_room_id in ips_in_net:
                loc = LocationResult(
                    sw_id=upstream_sw_id, port=upstream_port,
                    room_id=ip_room_id,
                    kind="degraded_l3", confidence="low",
                )
                ArpSync._apply_location(ip, mac or "", loc, db_session)

        db_session.flush()
        logger.info(f"[L3Degrader] {no_auth_sw_ip} 降级完成: "
                    f"upstream={upstream_sw_id}:{upstream_port}")

    @staticmethod
    def _get_managed_networks(sw_ip, room_ids: list[int], db_session) -> list[str]:
        """从 ip_networks 取该无权限交换机的直连网段

        flags 已迁移至 switch_routes 表，通过 JOIN 查询直连路由对应的网段。

        Args:
            sw_ip: 交换机管理IP
            room_ids: 机房ID列表
            db_session: 数据库 session

        Returns:
            list[str]: 直连网段 CIDR 列表
        """
        if not room_ids:
            return []

        from app.persistence.switch_ext_repository import SwitchExtRepository
        from app.persistence.ip_repositories import IPNetworkRepository

        sw_id = SwitchExtRepository(db_session).find_switch_device_id_by_ip(
            sw_ip, room_ids,
        )
        if sw_id is None:
            return []
        return IPNetworkRepository(db_session).list_subnet_networks_for_switch(
            sw_id, room_ids,
        )

    @staticmethod
    def _get_ips_in_network(network: str, room_ids: list[int],
                             db_session) -> list[tuple]:
        """从 ip_addresses 取该网段下所有 IP，LEFT JOIN ip_switch_info 取已知 MAC

        使用 ip_int 索引列做范围查询，避免 INET_ATON 实时计算。

        Args:
            network: 网段 CIDR
            room_ids: 机房ID列表
            db_session: 数据库 session

        Returns:
            list[tuple]: (ip_address, mac_address, room_id) 列表
        """
        if not room_ids:
            return []

        try:
            net = ipaddress.ip_network(network, strict=False)
        except ValueError:
            return []
        from app.models.ip_model import ip_to_int
        start_int = ip_to_int(str(net.network_address))
        end_int = ip_to_int(str(net.broadcast_address))
        from app.persistence.ip_repositories import IPManagerRepository

        rows = IPManagerRepository(db_session).list_ips_with_mac_in_range(
            room_ids, start_int, end_int,
        )
        return [(r[0], r[1], r[2]) for r in rows]


class NoAuthL2Degrader:
    """二层无权限交换机降级处理

    端口级降级，MAC 保留真实值。
    通过上游端口的 MAC 集合反查 IP，仅更新属于该 L2 交换机网段的 IP。
    """

    def degrade(self, no_auth_l2_sw_ip: str, scope: str,
                all_ctxs, db_session, scan_redis):
        """执行 L2 降级

        Args:
            no_auth_l2_sw_ip: 无权限 L2 交换机的管理 IP
            scope: 扫描范围标识
            all_ctxs: list[SwitchContext] 所有采集上下文
            db_session: 数据库 session
            scan_redis: ScanRedis 实例
        """
        fallback = scan_redis.fallback_get(scope, no_auth_l2_sw_ip)
        if not fallback:
            logger.error(f"[L2Degrader] {no_auth_l2_sw_ip} 无降级映射，跳过")
            return
        upstream_sw_id, upstream_port = fallback

        macs_on_port = scan_redis.port_mac_get(
            scope, upstream_sw_id, upstream_port
        )

        if not macs_on_port:
            upstream_ctx = next(
                (c for c in all_ctxs if c.sw_id == upstream_sw_id), None
            )
            if upstream_ctx:
                macs_on_port = {
                    m.mac for m in upstream_ctx.macs
                    if m.port == upstream_port
                }

        if not macs_on_port:
            logger.warning(f"[L2Degrader] {no_auth_l2_sw_ip} "
                           f"上游端口 {upstream_port} 无 MAC，跳过")
            return

        room_ids = _resolve_room_ids(scope, db_session)
        target_networks = self._get_managed_networks(
            no_auth_l2_sw_ip, room_ids, db_session
        )

        updated = 0
        for mac in macs_on_port:
            from app.persistence.ip_repositories import IPSwitchInfoRepository

            ip_row = IPSwitchInfoRepository(db_session).find_first_by_mac(
                mac, room_ids,
            )
            if not ip_row:
                continue
            ip, ip_room_id = ip_row[0], ip_row[1]
            if not _ip_in_networks(ip, target_networks):
                continue
            loc = LocationResult(
                sw_id=upstream_sw_id, port=upstream_port,
                room_id=ip_room_id,
                kind="degraded_l2", confidence="low",
            )
            ArpSync._apply_location(ip, mac, loc, db_session)
            updated += 1

        if updated:
            db_session.flush()
        logger.info(f"[L2Degrader] {no_auth_l2_sw_ip} 降级完成: "
                    f"upstream={upstream_sw_id}:{upstream_port}, "
                    f"updated={updated}")

    @staticmethod
    def _get_managed_networks(sw_ip, room_ids: list[int], db_session) -> list[str]:
        """从 ip_networks 取该无权限 L2 交换机的归属网段

        L2 交换机通常没有自己的路由条目，若无记录则用管理 IP 推算 /24 网段。

        Args:
            sw_ip: 交换机管理IP
            room_ids: 机房ID列表
            db_session: 数据库 session

        Returns:
            list[str]: 网段 CIDR 列表
        """
        if not room_ids:
            return []

        from app.persistence.switch_ext_repository import SwitchExtRepository
        from app.persistence.ip_repositories import IPNetworkRepository

        sw_id = SwitchExtRepository(db_session).find_switch_device_id_by_ip(
            sw_ip, room_ids,
        )
        if sw_id is None:
            return []
        rows = IPNetworkRepository(db_session).list_non_host_networks(
            sw_id, room_ids,
        )
        if rows:
            return rows
        return [str(ipaddress.ip_interface(f"{sw_ip}/24").network)]


def _ip_in_network(ip_str: str, net) -> bool:
    """判断 IP 是否在网段内

    Args:
        ip_str: IP 地址字符串
        net: ipaddress 网络对象

    Returns:
        bool: 是否在网段内
    """
    try:
        return ipaddress.ip_address(ip_str) in net
    except ValueError:
        return False


def _ip_in_networks(ip_str: str, networks: list[str]) -> bool:
    """判断 IP 是否在任一网段内

    Args:
        ip_str: IP 地址字符串
        networks: 网段 CIDR 列表

    Returns:
        bool: 是否在任一网段内
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        return any(
            ip_obj in ipaddress.ip_network(n, strict=False)
            for n in networks
        )
    except ValueError:
        return False
