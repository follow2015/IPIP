from __future__ import annotations
# -*- coding: utf-8 -*-
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
    """将点分十进制 IP 转为无符号整数，失败返回 None。"""
    if not ip:
        return None
    try:
        return struct.unpack("!I", _socket.inet_aton(ip))[0]
    except (OSError, struct.error):
        return None

_PORT_LOOPBACK_RE = re.compile(r'^loopback|^lo\d', re.IGNORECASE)
_PORT_VLANIF_RE   = re.compile(r'^vlan',            re.IGNORECASE)




class RouteSync:
    """路由表同步：将采集到的路由写入 ip_network，并在 Redis 中建立直连索引

    替代原有 sync_routes 函数在 ScanOrchestrator 中的调用，
    使用 SwitchContext 作为输入，支持端口归一化和 Redis 直连索引。
    """

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
        """同步单台交换机的路由表

        注意：route 记录的 room_id 始终使用 ctx.room_id（交换机物理机房），
        不做跨机房推断 —— 路由表是交换机自身配置，归属关系是确定的，
        与 ARP/MAC 表项需要推断终端实际机房（ip_arp_service._resolve_location）
        是不同的语义。

        Args:
            ctx: SwitchContext 采集结果
            db_session: 数据库 session
            scan_redis: ScanRedis 实例
            topology_graph: TopologyGraph 实例（可选，用于填充网关IP到拓扑图节点）
        """
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
            if self._is_excluded_network(route.network):
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
        """对 port="Unknown" 的路由，通过 Redis 端口IP索引推断出接口

        冷备场景：核心交换机有两条指向同一网段的路由，活跃路由 interface=GE1/0/1，
        非活跃路由 interface=Unknown。但非活跃路由的 nexthop 属于某互联网段
        （如 10.20.1.4/30），该互联网段在端口配置中有明确端口（如 GE1/0/2），
        可通过 Redis 端口IP索引反查推断。

        数据源：Phase 0 采集的端口IP配置（switch_port_ips 表），
        Phase 0c 批量加载到 Redis，Phase 1 路由同步时查询。
        扫描结束后 Redis TTL 自动清理。

        重要：port_ip_find_by_ip 返回 (sw_id, port)，必须验证 sw_id 与当前
        路由的 switch_id 一致，否则会跨交换机错误匹配（如将机房7的网关地址
        匹配到机房3的路由上）。

        Args:
            records: 待写入的路由记录列表（原地修改 port 字段）
            scan_redis: ScanRedis 实例
            scope: 扫描范围标识
        """
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
        """清理数据库中已存在的广播地址 /32 路由

        扫描前可能已存入广播地址路由，此处将其删除。

        Args:
            sw_id: 交换机ID
            room_id: 机房ID
            db_session: 数据库 session
        """
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
        """从端口 IP 索引获取 Vlanif 端口上真实配置的 IP 地址

        优先从 Phase 0c 已加载到 Redis 的 switch_port_ips 数据中读取，
        这是交换机端口上实际配置的 IP，比猜测"网段第一个可用主机地址"更准确。

        当 Redis 索引不可用（如端口名归一化不一致）时，回退到 _infer_gateway。

        Args:
            ctx: SwitchContext 采集结果
            route: ParsedRoute 路由条目
            scan_redis: ScanRedis 实例

        Returns:
            str | None: 网关地址字符串，无法获取时返回 None
        """
        port = route.port  # 已归一化
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
        """从直连路由推算网关地址（fallback）

        直连路由的网关通常是该网段的第一个可用主机 IP。
        例如 10.0.0.0/24 → gateway=10.0.0.1

        仅在端口 IP 索引不可用时作为回退使用。

        Args:
            route: ParsedRoute 路由条目

        Returns:
            str | None: 网关地址字符串，无法推算时返回 None
        """
        try:
            net = ipaddress.ip_network(route.network, strict=False)
            hosts = list(net.hosts())
            return str(hosts[0]) if hosts else None
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _normalize_flags(raw_flags: str) -> str:
        """将适配器输出的 protocol/flags 归一化为标准简写

        华为/H3C 路由表 protocol 字段为 "Direct"/"Static" 等全称，
        归一化后统一为 C/S/O/B 等简写，确保后续判断一致。

        注意：空 flags 不假定为直连（"C"），否则会把解析失败的非直连路由
        误判为直连，导致跨机房错误候选。
        空值保留为 "UNKNOWN"，_is_connected 会返回 False。

        Args:
            raw_flags: 原始 flags/protocol 字符串

        Returns:
            str: 归一化后的标准简写
        """
        if not raw_flags:
            return "UNKNOWN"
        return RouteSync._FLAGS_MAPPING.get(
            raw_flags.lower(), raw_flags.upper()
        )

    @staticmethod
    def _is_connected(flags: str) -> bool:
        """直连路由判断

        归一化后只需比较 "C"。

        Args:
            flags: 路由标志（已归一化）

        Returns:
            bool: 是否为直连路由
        """
        return flags == "C"

    @staticmethod
    def _is_blackhole(nexthop: str) -> bool:
        """判断 nexthop 是否为黑洞路由

        Args:
            nexthop: 下一跳地址

        Returns:
            bool: 是否为黑洞路由
        """
        nh = nexthop.lower()
        return "null" in nh or "blackhole" in nh

    @staticmethod
    def _classify_connected_route(prefix_len: int, port: str) -> int:
        """直连路由分类（flags == 'C'）

        以接口类型为主判据，前缀长度为辅：
        - Loopback → 互联地址
        - /32 + Vlanif → 网关地址
        - /32 + 其他 → 互联地址
        - Vlanif 非 /32 → 子网路由
        - /30、/31 → 互联地址
        - 其余 → 子网路由

        Args:
            prefix_len: 前缀长度
            port: 归一化后的端口名

        Returns:
            int: RouteNotes 枚举值
        """
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
        """根据路由特征自动分类路由类型

        判断优先级（决策树）：

        1. 默认路由   — network == "0.0.0.0/0"
        2. 黑洞路由   — nexthop 含 NULL / BLACKHOLE
        3. 主机路由   — /32 且非直连（静态或动态学习的主机条目）
        4. 网络路由   — 其余非直连（静态/OSPF/BGP 等）
        5. 直连路由   — 委托 _classify_connected_route

        Args:
            route: ParsedRoute 路由条目（flags 已归一化，port 已 normalize_port 处理）

        Returns:
            int: RouteNotes 枚举值
        """
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
        """判断 /32 主机路由是否为某网段的广播地址

        /32 主机路由中，如果该IP是其所属更小网段的广播地址，
        则属于广播地址，不应存入数据库。
        例如: 10.11.1.3/32 是 10.11.1.0/30 的广播地址

        Args:
            network: 路由网段字符串（如 "10.11.1.3/32"）

        Returns:
            bool: 是否为广播地址
        """
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

    @staticmethod
    def _is_excluded_network(network: str) -> bool:
        """判断是否为应排除的特殊网段

        交换机路由表中常出现 loopback / link-local / 未指定地址段 等无业务
        意义的直连路由（如华为/H3C LoopBack 接口的 127.0.0.0/8），这些网段
        不应在网段管理中展示，需在 sync() 入口跳过。

        注意：0.0.0.0/0（默认路由）不在此排除，由 _classify_route 分类为
        RouteNotes.DEFAULT 单独处理。

        Args:
            network: 路由网段字符串（如 "127.0.0.0/8"）

        Returns:
            bool: 是否应排除
        """
        try:
            net = ipaddress.ip_network(network, strict=False)
        except ValueError:
            return False
        addr = net.network_address
        if addr.is_unspecified and net.prefixlen == 0:
            return False
        return addr.is_loopback or addr.is_link_local or addr.is_unspecified

    def _load_existing_keys(self, sw_id: int, room_id: int, db_session) -> set[tuple]:
        """加载现有路由的五元组键集合

        Args:
            sw_id: 交换机ID
            room_id: 机房ID
            db_session: 数据库 session

        Returns:
            set: 现有路由的五元组键集合
        """
        rows = db_session.execute(
            text("SELECT network, switch_id, port "
                 "FROM ip_networks WHERE switch_id=:sid AND room_id=:rid"),
            {"sid": sw_id, "rid": room_id}
        ).fetchall()
        return {(r[0], r[1], r[2] or "") for r in rows}

    def _batch_upsert(self, records: list[dict], room_id: int, db_session) -> None:
        """批量 UPSERT ip_networks（仅网段信息列）

        flags/nexthop/route_type 已迁移至 switch_routes 表，
        此处仅写入 ip_networks 的网段归属信息。

        Args:
            records: 待写入的路由记录列表
            room_id: 机房ID
            db_session: 数据库 session
        """
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
        """批量删除已撤销的网段记录

        删除前先将引用这些 ip_networks 记录的 switch_routes.network_id 置 NULL，
        避免悬空引用导致前端 nexthop/route_type 丢失。
        NexthopResolver 会在 Phase 4 重新回填 network_id。

        使用 executemany 逐条参数绑定，避免动态拼接 OR 条件导致
        SQL 长度膨胀和参数上限溢出。

        Args:
            keys_to_delete: 待删除的三元组键集合 (network, switch_id, port)
            sw_id: 交换机ID
            room_id: 机房ID
            db_session: 数据库 session
        """
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
        """将采集到的路由表完整写入 switch_routes（增量替换）

        每次扫描后，该交换机的 switch_routes 记录应与采集结果完全一致：
        新增的 INSERT、已撤销的 DELETE、已有的 UPDATE。

        Args:
            ctx: SwitchContext 采集结果
            route_records: 已归一化的路由记录列表
            db_session: 数据库 session
        """
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
    """Phase 4 重构：为 switch_routes 补充 network_id（关联 ip_networks）

    原 Phase 4 查找 ip_networks 中 switch_id IS NULL 的行做 nexthop 推断，
    但 RouteSync 写入时 switch_id 始终有值，导致原逻辑为死代码。

    重构后：将 switch_routes 中未关联的记录，通过 destination + switch_id + room_id
    匹配 ip_networks，回填 network_id，建立路由条目与规划网段的双向关联。
    """

    def resolve(self, scope: str, db_session):
        """为 switch_routes 补充 network_id（关联 ip_networks）

        Args:
            scope: 扫描范围标识，"r:{room_id}" 或 "vr:{virtual_room_id}"
            db_session: 数据库 session
        """
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
