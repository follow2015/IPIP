# -*- coding: utf-8 -*-
"""
Phase 6a: 路由驱动的 IP switch_info 补填

旧版 update_ip_network_ip_ipinfo 为路由覆盖网段内的所有 IP 写入 switch_id/port，
新版 Phase 3 ARP 同步只处理 ARP 表中出现的 IP，导致仅通过路由表可发现的 IP
丢失 switch_id 信息。此服务补填这些 IP 的交换机归属。

逻辑：
1. 查询 ip_networks 中 SUBNET 类型的直连路由（终端子网）
2. 对每个网段，查找 ip_addresses 中存在（活跃/封禁状态）但 ip_switch_info 中缺失的 IP
3. 将这些 IP 的 switch_id 从路由记录写入 ip_switch_info（不写入 port，因为路由的 port 是 Vlanif）

注意：路由表的 port 是 Vlanif（VLAN 接口），不是物理端口。
写入 Vlanif 端口会导致 IP 错误归属到核心交换机的 VLAN 接口，
因此只补填 switch_id，不补填 port。
"""
import ipaddress
from app.utils.logging import get_logger

from sqlalchemy import text, bindparam

from app.core.enums import RouteNotes, IPStatus

logger = get_logger(__name__)


class RouteIPInfoService:
    """路由驱动的 IP switch_info 补填"""

    BATCH_SIZE = 500

    def fill_from_routes(self, scope: str, db_session) -> None:
        """为路由覆盖网段内缺少 switch_info 的 IP 补填交换机归属

        Args:
            scope: 扫描范围标识，"r:{room_id}" 或 "vr:{virtual_room_id}"
            db_session: 数据库 session
        """
        room_ids = self._resolve_room_ids(scope, db_session)
        if not room_ids:
            return

        routes = self._load_subnet_routes(room_ids, db_session)
        if not routes:
            return

        total_filled = 0
        for network_cidr, switch_id, room_id in routes:
            try:
                net = ipaddress.ip_network(network_cidr, strict=False)
                if net.prefixlen == 32 or net.num_addresses > 4096:
                    continue
            except ValueError:
                continue

            filled = self._fill_missing_ips(
                net, switch_id, room_id, db_session
            )
            total_filled += filled

        if total_filled:
            logger.info(
                "[Phase6a] 路由驱动IP信息补填完成: %d 条",
                total_filled,
                extra={"phase": "route_ip_info", "scope": scope},
            )

    @staticmethod
    def _resolve_room_ids(scope: str, db_session=None) -> list[int]:
        """从 scope 解析 room_id 列表"""
        if scope.startswith("r:"):
            return [int(scope[2:])]
        elif scope.startswith("vr:"):
            from app.services.virtual_room_service import VirtualRoomService
            from app.persistence.virtual_room_repository import VirtualRoomRepository
            return list(VirtualRoomService(VirtualRoomRepository(db_session)).get_covered_room_ids(int(scope[3:])))
        return []

    @staticmethod
    def _load_subnet_routes(room_ids: list[int], db_session) -> list[tuple]:
        """加载 SUBNET 类型的直连路由

        Returns:
            list[tuple]: [(network, switch_id, room_id), ...]
            注意：不再返回 port，因为路由表的 port 是 Vlanif，不是物理端口
        """
        if not room_ids:
            return []
        rows = db_session.execute(
            text("""
                SELECT ipn.network, ipn.switch_id, ipn.room_id
                FROM ip_networks ipn
                INNER JOIN switch_routes sr
                  ON sr.network_id = ipn.id AND sr.switch_id = ipn.switch_id
                WHERE ipn.room_id IN :rids
                  AND sr.route_type = :subnet
                  AND ipn.network NOT LIKE '%/32'
            """).bindparams(bindparam("rids", expanding=True)),
            {"rids": list(room_ids), "subnet": int(RouteNotes.SUBNET)},
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def _fill_missing_ips(
        self, net: ipaddress.IPv4Network, switch_id: int,
        room_id: int, db_session,
    ) -> int:
        """为网段内缺少 ip_switch_info 的活跃/封禁 IP 补填交换机归属

        只补填 switch_id，不补填 port（路由的 port 是 Vlanif，不是物理端口）。
        只补填活跃（status=0）和封禁（status=2）的 IP，不补填未使用（status=3）的 IP。

        Args:
            net: 网段对象
            switch_id: 交换机 device_id
            room_id: 机房ID
            db_session: 数据库 session

        Returns:
            int: 补填的记录数
        """
        from app.models.ip_model import ip_to_int

        start_int = ip_to_int(str(net.network_address))
        end_int = ip_to_int(str(net.broadcast_address))

        missing = db_session.execute(text("""
            SELECT ia.ip_address
            FROM ip_addresses ia
            LEFT JOIN ip_switch_info isi
              ON isi.ip_address = ia.ip_address AND isi.room_id = ia.room_id
            WHERE ia.room_id = :rid
              AND ia.ip_int BETWEEN :s AND :e
              AND ia.status IN (:active, :banned)
              AND isi.ip_address IS NULL
        """), {"rid": room_id, "s": start_int, "e": end_int,
               "active": int(IPStatus.ACTIVE), "banned": int(IPStatus.BANNED)}).fetchall()

        if not missing:
            return 0

        ip_list = [r[0] for r in missing]
        filled = 0
        for i in range(0, len(ip_list), self.BATCH_SIZE):
            batch = ip_list[i:i + self.BATCH_SIZE]
            rows = [
                {
                    "ip": ip,
                    "sid": switch_id,
                    "rid": room_id,
                }
                for ip in batch
            ]
            db_session.execute(text("""
                INSERT IGNORE INTO ip_switch_info
                    (ip_address, mac_address, switch_id, port, room_id, updated_at)
                VALUES (
                    :ip, NULL, :sid, NULL,
                    :rid, NOW()
                )
            """), rows)
            filled += len(batch)

        return filled
