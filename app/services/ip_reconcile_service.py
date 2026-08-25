# -*- coding: utf-8 -*-
"""
Phase 6: IP 全量对账

将 ip_networks 中的规划 IP 段展开为 ip_addresses 全量记录，
并根据本次 ARP 扫描结果设置正确的在线状态。
"""
import ipaddress
from app.utils.logging import get_logger

from app.core.enums import IPStatus
from app.persistence.ip_repositories import IPManagerRepository

logger = get_logger(__name__)


class IPReconcileService:
    """IP 全量对账：规划段 → ip_addresses 全量写入"""

    MAX_NETWORK_SIZE = 4096   # 超过 /20（4094 主机）的网段跳过展开，防 OOM
    BATCH_SIZE = 500          # 每批次 UPSERT 数量，平衡内存与事务大小

    def __init__(self, ip_repo: IPManagerRepository):
        """初始化 IPReconcileService

        Args:
            ip_repo: IPManagerRepository 实例（必须由调用方注入，绑定正确的 session）
        """
        self._ip_repo = ip_repo

    def reconcile(self, scope: str, active_ips: set[str], db_session, arp_banned_ips: set[str] | None = None):
        """执行 IP 对账（逐网段流式处理）

        将 ip_networks 中每个规划段的主机 IP 逐网段写入 ip_addresses，
        并根据 ARP 扫描结果设置正确状态。逐网段处理降低内存峰值。

        v5 陈旧度模型：只更新 active/banned + last_active_at，不做 inactive 降级。
        inactive 降级挪到独立的陈旧度清理任务（sweep_stale_active_ips）。

        Args:
            scope: 扫描范围标识，"r:{room_id}" 或 "vr:{virtual_room_id}"
            active_ips: 本次 ARP 扫描发现的活跃 IP 集合
            db_session: 数据库 session
            arp_banned_ips: ARP 中 MAC 为封禁标记(0000-0000-0001/0000-0000-0000)的 IP 集合
        """
        if scope.startswith("r:"):
            room_ids = [int(scope[2:])]
        elif scope.startswith("vr:"):
            from app.services.virtual_room_service import VirtualRoomService
            from app.persistence.virtual_room_repository import VirtualRoomRepository
            room_ids = list(VirtualRoomService(VirtualRoomRepository(db_session)).get_covered_room_ids(int(scope[3:])))
        else:
            room_ids = []

        ip_repo = self._ip_repo

        planned_networks = ip_repo.load_planned_networks(room_ids)
        if not planned_networks:
            logger.warning("无规划网段，跳过对账", extra={"phase": "reconcile", "scope": scope})
            return

        _banned_set = arp_banned_ips or set()
        banned_ips = ip_repo.load_blackhole_ips(room_ids) | _banned_set

        total_planned = total_active = total_banned = 0

        for net_cidr, net_room_id in planned_networks:
            try:
                net = ipaddress.ip_network(net_cidr, strict=False)
                if net.num_addresses > self.MAX_NETWORK_SIZE:
                    logger.warning("网段过大，跳过展开", extra={"phase": "reconcile", "network": net_cidr})
                    continue
            except ValueError:
                continue

            host_ips = [str(h) for h in net.hosts()]
            total_planned += len(host_ips)

            for i in range(0, len(host_ips), self.BATCH_SIZE):
                batch = host_ips[i:i + self.BATCH_SIZE]
                skip_ips = ip_repo.find_existing_ips_in_other_rooms(batch, net_room_id)
                insert_batch = [ip for ip in batch if ip not in skip_ips]
                ip_repo.batch_insert_ignore_ips(insert_batch, net_room_id, int(IPStatus.UNUSED))

            active_batch = [ip for ip in host_ips if ip in active_ips]
            banned_batch = [ip for ip in host_ips if ip in banned_ips]

            ip_repo.batch_update_active_status_with_timestamp(active_batch, net_room_id)
            ip_repo.batch_update_banned_status(banned_batch, net_room_id)

            total_active += len(active_batch)
            total_banned += len(banned_batch)
            db_session.flush()

        db_session.flush()
        logger.info(
            "对账完成",
            extra={"phase": "reconcile", "scope": scope,
                   "planned": total_planned, "active": total_active,
                   "banned": total_banned}
        )
