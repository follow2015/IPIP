# -*- coding: utf-8 -*-
"""
ARP 同步服务（Phase 3）

全局 ARP 合并去重 + 拓扑图驱动定位。
管理IP/网关IP零遍历直接归属，终端IP图遍历定位。
"""
from app.utils.logging import get_logger

from sqlalchemy import text

from app.persistence.ip_repositories import IPManagerRepository
from app.core.enums import IPStatus
from app.services.scan_context import ParsedArpEntry, SwitchContext
from app.services.topology_graph import (
    TopologyGraph, resolve_terminal_ip_with_redis, LocationResult,
)
from app.utils.port_name_utils import normalize_port

logger = get_logger(__name__)


class ArpSync:

    def __init__(self, ip_repo: IPManagerRepository):
        self._ip_repo = ip_repo
        self._valid_switch_ids = None
        self._device_room_map: dict[int, int] = {}
        self._topology_graph: TopologyGraph | None = None

    def sync_all(self, all_ctxs: list[SwitchContext], db_session, scan_redis,
                 topology_graph: TopologyGraph | None = None) -> None:
        self._valid_switch_ids = self._ip_repo.load_valid_switch_ids()
        self._device_room_map = self._ip_repo.load_device_room_map()
        self._topology_graph = topology_graph

        _BANNED_MACS = {"0000-0000-0001", "0000-0000-0000", "0000.0000.0001", "0000.0000.0000"}
        merged: dict[str, tuple] = {}
        for ctx in all_ctxs:
            if not ctx.has_ssh:
                continue
            for arp in ctx.arps:
                if not arp.mac or arp.mac.upper() == "N/A":
                    continue
                mac_normalized = arp.mac.lower().replace(":", "-")
                if mac_normalized in _BANNED_MACS:
                    continue
                if arp.ip not in merged:
                    merged[arp.ip] = (arp, ctx)
                else:
                    _, existing_ctx = merged[arp.ip]
                    if (ctx.layer, int(ctx.is_core)) < (existing_ctx.layer, int(existing_ctx.is_core)):
                        merged[arp.ip] = (arp, ctx)

        success_count = 0
        fail_count = 0
        for ip, (arp, ctx) in merged.items():
            try:
                nested = db_session.begin_nested()
                try:
                    self._process_arp(ip, arp, ctx, db_session, scan_redis)
                    nested.commit()
                    success_count += 1
                except Exception as e:
                    nested.rollback()
                    fail_count += 1
                    logger.warning("ARP 处理失败", extra={"phase": "arp_sync", "ip": ip, "error": str(e)})
            except Exception as e:
                fail_count += 1
                logger.error("SAVEPOINT 创建失败", extra={"phase": "arp_sync", "error": str(e)})

        db_session.flush()
        if fail_count:
            logger.warning(
                "ARP 同步完成（部分失败）",
                extra={"phase": "arp_sync", "success": success_count, "fail": fail_count}
            )

    @staticmethod
    def _load_valid_switch_ids(db_session) -> set:
        from app.persistence.ip_repositories import IPManagerRepository
        return IPManagerRepository(db_session).load_valid_switch_ids()

    @staticmethod
    def _load_device_room_map(db_session) -> dict[int, int]:
        from app.persistence.ip_repositories import IPManagerRepository
        return IPManagerRepository(db_session).load_device_room_map()

    def _resolve_location(self, ip: str, arp: ParsedArpEntry, ctx: SwitchContext,
                          scan_redis) -> LocationResult:
        if not self._topology_graph:
            if arp.interface:
                fallback_port = normalize_port(arp.interface)
                return LocationResult(
                    sw_id=ctx.sw_id, port=fallback_port, room_id=ctx.room_id,
                    kind="arp_fallback", confidence="low",
                )
            return LocationResult(
                sw_id=None, port=None, room_id=ctx.room_id,
                kind="unresolved", confidence="none",
            )

        owner = self._topology_graph.find_management_owner(ip)
        if owner and self._is_valid_switch(owner.sw_id):
            return LocationResult(
                sw_id=owner.sw_id, port=None,
                room_id=owner.room_id,
                kind="management_ip", confidence="exact",
            )

        owner = self._topology_graph.find_gateway_owner(ip)
        if owner and self._is_valid_switch(owner.sw_id):
            return LocationResult(
                sw_id=owner.sw_id, port=None,
                room_id=owner.room_id,
                kind="gateway_ip", confidence="exact",
            )

        if arp.mac:
            mac_candidates = self._get_mac_candidates(ctx.scope, arp.mac, scan_redis)
            if mac_candidates:
                def mac_lookup(scope, mac_addr):
                    return self._get_mac_candidates(scope, mac_addr, scan_redis)

                result = resolve_terminal_ip_with_redis(
                    ip, arp.mac, self._topology_graph, mac_candidates, mac_lookup,
                )
                logger.debug("拓扑图定位: 终端IP详情",
                             extra={"phase": "arp_sync", "ip": ip, "mac": arp.mac,
                                    "sw_id": result.sw_id, "port": result.port,
                                    "kind": result.kind, "confidence": result.confidence,
                                    "room_id": result.room_id,
                                    "mac_candidates": str(mac_candidates),
                                    "uplink_ports": str(self._topology_graph.get_uplink_ports(ctx.sw_id)) if ctx.sw_id else ""})
                if result.room_id is None:
                    result.room_id = ctx.room_id
                if result.sw_id is None:
                    if mac_candidates:
                        sw_id, port = max(mac_candidates,
                                          key=lambda c: self._topology_graph.depth_from_core(c[0]))
                        node = self._topology_graph.nodes.get(sw_id)
                        return LocationResult(
                            sw_id=sw_id, port=port,
                            room_id=node.room_id if node else ctx.room_id,
                            kind="mac_index_fallback", confidence="low",
                        )

                    if arp.interface:
                        fallback_port = normalize_port(arp.interface)
                        return LocationResult(
                            sw_id=ctx.sw_id, port=fallback_port, room_id=ctx.room_id,
                            kind="arp_fallback", confidence="low",
                        )
                    return LocationResult(
                        sw_id=None, port=None, room_id=ctx.room_id,
                        kind="unresolved", confidence="none",
                    )
                return result

        if arp.interface:
            fallback_port = normalize_port(arp.interface)
            return LocationResult(
                sw_id=ctx.sw_id, port=fallback_port, room_id=ctx.room_id,
                kind="arp_fallback", confidence="low",
            )

        return LocationResult(
            sw_id=None, port=None, room_id=ctx.room_id,
            kind="unresolved", confidence="none",
        )

    def _get_mac_candidates(self, scope: str, mac: str, scan_redis) -> list[tuple[int, str]]:
        key = f"mac_index:{scope}:{mac}"
        all_candidates = scan_redis.r.hgetall(key)
        if not all_candidates:
            return []
        result = []
        for field in all_candidates:
            if isinstance(field, bytes):
                field = field.decode()
            sw_id_str, port = field.split(":", 1)
            result.append((int(sw_id_str), port))
        return result

    def _process_arp(self, ip: str, arp: ParsedArpEntry, ctx: SwitchContext,
                     db_session, scan_redis) -> None:
        loc = self._resolve_location(ip, arp, ctx, scan_redis)

        self._apply_location(ip, arp.mac, loc, db_session)

        logger.debug("ARP 定位完成",
                     extra={"phase": "arp_sync", "ip": ip, "mac": arp.mac,
                            "sw_id": loc.sw_id, "port": loc.port,
                            "kind": loc.kind, "confidence": loc.confidence,
                            "room_id": loc.room_id})

    def _is_valid_switch(self, sw_id: int) -> bool:
        if self._valid_switch_ids is None:
            return True
        return sw_id in self._valid_switch_ids

    @staticmethod
    def _apply_location(ip: str, mac: str, loc: LocationResult, db_session) -> None:
        final_room_id = loc.room_id

        ip_repo = IPManagerRepository(db_session)
        ip_repo.delete_ip_switch_info_cross_room(ip, final_room_id)
        ip_repo.delete_ip_addresses_cross_room(ip, final_room_id)

        ip_repo.upsert_protect_customer(ip, final_room_id, status=IPStatus.ACTIVE)

        if loc.sw_id:
            if loc.port:
                ip_repo.upsert_ip_switch_info_with_port(ip, mac, loc.sw_id, loc.port, final_room_id)
            else:
                ip_repo.upsert_ip_switch_info_no_port(ip, mac, loc.sw_id, final_room_id)
        else:
            ip_repo.delete_ip_switch_info_by_ip(ip)
