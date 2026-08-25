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
    """ARP 同步：全局合并去重 + 拓扑图驱动定位

    使用 TopologyGraph 替代原有7级 if/elif 启发式评分链：
    ① 管理IP → 直接归属（零遍历）
    ② 网关IP → 直接归属（零遍历）
    ③ 终端IP → 图遍历 + Redis 下游追溯
    ④ 无法定位 → 回退到 ARP 来源交换机 + interface（arp_fallback）
    """

    def __init__(self, ip_repo: IPManagerRepository):
        """初始化 ArpSync

        Args:
            ip_repo: IPManagerRepository 实例（必须由调用方注入，绑定正确的 session）
        """
        self._ip_repo = ip_repo
        self._valid_switch_ids = None  # switch_id 有效性缓存
        self._device_room_map: dict[int, int] = {}  # device_id → room_id 映射
        self._topology_graph: TopologyGraph | None = None  # 拓扑图（由 sync_all 设置）

    def sync_all(self, all_ctxs: list[SwitchContext], db_session, scan_redis,
                 topology_graph: TopologyGraph | None = None) -> None:
        """全局 ARP 合并去重 + 逐条处理

        每条 ARP 失败时 rollback 恢复事务，确保不影响后续条目。

        Args:
            all_ctxs: list[SwitchContext] 所有有权限交换机的上下文
            db_session: 数据库 session
            scan_redis: ScanRedis 实例
            topology_graph: TopologyGraph 实例（必须提供，否则所有IP标记为 unresolved）
        """
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
        """预加载所有有效的 device id 集合（已迁移至 IPManagerRepository.load_valid_switch_ids）"""
        from app.persistence.ip_repositories import IPManagerRepository
        return IPManagerRepository(db_session).load_valid_switch_ids()

    @staticmethod
    def _load_device_room_map(db_session) -> dict[int, int]:
        """预加载 device_id → room_id 映射（已迁移至 IPManagerRepository.load_device_room_map）"""
        from app.persistence.ip_repositories import IPManagerRepository
        return IPManagerRepository(db_session).load_device_room_map()

    def _resolve_location(self, ip: str, arp: ParsedArpEntry, ctx: SwitchContext,
                          scan_redis) -> LocationResult:
        """完整解析一个 IP 的定位信息（不写任何数据库）

        多级定位，所有路径返回统一 LocationResult 结构：
        ① 管理IP → 直接归属该交换机本身（零遍历）
        ② 网关IP → 直接归属配置该网关的交换机（零遍历）
        ③ 终端IP → 图遍历 + Redis 下游追溯
        ④ MAC索引候选兜底 → 图遍历失败时，从MAC候选中取任意候选（confidence=low）
        ⑤ ARP来源交换机回退 → 回退到 ARP 来源交换机 + interface（arp_fallback）
        """
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
        """从 MAC 索引获取候选列表（不带评分，仅原始采集记录）

        返回所有候选供图遍历算法使用。
        """
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
        """处理单条 ARP 记录（统一单次解析 + 末尾原子写入）

        重构版：先完整解析出 (sw_id, port, room_id, confidence)，
        再在末尾统一写入。消除旧版"先写后纠"的多阶段中间状态。

        三级定位：
        ① 管理IP → 直接归属（零遍历）
        ② 网关IP → 直接归属（零遍历）
        ③ 终端IP → 图遍历 + Redis 下游追溯
        ④ 无法定位 → room_id 回退到 ARP 来源交换机机房
        """
        loc = self._resolve_location(ip, arp, ctx, scan_redis)

        self._apply_location(ip, arp.mac, loc, db_session)

        logger.debug("ARP 定位完成",
                     extra={"phase": "arp_sync", "ip": ip, "mac": arp.mac,
                            "sw_id": loc.sw_id, "port": loc.port,
                            "kind": loc.kind, "confidence": loc.confidence,
                            "room_id": loc.room_id})

    def _is_valid_switch(self, sw_id: int) -> bool:
        """校验 switch_id 是否在 devices 表中存在"""
        if self._valid_switch_ids is None:
            return True
        return sw_id in self._valid_switch_ids

    @staticmethod
    def _apply_location(ip: str, mac: str, loc: LocationResult, db_session) -> None:
        """原子化写入：ip_addresses + ip_switch_info + 清理旧记录

        所有路径（管理IP/网关IP/终端IP/unresolved）统一走此方法，
        消除旧版"先写后纠"的多阶段中间状态。

        写入规则：
        - 清理跨房间残留（ip_switch_info + ip_addresses）
        - UPSERT ip_addresses（房间已确定，一次写入）
        - confidence not in (low, none) 且有 sw_id → UPSERT ip_switch_info
          - 有 port：终端IP，写入 switch_id + port
          - 无 port：管理/网关IP，写入 switch_id（覆盖旧记录，port=NULL）
        - confidence in (low, none) → 删除该IP的所有 ip_switch_info（含同房间旧记录），
          避免旧的错误定位数据残留

        room_id 使用定位到的交换机所在机房（loc.room_id），
        确保终端IP归属到实际连接的交换机和机房。
        """
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
