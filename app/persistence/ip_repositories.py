# -*- coding: utf-8 -*-
"""
IP 域 Repository

提供 IPManager、IPNetwork 的数据访问方法。
包含客户信息保护（R-02）、黑洞路由查询等关键业务逻辑。
"""
import ipaddress
from app.utils.logging import get_logger
from datetime import datetime
from typing import Dict, List, Optional
from app.utils.time_utils import now_utc_naive

from sqlalchemy import update, delete, text, func, bindparam, select
from sqlalchemy.orm import joinedload
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.persistence.base import BaseRepository
from app.core.pagination_limits import ensure_offset_within_limit
from app.models.ip_model import IPManager
from app.models.switch_route import IPNetwork, SwitchRoute
from app.models.switch_credentials import SwitchCredentials, IPSwitchInfo
from app.models.customer import Customer
from app.models.room import Room
from app.core.enums import IPStatus, RouteNotes
from extensions import db

logger = get_logger(__name__)


class IPManagerRepository(BaseRepository):
    """IPManager 数据访问层

    继承 BaseRepository，增加 IP 域特有的查询方法。
    """

    def __init__(self, session=None):
        super().__init__(IPManager, session or db.session)

    def list_unbound_by_ips(self, ips) -> List[IPManager]:
        """取地址集合内**未分配给客户**且非 UNUSED 的 IP 行。

        B-44 收敛（删除设备时的 IP 释放）：``customer_id IS NULL`` 是"池内
        未分配"口径 —— 已分配给客户的 IP **不得**被设备删除顺手置回 UNUSED
        （那会凭空制造可用地址）；``status != UNUSED`` 排除已是空闲的行。
        """
        return (
            self.session.query(IPManager)
            .filter(
                IPManager.ip_address.in_(tuple(ips)),
                IPManager.customer_id.is_(None),
                IPManager.status != int(IPStatus.UNUSED),
            )
            .all()
        )

    def list_ips_with_mac_in_range(
        self, room_ids, start_int: int, end_int: int,
    ) -> List[tuple]:
        """网段内 ``(ip_address, mac_address, room_id)``（LEFT JOIN ip_switch_info）。

        B-46 批 5（scan_degrader 降级定位）：MAC 可能缺失（LEFT JOIN ⇒ None），
        调用方据此决定是否可定位 —— 写成 INNER JOIN 会静默丢掉无 MAC 的 IP。
        """
        ids = list(room_ids)
        if not ids:
            return []
        return self.session.execute(
            text("""SELECT im.ip_address, ii.mac_address, im.room_id
            FROM ip_addresses im
            LEFT JOIN ip_switch_info ii
              ON ii.ip_address = im.ip_address AND ii.room_id = im.room_id
            WHERE im.room_id IN :rids
              AND im.ip_int BETWEEN :s AND :e""")
            .bindparams(bindparam("rids", expanding=True)),
            {"rids": ids, "s": start_int, "e": end_int},
        ).fetchall()

    def list_by_statuses_and_ips(self, room_id: int, statuses, ips) -> List[str]:
        """该机房内状态命中且地址在给定集合内的 IP（B-46 批 5：探测筛选）。

        以 500 一批由调用方分块（``IN :ips`` expanding 绑定，原实现即如此）。
        """
        if not ips:
            return []
        rows = self.session.execute(
            text("""
                SELECT ip_address FROM ip_addresses
                WHERE room_id = :rid
                  AND status IN :statuses
                  AND ip_address IN :ips
            """).bindparams(
                bindparam("statuses", expanding=True),
                bindparam("ips", expanding=True),
            ),
            {"rid": room_id, "statuses": [int(s) for s in statuses], "ips": list(ips)},
        ).fetchall()
        return [r[0] for r in rows]

    def count_active_without_location(self, room_id: int) -> int:
        """在线(ACTIVE)但无定位记录的 IP 数（B-46 批 5：一致性对账①）。"""
        from app.core.enums import IPStatus

        return self.session.execute(
            text("SELECT COUNT(*) FROM ip_addresses ia "
                 "LEFT JOIN ip_switch_info si "
                 "  ON si.ip_address = ia.ip_address AND si.room_id = ia.room_id "
                 "WHERE ia.room_id = :rid AND ia.status = :active AND si.id IS NULL"),
            {"rid": room_id, "active": int(IPStatus.ACTIVE)},
        ).scalar() or 0

    def count_banned_without_record(self, room_id: int) -> int:
        """封禁(BANNED)但无封禁单的 IP 数（B-46 批 5：一致性对账②）。"""
        from app.core.enums import IPStatus

        return self.session.execute(
            text("SELECT COUNT(*) FROM ip_addresses ia "
                 "LEFT JOIN ip_ban_records br "
                 "  ON br.ip_address = ia.ip_address AND br.room_id = ia.room_id "
                 "WHERE ia.room_id = :rid AND ia.status = :banned AND br.id IS NULL"),
            {"rid": room_id, "banned": int(IPStatus.BANNED)},
        ).scalar() or 0

    def count_by_status_in_ip_range(
        self, first_ip_int: int, last_ip_int: int,
        customer_id: int, room_id: int,
    ) -> List[tuple]:
        """按状态统计某网段内该客户在该机房的 IP 数（去重 ip_address）。

        B-44 收敛（customer_service 资产报告的 IP 状态分布）：返回
        ``[(status, count), ...]`` —— 调用方只要统计行，行本身无意义。
        """
        rows = (
            self.session.query(
                IPManager.status,
                func.count(func.distinct(IPManager.ip_address)).label("count"),
            )
            .filter(
                IPManager.ip_int >= first_ip_int,
                IPManager.ip_int <= last_ip_int,
                IPManager.customer_id == customer_id,
                IPManager.room_id == room_id,
            )
            .group_by(IPManager.status)
            .all()
        )
        return [(r[0], r[1]) for r in rows]

    def list_by_ip_room_pairs(self, ip_addrs, room_ids) -> List[IPManager]:
        """按 (ip_address IN, room_id IN) 取 IP 行（B-44 收敛：封禁一致性对账）。

        [WARN] 双 IN 是**刻意的笛卡尔收缩**（原实现即如此）：调用方按
        ``(ip_address, room_id)`` 二元组建映射，行多取了也只是被丢掉。
        """
        return (
            self.session.query(IPManager)
            .filter(
                IPManager.ip_address.in_(tuple(ip_addrs)),
                IPManager.room_id.in_(tuple(room_ids)),
            )
            .all()
        )

    def list_pending_status(self, room_id: Optional[int] = None) -> List[IPManager]:
        """取处于**过渡态**（PENDING_BAN / PENDING_UNBAN）的 IP 行。

        B-44 收敛（pending 超时对账：进程在阶段 1 commit 后、阶段 3 完成前
        崩溃时会留下过渡态行）。``room_id`` 传 None = 全机房范围（原实现即如此）。
        """
        query = self.session.query(IPManager).filter(
            IPManager.status.in_((IPStatus.PENDING_BAN, IPStatus.PENDING_UNBAN))
        )
        if room_id is not None:
            query = query.filter(IPManager.room_id == room_id)
        return query.all()

    def list_by_room_ids_and_status(self, room_ids, statuses) -> List[IPManager]:
        """取机房集合内指定状态的 IP（排除 ``ip_int IS NULL`` 的行）。

        B-44 部署计划批：容量统计只认 UNUSED/INACTIVE；``ip_int`` 为 NULL 的行
        无法参与排序/网段换算，原实现显式 ``isnot(None)``，此处保留。
        """
        ids = tuple(room_ids)
        if not ids:
            return []
        return (
            self.session.query(IPManager)
            .filter(
                IPManager.room_id.in_(ids),
                IPManager.status.in_([int(s) for s in statuses]),
                IPManager.ip_int.isnot(None),
            )
            .all()
        )

    def get_by_ip_room(self, ip: str, room_id: int) -> Optional[IPManager]:
        """根据 IP + 机房ID 查询记录

        Args:
            ip: IP地址
            room_id: 机房ID

        Returns:
            Optional[IPManager]: 记录对象，不存在返回None
        """
        return self.find_one({"ip_address": ip, "room_id": room_id})

    def get_by_ips_room(self, ip_list: List[str], room_id: int) -> Dict[str, IPManager]:
        """根据 IP 列表 + 机房ID 批量查询记录（避免 N+1）

        Args:
            ip_list: IP地址列表
            room_id: 机房ID

        Returns:
            Dict[str, IPManager]: IP地址 → 记录对象映射
        """
        if not ip_list:
            return {}
        rows = self.session.query(IPManager).filter(
            IPManager.ip_address.in_(ip_list),
            IPManager.room_id == room_id,
        ).all()
        return {r.ip_address: r for r in rows}

    def get_by_ips(
        self, ip_list: List[str], room_id: Optional[int] = None,
    ) -> List[IPManager]:
        """根据 IP 列表批量查询记录行（机房可选，不传则跨机房）

        供批量归属变更审计留痕使用：需要先读出变更前状态，才能只给
        「真正发生变化」的 IP 留痕，避免记录无变化的假日志。

        注意返回**行列表**而非 ip→记录 映射：room_id 未限定时，同一私网 IP
        可能存在于多个机房（同 IP 不同 room_id 是不同实例），按 ip 做 dict
        键会静默折叠多行，导致审计漏记/机房归属张冠李戴。

        Args:
            ip_list: IP地址列表
            room_id: 机房ID，不传则不按机房过滤

        Returns:
            List[IPManager]: 匹配的记录行（每行含各自的 ip_address/room_id）
        """
        if not ip_list:
            return []
        filters = [IPManager.ip_address.in_(ip_list)]
        if room_id is not None:
            filters.append(IPManager.room_id == room_id)
        return self.session.query(IPManager).filter(*filters).all()

    def find_customer_ids_in_cidr(
        self, room_id: int, network_cidr: str, only_unassigned: bool = False,
    ) -> Dict[str, Optional[int]]:
        """查询网段内各 IP 的当前客户归属（值快照）

        供网段级归属变更审计留痕使用：必须在 UPDATE **之前**调用并把结果
        保存为普通值字典——Core update() 经 session 执行时
        synchronize_session='auto' 会把已加载 ORM 对象同步成新值，
        UPDATE 后再读会拿到新归属。

        Args:
            room_id: 机房ID（私网时用于过滤，公网时忽略）
            network_cidr: 网段CIDR
            only_unassigned: True 时只查 customer_id IS NULL 的 IP
                （对应网段分配 force=False 的「只填空」语义）

        Returns:
            Dict[str, Optional[int]]: IP地址 → 当前客户ID（未分配为 None）
        """
        net = ipaddress.ip_network(network_cidr, strict=False)
        from app.models.ip_model import ip_to_int
        start_int = ip_to_int(str(net.network_address))
        end_int = ip_to_int(str(net.broadcast_address))
        filters = [IPManager.ip_int.between(start_int, end_int)]
        if net.is_private:
            filters.append(IPManager.room_id == room_id)
        if only_unassigned:
            filters.append(IPManager.customer_id.is_(None))
        rows = self.session.query(
            IPManager.ip_address, IPManager.customer_id,
        ).filter(*filters).all()
        return {r.ip_address: r.customer_id for r in rows}

    def _find_existing_null_room_ips(self, ip_list: List[str]) -> set:
        """返回库中已存在且 ``room_id IS NULL`` 的 IP 集合。

        MySQL 唯一约束 ``unique_ip_room(ip_address, room_id)`` 对 NULL 不去重，
        room_id 为空时同一 IP 可被重复插入（2026-09-24 重复 10.0.1.2 事故），
        故 NULL 机房场景必须在应用层显式查重。
        """
        unique_ips = {ip for ip in ip_list if ip}
        if not unique_ips:
            return set()
        rows = self.session.query(IPManager.ip_address).filter(
            IPManager.ip_address.in_(unique_ips),
            IPManager.room_id.is_(None),
        ).all()
        return {row[0] for row in rows}

    def _drop_null_room_duplicates(self, rows: List[dict]) -> List[dict]:
        """剔除 room_id 为空且「库中已存在或本批已出现」的重复行。"""
        null_ips = [
            r["ip_address"] for r in rows
            if r.get("room_id") is None and r.get("ip_address")
        ]
        if not null_ips:
            return rows
        seen = self._find_existing_null_room_ips(null_ips)
        kept: List[dict] = []
        for row in rows:
            ip = row.get("ip_address")
            if row.get("room_id") is None and ip:
                if ip in seen:
                    continue
                seen.add(ip)
            kept.append(row)
        return kept

    def upsert_protect_customer(
        self,
        ip_address: str,
        room_id: int,
        status: int = IPStatus.UNUSED,
        customer_id: Optional[int] = None,
    ) -> None:
        """UPSERT 并保护 customer_id（R-02）

        ON DUPLICATE KEY UPDATE 时不覆盖 customer_id，
        仅在初次 INSERT 时写入；已有记录不触碰 customer_id 字段。

        **观测即刷新（v5 陈旧度模型）**：写入 ``status=ACTIVE`` 意味着"本轮扫描
        真的观测到了这个 IP"，因此**必然**同时刷新 ``last_active_at``。这里不给
        可绕过的开关参数 —— 原实现只有 ARP 之外的路径
        （``batch_update_active_status_with_timestamp``，且仅限规划网段内）写时间戳，
        导致生产 868 行 ACTIVE 中 780 行（90%）``last_active_at`` 为空；而陈旧度
        清理的判据要求 ``last_active_at IS NOT NULL``，这些行**永远不可能被降级**
        （2026-09-24 排查结论）。BANNED(2) 行的 status 与 last_active_at 都不动。

        Args:
            ip_address: IP地址
            room_id: 机房ID
            status: IP状态
            customer_id: 客户ID（仅首次写入）
        """
        touch_last_active = int(status) == int(IPStatus.ACTIVE)
        last_active_expr = text(
            "CASE WHEN ip_addresses.status = 2 THEN ip_addresses.last_active_at "
            "ELSE NOW() END"
        ) if touch_last_active else None

        if room_id is None:
            existing_id = self.session.query(IPManager.id).filter(
                IPManager.ip_address == ip_address,
                IPManager.room_id.is_(None),
            ).scalar()
            if existing_id is not None:
                values = {
                    "status": text(
                        "CASE WHEN ip_addresses.status = 2 THEN 2 ELSE :st END"
                    ),
                    "updated_at": func.now(),
                }
                if last_active_expr is not None:
                    values["last_active_at"] = last_active_expr
                self.session.execute(
                    update(IPManager).where(IPManager.id == existing_id).values(**values),
                    {"st": int(status)},
                )
                self.session.flush()
                return
        insert_values = {
            "ip_address": ip_address,
            "room_id": room_id,
            "status": status,
            "customer_id": customer_id,
        }
        if last_active_expr is not None:
            insert_values["last_active_at"] = func.now()
        stmt = mysql_insert(IPManager).values(**insert_values)
        update_map = {
            "status": text("CASE WHEN ip_addresses.status = 2 THEN 2 ELSE VALUES(status) END"),
            "updated_at": func.now(),
        }
        if last_active_expr is not None:
            update_map["last_active_at"] = last_active_expr
        stmt = stmt.on_duplicate_key_update(**update_map)
        self.session.execute(stmt)
        self.session.flush()

    def update_status(self, ip: str, room_id: int, status: IPStatus) -> None:
        """更新 IP 状态及状态更新时间

        Args:
            ip: IP地址
            room_id: 机房ID
            status: 新状态
        """
        now = now_utc_naive()
        stmt = (
            update(IPManager)
            .where(IPManager.ip_address == ip, IPManager.room_id == room_id)
            .values(status=int(status), updated_at=now)
        )
        self.session.execute(stmt)
        self.session.flush()

    def get_by_status(
        self, status: IPStatus, room_id: Optional[int] = None,
    ) -> List[IPManager]:
        """按状态查询 IP 列表

        Args:
            status: IP状态
            room_id: 可选机房ID过滤

        Returns:
            List[IPManager]: IP记录列表
        """
        filters = {"status": int(status)}
        if room_id is not None:
            filters["room_id"] = room_id
        return self.find_all(filters)

    def bulk_update_customer_where_null(
        self, room_id: int, network_cidr: str, customer_id: Optional[int],
    ) -> int:
        """批量填充同网段内未分配客户 IP 的客户归属（只填空，保留已手工 IP 级分配）

        供 NetworkService.update_network_customer 网段级分配时级联同步：
        仅更新 customer_id IS NULL 的行，已单独分配客户的 IP 不被覆盖。

        公网 IP 全局唯一（同 IP 跨机房只归属一个客户），按 IP 范围全局更新；
        私网 IP 可能跨机房重复（同 IP 不同 room_id 是不同实例），保留 room_id 过滤。

        Args:
            room_id: 机房ID（私网时用于过滤，公网时忽略）
            network_cidr: 网段CIDR
            customer_id: 客户ID（None 表示取消分配，此时无 NULL→NULL 操作，直接跳过）

        Returns:
            int: 更新行数
        """
        if customer_id is None:
            return 0
        net = ipaddress.ip_network(network_cidr, strict=False)
        from app.models.ip_model import ip_to_int
        start_int = ip_to_int(str(net.network_address))
        end_int = ip_to_int(str(net.broadcast_address))
        filters = [
            IPManager.ip_int.between(start_int, end_int),
            IPManager.customer_id.is_(None),
        ]
        if net.is_private:
            filters.append(IPManager.room_id == room_id)
        stmt = (
            update(IPManager)
            .where(*filters)
            .values(customer_id=customer_id)
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def bulk_update_customer_all(
        self, room_id: int, network_cidr: str, customer_id: Optional[int],
    ) -> int:
        """批量覆盖同网段内所有 IP 的客户归属（不保留已分配的，强制更新）

        供 NetworkService.update_network_customer 网段级分配 force=True 时使用：
        更新网段内所有 IP 的 customer_id，不管原值是否为空。

        公网 IP 全局唯一，按 IP 范围全局更新；私网 IP 按 room_id + IP 范围更新。
        customer_id 为 None 时表示取消分配，会把网段内所有 IP 的 customer_id 清空。

        Args:
            room_id: 机房ID（私网时用于过滤，公网时忽略）
            network_cidr: 网段CIDR
            customer_id: 客户ID（None 表示取消分配，清空所有 IP 客户）

        Returns:
            int: 更新行数
        """
        net = ipaddress.ip_network(network_cidr, strict=False)
        from app.models.ip_model import ip_to_int
        start_int = ip_to_int(str(net.network_address))
        end_int = ip_to_int(str(net.broadcast_address))
        filters = [IPManager.ip_int.between(start_int, end_int)]
        if net.is_private:
            filters.append(IPManager.room_id == room_id)
        stmt = (
            update(IPManager)
            .where(*filters)
            .values(customer_id=customer_id)
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def update_customer_by_ip(
        self, ip_address: str, customer_id: Optional[int], room_id: Optional[int] = None,
    ) -> int:
        """更新IP地址的客户关联"""
        filters = [IPManager.ip_address == ip_address]
        if room_id is not None:
            filters.append(IPManager.room_id == room_id)
        stmt = update(IPManager).where(*filters).values(
            customer_id=customer_id, updated_at=func.now(),
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def update_notes_by_ip(
        self, ip_address: str, notes: str, room_id: Optional[int] = None,
    ) -> int:
        """更新IP地址备注"""
        filters = [IPManager.ip_address == ip_address]
        if room_id is not None:
            filters.append(IPManager.room_id == room_id)
        stmt = update(IPManager).where(*filters).values(
            notes=notes, updated_at=func.now(),
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def update_status_by_ip(
        self, ip_address: str, status: int, room_id: Optional[int] = None,
    ) -> int:
        """更新IP状态"""
        filters = [IPManager.ip_address == ip_address]
        if room_id is not None:
            filters.append(IPManager.room_id == room_id)
        stmt = update(IPManager).where(*filters).values(
            status=status, updated_at=now_utc_naive(),
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_update_status_by_ips(
        self, ip_list: List[str], status: int, room_id: int,
    ) -> int:
        """批量更新IP状态"""
        stmt = update(IPManager).where(
            IPManager.ip_address.in_(ip_list),
            IPManager.room_id == room_id,
        ).values(status=status, updated_at=func.now())
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_update_status_to_inactive_preserve_unused(
        self, inactive_ips: List[str], room_id: int,
    ) -> int:
        """将非活跃 IP 标记为 INACTIVE，但保护 UNUSED/BANNED 状态不被覆盖。

        只将当前 status=ACTIVE 的 IP 更新为 INACTIVE。

        Args:
            inactive_ips: 非活跃 IP 列表
            room_id: 机房ID

        Returns:
            int: 影响行数
        """
        stmt = update(IPManager).where(
            IPManager.ip_address.in_(inactive_ips),
            IPManager.room_id == room_id,
            IPManager.status == int(IPStatus.ACTIVE),
        ).values(status=int(IPStatus.INACTIVE), updated_at=func.now())
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_update_active_preserve_banned(
        self, ip_list: List[str],
    ) -> int:
        """将 IP 标记为 ACTIVE，但保护 BANNED 状态不被覆盖。

        Args:
            ip_list: IP 列表

        Returns:
            int: 影响行数
        """
        stmt = update(IPManager).where(
            IPManager.ip_address.in_(ip_list),
            IPManager.status != int(IPStatus.BANNED),
        ).values(status=int(IPStatus.ACTIVE), updated_at=func.now())
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_update_customer_by_ips(
        self, customer_id: int, ip_list: List[str], room_id: Optional[int] = None,
    ) -> int:
        """批量更新IP客户信息"""
        filters = [IPManager.ip_address.in_(ip_list)]
        if room_id is not None:
            filters.append(IPManager.room_id == room_id)
        stmt = update(IPManager).where(*filters).values(
            customer_id=customer_id, updated_at=func.now(),
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_update_notes_by_ips(
        self, notes: str, ip_list: List[str], room_id: Optional[int] = None,
    ) -> int:
        """批量更新IP备注"""
        filters = [IPManager.ip_address.in_(ip_list)]
        if room_id is not None:
            filters.append(IPManager.room_id == room_id)
        stmt = update(IPManager).where(*filters).values(
            notes=notes, updated_at=func.now(),
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def _bulk_upsert(self, rows: List[dict], update_cols: List[str]) -> int:
        """通用 MySQL INSERT ... ON DUPLICATE KEY UPDATE

        Args:
            rows: 与 IPManager 列名匹配的字典列表
            update_cols: 冲突时需要更新的列名列表

        Returns:
            int: 影响行数
        """
        if not rows:
            return 0
        rows = self._drop_null_room_duplicates(rows)
        if not rows:
            return 0
        stmt = mysql_insert(IPManager).values(rows)
        update_map = {c: getattr(stmt.inserted, c) for c in update_cols}
        update_map["updated_at"] = func.now()
        stmt = stmt.on_duplicate_key_update(**update_map)
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def _paginate(self, query, page: int, page_size: int):
        """通用分页：返回 (items, total_count, total_pages)"""
        total = query.count()
        offset = (page - 1) * page_size
        ensure_offset_within_limit(offset)
        items = query.offset(offset).limit(page_size).all()
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return items, total, total_pages

    def bulk_upsert_preserve_customer(self, rows: List[dict]) -> int:
        """批量upsert ip_manager，保留已有customer_id"""
        return self._bulk_upsert(rows, ["room_id"])

    def bulk_upsert_with_customer(self, rows: List[dict]) -> int:
        """批量upsert ip_manager，插入或更新room_id/customer_id/status"""
        return self._bulk_upsert(rows, ["room_id", "customer_id", "status"])

    def bulk_upsert_room_only(self, rows: List[dict]) -> int:
        """批量upsert ip_manager，仅更新room_id"""
        return self._bulk_upsert(rows, ["room_id"])

    def bulk_upsert_update_only(self, rows: List[dict]) -> int:
        """批量upsert ip_manager，已有记录仅更新updated_at"""
        return self._bulk_upsert(rows, [])

    def bulk_upsert_customer_with_room(
        self, updates: List[tuple],
    ) -> int:
        """批量upsert ip_manager，插入(ip,customer_id,room_id)或更新customer_id"""
        rows = [
            {"ip_address": ip, "customer_id": cid, "room_id": rid, "status": IPStatus.UNUSED}
            for ip, cid, rid in updates
        ]
        return self._bulk_upsert(rows, ["customer_id"])

    def batch_delete_by_ips_and_room(self, ip_list: List[str], room_id: int) -> int:
        """批量删除指定机房中的IP记录"""
        stmt = delete(IPManager).where(
            IPManager.ip_address.in_(ip_list),
            IPManager.room_id == room_id,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_delete_no_customer_by_ips_and_room(
        self, ip_list: List[str], room_id: int,
    ) -> int:
        """批量删除无客户关联的IP记录"""
        stmt = delete(IPManager).where(
            IPManager.ip_address.in_(ip_list),
            IPManager.room_id == room_id,
            IPManager.customer_id == None,  # noqa: E711
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_delete_by_ips(self, ip_list: List[str]) -> int:
        """批量删除IP记录（不限机房）"""
        stmt = delete(IPManager).where(IPManager.ip_address.in_(ip_list))
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def find_by_ip_address(
        self, ip_address: str, room_id: Optional[int] = None,
    ) -> Optional[IPManager]:
        """根据IP地址查找记录

        Args:
            ip_address: IP地址
            room_id: 可选机房ID过滤（多机房部署中同一IP可能存在于多个机房）

        Returns:
            Optional[IPManager]: 记录对象，不存在返回None
        """
        query = self.session.query(IPManager).filter(
            IPManager.ip_address == ip_address,
        )
        if room_id is not None:
            query = query.filter(IPManager.room_id == room_id)
        return query.first()

    def find_by_customer_id(
        self, customer_id: int, status: Optional[int] = None,
    ) -> List[IPManager]:
        """根据客户ID查找IP地址"""
        query = self.session.query(IPManager).filter(
            IPManager.customer_id == customer_id,
        )
        if status is not None:
            query = query.filter(IPManager.status == status)
        return query.all()

    def clear_customer(self, customer_id: int) -> int:
        """批量解绑客户名下所有 IP（customer_id 置 NULL）。

        Returns:
            int: 受影响行数
        """
        result = self.session.query(IPManager).filter(
            IPManager.customer_id == customer_id,
        ).update({IPManager.customer_id: None}, synchronize_session=False)
        return result

    def find_by_room_id(
        self, room_id: int, status: Optional[int] = None,
    ) -> List[IPManager]:
        """根据机房ID查找IP地址"""
        query = self.session.query(IPManager).filter(
            IPManager.room_id == room_id,
        )
        if status is not None:
            query = query.filter(IPManager.status == status)
        return query.all()

    def get_status_statistics(
        self, room_id: Optional[int] = None, search: Optional[str] = None,
    ) -> dict:
        """获取IP状态统计

        Args:
            room_id: 可选机房ID过滤
            search: 可选搜索关键词（IP地址或MAC地址，CIDR格式走范围查询）

        Returns:
            dict: 各状态IP数量统计
        """
        query = self.session.query(
            IPManager.status,
            func.count(IPManager.id),
        ).filter(
        )

        if room_id is not None:
            query = query.filter(IPManager.room_id == room_id)

        if search:
            if '/' in search:
                try:
                    net = ipaddress.ip_network(search, strict=False)
                    from app.models.ip_model import ip_to_int
                    start_int = ip_to_int(str(net.network_address))
                    end_int = ip_to_int(str(net.broadcast_address))
                    query = query.filter(
                        IPManager.ip_int.between(start_int, end_int)
                    )
                except ValueError:
                    search_term = f"%{search}%"
                    query = query.filter(
                        IPManager.ip_address.like(search_term)
                    )
            else:
                search_term = f"%{search}%"
                query = query.filter(
                    IPManager.ip_address.like(search_term)
                )

        rows = query.group_by(IPManager.status).all()
        stats = {"total": 0, "active": 0, "inactive": 0, "blocked": 0, "unused": 0}
        for status_val, count in rows:
            stats["total"] += count
            mapping = {0: "active", 1: "inactive", 2: "blocked", 3: "unused"}
            key = mapping.get(status_val)
            if key:
                stats[key] = count
        return stats

    def get_network_type_statistics(self) -> dict:
        """获取公网/私网 IP 分组统计。

        Returns:
            dict: {"private": {"total": N, "active": N, ...}, "public": {"total": N, ...}}
        """
        from sqlalchemy import text as sa_text
        from app.models.ip_model import ip_to_int

        _priv10_s, _priv10_e = ip_to_int("10.0.0.0"), ip_to_int("10.255.255.255")
        _priv172_s, _priv172_e = ip_to_int("172.16.0.0"), ip_to_int("172.31.255.255")
        _priv192_s, _priv192_e = ip_to_int("192.168.0.0"), ip_to_int("192.168.255.255")

        private_stats = {"total": 0, "active": 0, "inactive": 0, "blocked": 0, "unused": 0}
        private_rows = self.session.execute(sa_text("""
            SELECT status, COUNT(*) as cnt FROM ip_addresses
            WHERE (
                ip_int BETWEEN :s1 AND :e1
                OR ip_int BETWEEN :s2 AND :e2
                OR ip_int BETWEEN :s3 AND :e3
            )
            GROUP BY status
        """).bindparams(
            s1=_priv10_s, e1=_priv10_e,
            s2=_priv172_s, e2=_priv172_e,
            s3=_priv192_s, e3=_priv192_e,
        )).fetchall()
        status_key_map = {0: "active", 1: "inactive", 2: "blocked", 3: "unused"}
        for status_val, cnt in private_rows:
            private_stats["total"] += cnt
            key = status_key_map.get(status_val)
            if key:
                private_stats[key] = cnt

        total_stats = self.get_status_statistics()
        public_stats = {
            "total": total_stats["total"] - private_stats["total"],
            "active": total_stats["active"] - private_stats["active"],
            "inactive": total_stats["inactive"] - private_stats["inactive"],
            "blocked": total_stats["blocked"] - private_stats["blocked"],
            "unused": total_stats["unused"] - private_stats["unused"],
        }

        return {"private": private_stats, "public": public_stats}

    def find_notes_by_ip(
        self, ip_address: str, room_id: Optional[int] = None,
    ) -> List[dict]:
        """根据IP地址查询备注记录"""
        query = self.session.query(
            IPManager.id, IPManager.ip_address, IPManager.notes,
            IPManager.created_at, IPManager.updated_at,
        ).filter(IPManager.ip_address == ip_address)
        if room_id is not None:
            query = query.filter(IPManager.room_id == room_id)
        return [row._asdict() for row in query.order_by(IPManager.created_at.desc()).all()]

    def paginate_with_relations(
        self, page: int = 1, page_size: int = 20,
        filters: dict = None, search: str = None,
    ) -> dict:
        """分页查询IP列表（含关联信息：交换机名/端口/客户名/机房名/MAC地址）

        JOIN ip_info / sw_manager / customer_manager / jf_manager_db 四张关联表，
        在 to_dict 基础上追加 switch_name, port, customer_name, room_name, mac_address。

        Args:
            page: 页码
            page_size: 每页数量
            filters: 过滤条件（room_id, status, customer_id, switch_id）
            search: 搜索关键词（IP地址或MAC地址）
        """
        query = self.session.query(IPManager).outerjoin(
            IPManager.ip_switch_info
        ).options(
            joinedload(IPManager.ip_switch_info),
        ).filter(
        )

        if filters:
            if filters.get("room_id") is not None:
                query = query.filter(IPManager.room_id == filters["room_id"])
            if filters.get("status") is not None:
                query = query.filter(IPManager.status == filters["status"])
            if filters.get("customer_id") is not None:
                query = query.filter(IPManager.customer_id == filters["customer_id"])
            if filters.get("switch_id") is not None:
                query = query.filter(IPSwitchInfo.switch_id == filters["switch_id"])

        if search:
            if '/' in search:
                try:
                    net = ipaddress.ip_network(search, strict=False)
                    from app.models.ip_model import ip_to_int
                    start_int = ip_to_int(str(net.network_address))
                    end_int = ip_to_int(str(net.broadcast_address))
                    query = query.filter(
                        IPManager.ip_int.between(start_int, end_int)
                    )
                except ValueError:
                    search_term = f"%{search}%"
                    query = query.filter(
                        IPManager.ip_address.like(search_term)
                        | IPSwitchInfo.mac_address.like(search_term)
                    )
            else:
                search_term = f"%{search}%"
                query = query.filter(
                    IPManager.ip_address.like(search_term)
                    | IPSwitchInfo.mac_address.like(search_term)
                )

        query = query.order_by(IPManager.ip_address)
        items, total_count, total_pages = self._paginate(query, page, page_size)

        room_ids = {item.room_id for item in items if item.room_id}
        customer_ids = {item.customer_id for item in items if item.customer_id}
        switch_ids = set()
        for item in items:
            if item.ip_switch_info and item.ip_switch_info.switch_id:
                switch_ids.add(item.ip_switch_info.switch_id)

        room_map = {}
        if room_ids:
            for r in self.session.query(Room).filter(Room.id.in_(room_ids)).all():
                room_map[r.id] = r.name

        customer_map = {}
        if customer_ids:
            for c in self.session.query(Customer).filter(Customer.id.in_(customer_ids)).all():
                customer_map[c.id] = c.customer_name

        switch_map = {}
        if switch_ids:
            for s in self.session.query(SwitchCredentials).options(
                joinedload(SwitchCredentials.device)
            ).filter(SwitchCredentials.device_id.in_(switch_ids)).all():
                switch_map[s.device_id] = s.device.device_name if s.device else None

        data_list = []
        for item in items:
            item_dict = item.to_dict()
            if item.ip_switch_info:
                item_dict["mac_address"] = item.ip_switch_info.mac_address or "N/A"
                item_dict["port"] = item.ip_switch_info.port
                item_dict["switch_name"] = switch_map.get(item.ip_switch_info.switch_id)
            else:
                item_dict["mac_address"] = "N/A"
                item_dict["port"] = None
                item_dict["switch_name"] = None
            item_dict["customer_name"] = customer_map.get(item.customer_id)
            item_dict["room_name"] = room_map.get(item.room_id)
            data_list.append(item_dict)

        return {
            "data": data_list,
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
        }

    def get_detail_with_relations(self, ip_address: str, room_id: int = None) -> Optional[dict]:
        """获取IP详细信息（含5表JOIN关联数据）

        Args:
            ip_address: IP地址
            room_id: 可选机房ID过滤

        Returns:
            Optional[dict]: 含 switch_name/switch_ip/port/customer_name/room_name/mac_address 的详情字典
        """
        query = self.session.query(IPManager).filter(
            IPManager.ip_address == ip_address,
        )
        if room_id is not None:
            query = query.filter(IPManager.room_id == room_id)

        item = query.first()
        if not item:
            return None

        item_dict = item.to_dict()

        if item.ip_switch_info:
            info = item.ip_switch_info
            item_dict["mac_address"] = info.mac_address or "N/A"
            item_dict["port"] = info.port
            item_dict["updated_at"] = info.updated_at.isoformat() if info.updated_at else None
            if info.switch_id:
                switch = self.session.query(SwitchCredentials).filter(
                    SwitchCredentials.device_id == info.switch_id
                ).first()
                if switch:
                    item_dict["switch_name"] = switch.device.device_name if switch.device else None
                    item_dict["switch_ip"] = switch.ip
        else:
            item_dict["mac_address"] = "N/A"
            item_dict["port"] = None
            item_dict["switch_name"] = None
            item_dict["switch_ip"] = None
            item_dict["updated_at"] = None

        if item.customer_id:
            customer = self.session.get(Customer, item.customer_id)
            item_dict["customer_name"] = customer.customer_name if customer else None
        else:
            item_dict["customer_name"] = None

        if item.room_id:
            room = self.session.get(Room, item.room_id)
            item_dict["room_name"] = room.name if room else None
        else:
            item_dict["room_name"] = None

        return item_dict

    def search_ips(
        self, keyword: str = None, customer_id: int = None,
        room_id: int = None, status: int = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        """搜索IP地址（支持关键词+过滤+分页）"""
        query = self.session.query(IPManager).filter(
        )
        if keyword:
            query = query.filter(
                IPManager.ip_address.contains(keyword) |
                IPManager.notes.contains(keyword)
            )
        if customer_id is not None:
            query = query.filter(IPManager.customer_id == customer_id)
        if room_id is not None:
            query = query.filter(IPManager.room_id == room_id)
        if status is not None:
            query = query.filter(IPManager.status == status)
        items, total, total_pages = self._paginate(query, page, page_size)
        return {
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def search_ips_by_cidr(
        self, network_cidr: str, room_id: int = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        """按CIDR网段范围精确查询IP地址

        Args:
            network_cidr: 网段CIDR（如 10.10.1.0/24）
            room_id: 可选机房ID过滤
            page: 页码
            page_size: 每页数量

        Returns:
            dict: 分页结果
        """
        net = ipaddress.ip_network(network_cidr, strict=False)
        from app.models.ip_model import ip_to_int
        start_int = ip_to_int(str(net.network_address))
        end_int = ip_to_int(str(net.broadcast_address))
        query = self.session.query(IPManager).where(
            IPManager.ip_int.between(start_int, end_int),
        )
        if room_id is not None:
            query = query.filter(IPManager.room_id == room_id)
        items, total, total_pages = self._paginate(query, page, page_size)
        return {
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }


    def load_valid_switch_ids(self) -> set:
        """预加载所有有效的 device id 集合"""
        rows = self.session.execute(
            text("SELECT id FROM devices WHERE deleted_at IS NULL")
        ).fetchall()
        return {r[0] for r in rows}

    def load_device_room_map(self) -> dict[int, int]:
        """预加载 device_id → room_id 映射"""
        rows = self.session.execute(text("""
            SELECT d.id, c.room_id
            FROM devices d JOIN cabinets c ON c.id = d.cabinet_id
            WHERE d.deleted_at IS NULL AND c.room_id IS NOT NULL
        """)).fetchall()
        return {r[0]: r[1] for r in rows}

    _CROSS_ROOM_PREDICATE = "(room_id IS NULL OR room_id <> :rid)"

    def delete_ip_switch_info_cross_room(self, ip: str, room_id: Optional[int]) -> None:
        """清理跨房间残留 ip_switch_info（含 room_id IS NULL 的无归属行）

        防御：``room_id is None`` 时「跨机房」语义不成立（NULL 是「无归属」而非
        「其他机房」），此时显式含 NULL 的判据会退化成「删除该 IP 的所有行」，
        故直接返回，绝不执行删除。
        """
        if room_id is None:
            logger.warning(
                "跨机房清理缺少当前机房（room_id=None），跳过 ip_switch_info 清理",
                extra={"ip": ip},
            )
            return
        self.session.execute(text(
            f"DELETE FROM ip_switch_info WHERE ip_address = :ip "
            f"AND {self._CROSS_ROOM_PREDICATE}"
        ), {"ip": ip, "rid": room_id})

    def delete_ip_addresses_cross_room(self, ip: str, room_id: Optional[int]) -> None:
        """清理跨房间残留 ip_addresses（含 room_id IS NULL 的无归属行）

        防御同 ``delete_ip_switch_info_cross_room``：``room_id is None`` 直接返回。
        """
        if room_id is None:
            logger.warning(
                "跨机房清理缺少当前机房（room_id=None），跳过 ip_addresses 清理",
                extra={"ip": ip},
            )
            return
        self.session.execute(text(
            f"DELETE FROM ip_addresses WHERE ip_address = :ip "
            f"AND {self._CROSS_ROOM_PREDICATE}"
        ), {"ip": ip, "rid": room_id})

    def _upsert_ip_switch_info_row(self, values: dict, update_cols: list[str]) -> None:
        """方言感知 UPSERT ip_switch_info（WP-6 重构：原 MySQL 专有 raw SQL → Core）

        冲突键 = uk_isi_ip_room (ip_address, room_id)。
        - MySQL：ON DUPLICATE KEY UPDATE（语义与原 raw SQL 逐列等价）
        - SQLite（测试库）：ON CONFLICT ... DO UPDATE —— 使降级/来源标记
          可在 sqlite 集成测试中真实执行（原 raw SQL 在测试库无法编译）

        source 无条件以新值覆盖（**最近写入者语义**，含置 NULL）：普通扫描
        覆盖降级行后标记消失，按标记回滚不会误删已被权威数据覆盖的行。
        """
        bind = self.session.get_bind()
        if bind.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            stmt = sqlite_insert(IPSwitchInfo.__table__).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[IPSwitchInfo.__table__.c.ip_address,
                                IPSwitchInfo.__table__.c.room_id],
                set_={c: getattr(stmt.excluded, c) for c in update_cols},
            )
        else:
            stmt = mysql_insert(IPSwitchInfo.__table__).values(**values)
            stmt = stmt.on_duplicate_key_update(
                **{c: getattr(stmt.inserted, c) for c in update_cols})
        self.session.execute(stmt)

    def upsert_ip_switch_info_with_port(self, ip: str, mac: str,
                                         switch_id: int, port: str,
                                         room_id: int,
                                         source: "str | None" = None) -> None:
        """UPSERT ip_switch_info（终端IP：有端口定位）

        source：写入来源标记（WP-6）。None=普通扫描；降级路径传
        degraded_l2/l3[_24fallback]。语义见 _upsert_ip_switch_info_row。
        """
        from app.models.network_port import NetworkPort
        port_id_sq = (
            select(NetworkPort.id)
            .where(NetworkPort.device_id == switch_id,
                   NetworkPort.port_name == port)
            .limit(1).scalar_subquery()
        )
        values = {
            "ip_address": ip, "mac_address": mac, "switch_id": switch_id,
            "port": port, "port_id": port_id_sq, "room_id": room_id,
            "source": source, "updated_at": func.now(),
        }
        self._upsert_ip_switch_info_row(
            values,
            ["mac_address", "switch_id", "port", "port_id", "source", "updated_at"],
        )

    def upsert_ip_switch_info_no_port(self, ip: str, mac: str,
                                       switch_id: int, room_id: int,
                                       source: "str | None" = None) -> None:
        """UPSERT ip_switch_info（管理/网关IP：无端口）——source 语义见 with_port 版"""
        values = {
            "ip_address": ip, "mac_address": mac, "switch_id": switch_id,
            "port": None, "port_id": None, "room_id": room_id,
            "source": source, "updated_at": func.now(),
        }
        self._upsert_ip_switch_info_row(
            values,
            ["mac_address", "switch_id", "port", "port_id", "source", "updated_at"],
        )

    def delete_ip_switch_info_by_ip(self, ip: str) -> None:
        """删除该IP的所有 ip_switch_info（无法定位时清理残留）"""
        self.session.execute(text(
            "DELETE FROM ip_switch_info WHERE ip_address = :ip"
        ), {"ip": ip})


    def load_planned_networks(self, room_ids: list[int]) -> list[tuple[str, int]]:
        """加载机房内的规划网段（排除主机路由），保留每个网段实际所属的 room_id

        重要：同一个 CIDR 字符串可能在不同机房各自配置（如多机房使用相同私网段规划），
        必须保留网段与其配置机房的一一对应关系，不能在虚拟机房场景下对所有覆盖机房
        做笛卡尔积展开 —— 否则会把"只在机房A配置的网段"错误地复制到机房B/C下。

        Args:
            room_ids: 机房ID列表

        Returns:
            list[tuple[str, int]]: [(network_cidr, room_id), ...] 网段与其配置机房的映射
        """
        rows = self.session.execute(
            text("SELECT DISTINCT network, room_id FROM ip_networks WHERE room_id IN :rids AND network NOT LIKE '%/32'")
            .bindparams(bindparam("rids", expanding=True)),
            {"rids": list(room_ids)}
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def load_blackhole_ips(self, room_ids: list[int]) -> set[str]:
        """加载机房内黑洞路由对应的 IP 地址

        黑洞路由（route_type=4）通常是 /32 的静态路由，
        nexthop 为 NULL0/Null0，对应被封禁的 IP。
        route_type 已迁移至 switch_routes 表。

        Args:
            room_ids: 机房ID列表

        Returns:
            set[str]: 被封禁的 IP 地址集合
        """
        rows = self.session.execute(
            text("SELECT sr.destination FROM switch_routes sr WHERE sr.room_id IN :rids AND sr.route_type = :blackhole")
            .bindparams(bindparam("rids", expanding=True)),
            {"rids": list(room_ids), "blackhole": int(RouteNotes.BLACKHOLE)}
        ).fetchall()
        banned_ips = set()
        for (destination,) in rows:
            ip = destination.rsplit("/", 1)[0] if "/" in destination else destination
            banned_ips.add(ip)
        return banned_ips

    def find_existing_ips_in_other_rooms(self, batch: list[str], room_id: Optional[int]) -> set[str]:
        """查找已在其他机房存在的 IP（含 room_id IS NULL 的无归属行）

        判据显式含 NULL（同 ``_CROSS_ROOM_PREDICATE`` 的理由）：无归属行也算
        「不属本机房」。对账据此跳过插入，避免同一 IP 在「无归属行 + 规划行」
        之间产生两条记录。取舍是**宁可少一行，不要多一行**。

        防御：``room_id is None`` 时返回空集合（= 无冲突，照常插入）。这样与
        改造前的行为一致（原判据 ``room_id != NULL`` 恒 unknown，同样返回空集），
        避免因换判据而让对账静默停摆。实践中 room_id 来自
        ``load_planned_networks``（按 ``room_id IN (...)`` 取网段），不会为 None。
        """
        if room_id is None:
            logger.warning(
                "对账查重缺少当前机房（room_id=None），跳过其他机房存在性判定"
            )
            return set()
        rows = self.session.execute(
            text(
                "SELECT ip_address FROM ip_addresses "
                f"WHERE ip_address IN :ips AND {self._CROSS_ROOM_PREDICATE}"
            ).bindparams(bindparam("ips", expanding=True)),
            {"ips": batch, "rid": room_id}
        ).fetchall()
        return {r[0] for r in rows}

    def batch_insert_ignore_ips(self, insert_batch: list[str], room_id: int, status: int) -> None:
        """批量 INSERT IGNORE IP 地址

        Args:
            insert_batch: IP 列表
            room_id: 机房ID
            status: IP 状态
        """
        if not insert_batch:
            return
        if room_id is None:
            existing = self._find_existing_null_room_ips(insert_batch)
            insert_batch = [ip for ip in insert_batch if ip not in existing]
            if not insert_batch:
                return
        self.session.execute(text("""
            INSERT IGNORE INTO ip_addresses (ip_address, room_id, status)
            VALUES (:ip, :rid, :unused)
        """), [{"ip": ip, "rid": room_id, "unused": status}
               for ip in insert_batch])

    def batch_update_active_status(self, active_ips: list[str], room_id: int) -> None:
        """将活跃 IP 标记为 ACTIVE"""
        if not active_ips:
            return
        self.session.execute(
            text("""
                UPDATE ip_addresses
                SET status = :active, updated_at = NOW()
                WHERE ip_address = :ip AND room_id = :rid
                  AND status != :banned
            """),
            [{"ip": ip, "rid": room_id,
              "active": int(IPStatus.ACTIVE),
              "banned": int(IPStatus.BANNED)}
             for ip in active_ips]
        )

    def batch_update_active_status_with_timestamp(self, active_ips: list[str], room_id: int) -> None:
        """将活跃 IP 标记为 ACTIVE 并更新 last_active_at（自动扫描陈旧度模型 v5）

        扫描观测到活跃 IP 时调用，同时刷新 last_active_at 供陈旧度清理任务判定。
        条件更新：只更新 last_active_at 超过 1 小时未刷新的行，减少索引写放大。
        """
        if not active_ips:
            return
        self.session.execute(
            text("""
                UPDATE ip_addresses
                SET status = :active, last_active_at = NOW(), updated_at = NOW()
                WHERE ip_address = :ip AND room_id = :rid
                  AND status != :banned
                  AND (last_active_at IS NULL
                       OR last_active_at < DATE_SUB(NOW(), INTERVAL 1 HOUR))
            """),
            [{"ip": ip, "rid": room_id,
              "active": int(IPStatus.ACTIVE),
              "banned": int(IPStatus.BANNED)}
             for ip in active_ips]
        )
        self.session.execute(
            text("""
                UPDATE ip_addresses
                SET status = :active, updated_at = NOW()
                WHERE ip_address = :ip AND room_id = :rid
                  AND status != :active
                  AND status != :banned
                  AND last_active_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            """),
            [{"ip": ip, "rid": room_id,
              "active": int(IPStatus.ACTIVE),
              "banned": int(IPStatus.BANNED)}
             for ip in active_ips]
        )

    def batch_update_inactive_status(self, inactive_ips: list[str], room_id: int) -> None:
        """将规划内但不活跃的 IP 标记为 INACTIVE（仅 ACTIVE→INACTIVE）"""
        if not inactive_ips:
            return
        self.session.execute(
            text("""
                UPDATE ip_addresses
                SET status = :inactive, updated_at = NOW()
                WHERE ip_address = :ip AND room_id = :rid
                  AND status = :active
            """),
            [{"ip": ip, "rid": room_id,
              "active": int(IPStatus.ACTIVE),
              "inactive": int(IPStatus.INACTIVE)}
             for ip in inactive_ips]
        )

    def find_unused_inactive_ips_by_rooms(
        self, room_ids: list[int], status_values: list[int],
    ) -> list[str]:
        """查询指定机房内指定状态的 IP 地址列表

        供扫描编排器 Phase 6b 筛选 ARP 未覆盖的待探测 IP。

        Args:
            room_ids: 机房ID列表
            status_values: IP 状态值列表（如 [IPStatus.UNUSED, IPStatus.INACTIVE]）

        Returns:
            list[str]: IP 地址字符串列表
        """
        if not room_ids:
            return []
        rows = self.session.execute(
            text("""
                SELECT ip_address FROM ip_addresses
                WHERE room_id IN :rids
                  AND status IN (:unused, :inactive)
            """).bindparams(bindparam("rids", expanding=True)),
            {
                "rids": list(room_ids),
                "unused": status_values[0] if len(status_values) > 0 else 3,
                "inactive": status_values[1] if len(status_values) > 1 else 1,
            }
        ).fetchall()
        return [r[0] for r in rows]

    def get_status_statistics_by_cidr(self, cidr: str) -> dict:
        """按 CIDR 范围做 SUM(CASE WHEN) 聚合统计。"""
        import ipaddress as _ipaddress
        from sqlalchemy import case
        from app.models.ip_model import ip_to_int

        net = _ipaddress.ip_network(cidr, strict=False)
        start_int = ip_to_int(str(net.network_address))
        end_int = ip_to_int(str(net.broadcast_address))

        row = self.session.query(
            func.count(IPManager.id).label("total"),
            func.sum(case((IPManager.status == 0, 1), else_=0)).label("active"),
            func.sum(case((IPManager.status == 1, 1), else_=0)).label("inactive"),
            func.sum(case((IPManager.status == 2, 1), else_=0)).label("blocked"),
            func.sum(case((IPManager.status == 3, 1), else_=0)).label("unused"),
        ).where(
            IPManager.ip_int.between(start_int, end_int),
        ).one()

        return {
            "total": int(row.total or 0),
            "active": int(row.active or 0),
            "inactive": int(row.inactive or 0),
            "blocked": int(row.blocked or 0),
            "unused": int(row.unused or 0),
        }

    def paginate_with_relations_by_cidr(self, cidr: str, room_id: int = None, page: int = 1, page_size: int = 20) -> dict:
        """按 CIDR 范围分页查询 IP 列表，含 ip_switch_info joinedload。"""
        import ipaddress as _ipaddress
        from app.models.ip_model import ip_to_int

        net = _ipaddress.ip_network(cidr, strict=False)
        start_int = ip_to_int(str(net.network_address))
        end_int = ip_to_int(str(net.broadcast_address))

        query = self._base_query().outerjoin(
            IPManager.ip_switch_info
        ).options(
            joinedload(IPManager.ip_switch_info),
        ).where(
            IPManager.ip_int.between(start_int, end_int)
        )
        if room_id is not None:
            query = query.filter(IPManager.room_id == room_id)

        total = query.count()
        total_pages = max(1, (total + page_size - 1) // page_size)
        offset = (page - 1) * page_size
        ensure_offset_within_limit(offset)
        items = query.order_by(IPManager.ip_address).offset(offset).limit(page_size).all()

        return {
            "data": items,
            "total": total,
            "total_pages": total_pages,
            "page": page,
            "page_size": page_size,
        }

    def batch_update_banned_status(self, banned_ips: list[str], room_id: int) -> None:
        """将封禁 IP 标记为 BANNED，并清理无效的 ip_switch_info 记录"""
        if not banned_ips:
            return
        self.session.execute(
            text("""
                UPDATE ip_addresses
                SET status = :banned, updated_at = NOW()
                WHERE ip_address = :ip AND room_id = :rid
            """),
            [{"ip": ip, "rid": room_id,
              "banned": int(IPStatus.BANNED)}
             for ip in banned_ips]
        )
        for ip in banned_ips:
            self.session.execute(
                text("""
                    DELETE FROM ip_switch_info
                    WHERE ip_address = :ip AND room_id = :rid
                      AND mac_address IN ('0000-0000-0000', '0000-0000-0001',
                                          '0000.0000.0000', '0000.0000.0001')
                """),
                {"ip": ip, "rid": room_id}
            )

    def sweep_stale_active_ips(self, grace_period_seconds: int, batch_limit: int = 5000) -> int:
        """将超过 grace_period 未观测到活跃的 IP 降级为 INACTIVE（自动扫描陈旧度模型 v5）

        全局生效（不限定房间），只降级 ACTIVE 状态的 IP，不动 BANNED/UNUSED。
        循环分批处理避免大表锁表；每批独立 commit 释放锁、缩短事务、尽早释放 binlog。

        事务语义：方法内自提交，调用方无需再 commit。

        Args:
            grace_period_seconds: 宽限期（秒），last_active_at 超过此值未刷新则降级
            batch_limit: 单批最大处理行数

        Returns:
            int: 受影响行数（所有批次累计）
        """
        total = 0
        while True:
            result = self.session.execute(
                text("""
                    UPDATE ip_addresses
                    SET status = :inactive, updated_at = NOW()
                    WHERE status = :active
                      AND last_active_at IS NOT NULL
                      AND last_active_at < DATE_SUB(NOW(), INTERVAL :grace SECOND)
                    LIMIT :limit
                """),
                {
                    "active": int(IPStatus.ACTIVE),
                    "inactive": int(IPStatus.INACTIVE),
                    "grace": grace_period_seconds,
                    "limit": batch_limit,
                },
            )
            affected = result.rowcount or 0
            self.session.commit()
            total += affected
            if affected < batch_limit:
                break
        return total


class IPSwitchInfoRepository(BaseRepository):
    """IPSwitchInfo 数据访问层（替代旧 IPInfoRepository）"""

    def __init__(self, session=None):
        super().__init__(IPSwitchInfo, session or db.session)

    def get_by_ip_room(self, ip: str, room_id: int) -> Optional[IPSwitchInfo]:
        """根据 IP + 机房ID 查询详细信息

        Args:
            ip: IP地址
            room_id: 机房ID

        Returns:
            Optional[IPSwitchInfo]: 记录对象
        """
        return self.find_one({"ip_address": ip, "room_id": room_id})

    def upsert_ip_info(
        self, ip_address: str, room_id: int, switch_id: int,
        port: str = None, mac_address: str = None,
    ) -> IPSwitchInfo:
        """UPSERT IP 详细信息

        Args:
            ip_address: IP地址
            room_id: 机房ID
            switch_id: 交换机ID
            port: 端口号
            mac_address: MAC地址

        Returns:
            IPSwitchInfo: 更新后的记录
        """
        stmt = mysql_insert(IPSwitchInfo).values(
            ip_address=ip_address,
            room_id=room_id,
            switch_id=switch_id,
            port=port,
            mac_address=mac_address,
        )
        stmt = stmt.on_duplicate_key_update(
            switch_id=stmt.inserted.switch_id,
            port=stmt.inserted.port,
            mac_address=stmt.inserted.mac_address,
            updated_at=func.now(),
        )
        self.session.execute(stmt)
        self.session.flush()

        return self.get_by_ip_room(ip_address, room_id)

    def batch_delete_by_ips_and_room(
        self, ip_list: List[str], room_id: int,
    ) -> int:
        """批量删除指定机房中的IP信息记录"""
        stmt = delete(IPSwitchInfo).where(
            IPSwitchInfo.ip_address.in_(ip_list), IPSwitchInfo.room_id == room_id,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_delete_by_ips_and_switch_room(
        self, ip_list: List[str], switch_id: int, room_id: int,
    ) -> int:
        """批量删除指定交换机和机房中的IP信息记录"""
        stmt = delete(IPSwitchInfo).where(
            IPSwitchInfo.ip_address.in_(ip_list),
            IPSwitchInfo.switch_id == switch_id,
            IPSwitchInfo.room_id == room_id,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_delete_by_ips_and_switch(
        self, ip_list: List[str], switch_id: int,
    ) -> int:
        """批量删除指定交换机中的IP信息记录"""
        stmt = delete(IPSwitchInfo).where(
            IPSwitchInfo.ip_address.in_(ip_list), IPSwitchInfo.switch_id == switch_id,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_delete_by_ips(self, ip_list: List[str]) -> int:
        """批量删除IP信息记录"""
        stmt = delete(IPSwitchInfo).where(IPSwitchInfo.ip_address.in_(ip_list))
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def find_by_ip_address(self, ip_address: str) -> List[IPSwitchInfo]:
        """根据IP地址查找信息记录"""
        return self.find_all({"ip_address": ip_address})

    def find_by_mac_address(self, mac_address: str) -> List[IPSwitchInfo]:
        """根据MAC地址查找IP信息"""
        return self.find_all({"mac_address": mac_address})

    def find_by_switch_id(self, switch_id: int) -> List[IPSwitchInfo]:
        """根据交换机ID查找IP信息"""
        return self.find_all({"switch_id": switch_id})

    def find_by_room_id(self, room_id: int) -> List[IPSwitchInfo]:
        """根据机房ID查找IP信息"""
        return self.find_all({"room_id": room_id})

    def _bulk_upsert(self, rows: List[dict], update_cols: List[str]) -> int:
        """通用 MySQL INSERT ... ON DUPLICATE KEY UPDATE

        Args:
            rows: 与 IPSwitchInfo 列名匹配的字典列表
            update_cols: 冲突时需要更新的列名列表

        Returns:
            int: 影响行数
        """
        if not rows:
            return 0
        stmt = mysql_insert(IPSwitchInfo).values(rows)
        update_map = {c: getattr(stmt.inserted, c) for c in update_cols}
        update_map["updated_at"] = func.now()
        stmt = stmt.on_duplicate_key_update(**update_map)
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def bulk_upsert_switch_port(self, rows: List[dict]) -> int:
        """批量upsert ip_switch_info，插入或更新switch_id/port"""
        return self._bulk_upsert(rows, ["switch_id", "port"])

    def bulk_upsert_switch_only(self, rows: List[dict]) -> int:
        """批量upsert ip_switch_info，仅更新switch_id"""
        return self._bulk_upsert(rows, ["switch_id"])

    def bulk_upsert_full(self, rows: List[dict]) -> int:
        """批量upsert ip_switch_info，更新mac/switch_id/port"""
        return self._bulk_upsert(rows, ["mac_address", "switch_id", "port"])

    def bulk_upsert_full_with_room(self, rows: List[dict]) -> int:
        """批量upsert ip_switch_info，更新mac/switch_id/port/room_id"""
        return self._bulk_upsert(rows, ["mac_address", "switch_id", "port", "room_id"])


    def find_first_by_mac(self, mac_address: str, room_ids) -> "tuple | None":
        """按 MAC 在机房集合内取 ``(ip_address, room_id)`` 首行（B-46 批 5）。

        返回**首行**（原实现 fetchone）：同一 MAC 可能多行（跨机房/NAT），
        取首行是先到先得语义，勿"顺手"改成聚合。
        """
        ids = list(room_ids)
        if not ids:
            return None
        return self.session.execute(
            text("SELECT ip_address, room_id FROM ip_switch_info "
                 "WHERE mac_address = :mac AND room_id IN :rids")
            .bindparams(bindparam("rids", expanding=True)),
            {"mac": mac_address, "rids": ids},
        ).fetchone()

    def find_by_macs(self, mac_addresses, room_ids) -> dict:
        """按 MAC 集合在机房集合内批量取 ``{mac: (ip_address, room_id)}``（WP-9/9.1）。

        消除 L2 降级循环的逐 MAC 反查 N+1：N 个 MAC 由 N 次 SELECT 降为 1 次。
        **首行语义与 :meth:`find_first_by_mac` 一致**：同一 MAC 多行（跨机房/NAT）
        先到先得取第一行；结果集中不存在的 MAC 即"无定位数据"（与原 `fetchone`
        返回 None 同义）。
        """
        macs = [m for m in mac_addresses if m]
        ids = list(room_ids)
        if not macs or not ids:
            return {}
        rows = self.session.execute(
            text("SELECT mac_address, ip_address, room_id FROM ip_switch_info "
                 "WHERE mac_address IN :macs AND room_id IN :rids")
            .bindparams(bindparam("macs", expanding=True),
                        bindparam("rids", expanding=True)),
            {"macs": macs, "rids": ids},
        ).fetchall()
        result: dict = {}
        for mac, ip, rid in rows:
            if mac not in result:  # 先到先得，同 find_first_by_mac 的"首行"语义
                result[mac] = (ip, rid)
        return result

    def list_missing_location_ips(
        self, room_id: int, start_int: int, end_int: int,
    ) -> List[str]:
        """网段内"ip_addresses 有活跃/封禁记录但 ip_switch_info 无定位"的 IP。

        B-46 批 5（ip_route_info 的补全阶段）：``isi.ip_address IS NULL`` 是
        "缺定位"判据 —— 状态取 ACTIVE/BANNED（UNUSED 不需要定位）。
        """
        from app.core.enums import IPStatus

        rows = self.session.execute(
            text("""
            SELECT ia.ip_address
            FROM ip_addresses ia
            LEFT JOIN ip_switch_info isi
              ON isi.ip_address = ia.ip_address AND isi.room_id = ia.room_id
            WHERE ia.room_id = :rid
              AND ia.ip_int BETWEEN :s AND :e
              AND ia.status IN (:active, :banned)
              AND isi.ip_address IS NULL
        """),
            {"rid": room_id, "s": start_int, "e": end_int,
             "active": int(IPStatus.ACTIVE), "banned": int(IPStatus.BANNED)},
        ).fetchall()
        return [r[0] for r in rows]

    def insert_ignore_ips(self, rows) -> None:
        """批量 ``INSERT IGNORE`` 补定位行（只写 switch_id，不写 port）。

        [WARN] 保留 ``INSERT IGNORE``：并发/重跑时同 (ip,room) 可能已存在，
        IGNORE 让补全幂等（原实现即如此）。
        """
        self.session.execute(
            text("""
                INSERT IGNORE INTO ip_switch_info
                    (ip_address, mac_address, switch_id, port, room_id, updated_at)
                VALUES (
                    :ip, NULL, :sid, NULL,
                    :rid, NOW()
                )
            """),
            rows,
        )

    def delete_by_switch(self, switch_id: int) -> int:
        """清空该交换机的 IP-交换机关联行（B-44 收敛：设备彻底删除的清理面）。"""
        return (
            self.session.query(IPSwitchInfo)
            .filter_by(switch_id=switch_id)
            .delete()
        )


class IPNetworkRepository(BaseRepository):
    """IPNetwork 数据访问层

    提供路由表查询、黑洞路由操作等方法。
    """

    def __init__(self, session=None):
        super().__init__(IPNetwork, session or db.session)

    def list_by_room_ids(self, room_ids) -> List[IPNetwork]:
        """取机房集合的全部网段（B-44 部署计划批：IP 容量统计的入口）。"""
        ids = tuple(room_ids)
        if not ids:
            return []
        return (
            self.session.query(IPNetwork)
            .filter(IPNetwork.room_id.in_(ids))
            .all()
        )

    def get_by_switch(self, switch_id: int, room_id: int) -> List[IPNetwork]:
        """查询指定交换机的所有路由

        Args:
            switch_id: 交换机ID
            room_id: 机房ID

        Returns:
            List[IPNetwork]: 路由记录列表
        """
        return self.find_all({"switch_id": switch_id, "room_id": room_id})


    def list_host_route_ids(self, switch_id: int, room_id: int) -> List[tuple]:
        """该交换机在该机房的全部 /32 路由 (id, network)。"""
        return self.session.execute(
            text(
                "SELECT id, network FROM ip_networks "
                "WHERE switch_id=:sid AND room_id=:rid AND network LIKE '%/32'"
            ),
            {"sid": switch_id, "rid": room_id},
        ).fetchall()

    def delete_networks_by_ids(self, ids) -> None:
        """按主键逐条删除 ip_networks（executemany）。

        [WARN] 保持**逐条**参数绑定（docstring：避免 tuple 参数绑定问题）——
        不要改成拼接 OR 或 IN 列表。
        """
        self.session.execute(
            text("DELETE FROM ip_networks WHERE id = :id"),
            [{"id": i} for i in ids],
        )

    def list_existing_network_keys(self, switch_id: int, room_id: int) -> List[tuple]:
        """该交换机在该机房的既有网段键 (network, switch_id, port)。"""
        return self.session.execute(
            text(
                "SELECT network, switch_id, port "
                "FROM ip_networks WHERE switch_id=:sid AND room_id=:rid"
            ),
            {"sid": switch_id, "rid": room_id},
        ).fetchall()

    def upsert_networks(self, net_rows) -> None:
        """批量 upsert ip_networks（仅网段归属列；flags/nexthop/route_type 在 switch_routes）。

        ``AS _new ... ON DUPLICATE KEY UPDATE gateway/updated_at``：MySQL 8 别名
        语法 —— 只更新 gateway 与 updated_at（network/switch_id/port/room_id 是
        冲突键，不更新，原实现即如此）。
        """
        self.session.execute(
            text("""
            INSERT INTO ip_networks
                (network, switch_id, port, gateway, room_id, updated_at)
            VALUES
                (:ip_network, :switch_id, :port, :gateway, :room_id, NOW())
            AS _new
            ON DUPLICATE KEY UPDATE
                gateway = _new.gateway,
                updated_at = NOW()
        """),
            net_rows,
        )

    def nullify_route_links(self, params) -> None:
        """删除网段前，先把引用它的 switch_routes.network_id 置 NULL。

        [WARN] docstring 语义（原实现）：**必须先置空再删**，否则悬空引用会让前端
        nexthop/route_type 丢失；NexthopResolver 会在 Phase 4 重新回填。
        executemany 逐条绑定（避免动态 OR 拼接导致 SQL 长度膨胀 / 参数上限溢出）。
        """
        self.session.execute(
            text("UPDATE switch_routes sr "
                 "INNER JOIN ip_networks ipn ON sr.network_id = ipn.id "
                 "SET sr.network_id = NULL "
                 "WHERE ipn.network=:net AND ipn.switch_id=:sid "
                 "AND ipn.port=:port AND ipn.room_id=:rid"),
            params,
        )

    def delete_network_keys(self, params) -> None:
        """按 (network, switch_id, port, room_id) 四元组逐条删除 ip_networks。"""
        self.session.execute(
            text("DELETE FROM ip_networks "
                 "WHERE network=:net AND switch_id=:sid "
                 "AND port=:port AND room_id=:rid"),
            params,
        )

    def list_switch_route_triples(self, switch_id: int, room_id: int) -> List[tuple]:
        """该交换机在该机房的既有路由三元组 (destination, nexthop, route_type)。"""
        return self.session.execute(
            text("""
            SELECT destination, nexthop, route_type FROM switch_routes
            WHERE switch_id = :sid AND room_id = :rid
        """),
            {"sid": switch_id, "rid": room_id},
        ).fetchall()

    def upsert_switch_routes(self, rows) -> None:
        """批量 upsert switch_routes（含整数化列 CR-ROUTE-INT）。

        ``network_id = NULL``：路由详情变更后由 NexthopResolver 重新回填关联
        （原实现即如此，勿"顺手"保留旧关联）。
        """
        self.session.execute(
            text("""
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
            """),
            rows,
        )

    def delete_switch_route_keys(self, params) -> None:
        """按 (switch_id, room_id, destination, nexthop, route_type) 逐条删除路由。"""
        self.session.execute(
            text("DELETE FROM switch_routes "
                 "WHERE switch_id=:sid AND room_id=:rid "
                 "AND destination=:dest AND nexthop=:nh AND route_type=:rt"),
            params,
        )

    def clear_dangling_network_ids(self, room_ids) -> int:
        """修复悬空 network_id（指向已删 ip_networks 的行）⇒ 置 NULL。

        [WARN] 必须**先修悬空**再回填：悬空行的 network_id 非 NULL 会躲过
        ``network_id IS NULL`` 的回填条件，形成**永久悬空引用**（原注释即如此）。
        Returns: 修复行数
        """
        result = self.session.execute(
            text("""
            UPDATE switch_routes sr
            LEFT JOIN ip_networks ipn ON sr.network_id = ipn.id
            SET sr.network_id = NULL, sr.updated_at = NOW()
            WHERE sr.room_id IN :room_ids
              AND sr.network_id IS NOT NULL
              AND ipn.id IS NULL
        """).bindparams(bindparam("room_ids", expanding=True)),
            {"room_ids": list(room_ids)},
        )
        return result.rowcount or 0

    _BACKFILL_SQL_INT = """
        UPDATE switch_routes sr
        INNER JOIN ip_networks ipn
          ON ipn.network_int = sr.destination_int
         AND ipn.prefix = sr.destination_prefix
         AND ipn.room_id = sr.room_id
         AND ipn.switch_id = sr.switch_id
        SET sr.network_id = ipn.id, sr.updated_at = NOW()
        WHERE {scope} AND sr.network_id IS NULL
          AND sr.destination_int IS NOT NULL
    """
    _BACKFILL_SQL_STR = """
        UPDATE switch_routes sr
        INNER JOIN ip_networks ipn
          ON ipn.network = sr.destination
         AND ipn.room_id = sr.room_id
         AND ipn.switch_id = sr.switch_id
        SET sr.network_id = ipn.id, sr.updated_at = NOW()
        WHERE {scope} AND sr.network_id IS NULL
    """

    def backfill_network_ids_for_room(self, room_id: int) -> int:
        """单机房回填 network_id：① 整数化列精确匹配 → ② destination 字符串回退。

        两步是**效率 + 兼容**的双设计（原实现即如此）：整数列命中绝大多数，
        字符串回退兜住整数列缺失的历史行。Returns: 两步 rowcount 之和。
        """
        result = self.session.execute(
            text(self._BACKFILL_SQL_INT.format(scope="sr.room_id = :rid")),
            {"rid": room_id},
        )
        result2 = self.session.execute(
            text(self._BACKFILL_SQL_STR.format(scope="sr.room_id = :rid")),
            {"rid": room_id},
        )
        return (result.rowcount or 0) + (result2.rowcount or 0)

    def backfill_network_ids_for_rooms(self, room_ids) -> int:
        """多机房回填 network_id（同上两步；``IN :room_ids`` expanding 绑定）。"""
        result = self.session.execute(
            text(self._BACKFILL_SQL_INT.format(scope="sr.room_id IN :room_ids"))
            .bindparams(bindparam("room_ids", expanding=True)),
            {"room_ids": list(room_ids)},
        )
        result2 = self.session.execute(
            text(self._BACKFILL_SQL_STR.format(scope="sr.room_id IN :room_ids"))
            .bindparams(bindparam("room_ids", expanding=True)),
            {"room_ids": list(room_ids)},
        )
        return (result.rowcount or 0) + (result2.rowcount or 0)

    def list_gateway_rows_by_switch_ids(self, switch_ids) -> List[tuple]:
        """取集合内交换机的 (switch_id, gateway, port)（gateway 非空）。

        B-46 批 4（拓扑建图）：外部占位节点不参与采集，网关只能从 ip_networks
        历史数据回填 —— "gateway 非空"由 SQL 端过滤（原实现即如此）。
        """
        ids = list(switch_ids)
        if not ids:
            return []
        return (
            self.session.query(
                IPNetwork.switch_id, IPNetwork.gateway, IPNetwork.port,
            )
            .filter(
                IPNetwork.switch_id.in_(ids),
                IPNetwork.gateway.isnot(None),
            )
            .all()
        )

    def list_subnet_networks_for_switch(self, switch_id: int, room_ids) -> List[str]:
        """该交换机在机房集合内的 **SUBNET(终端子网)** 路由网段（排除 /32）。

        与 ``list_non_host_networks`` 的区别：本方法**要求**存在 SUBNET 类型的
        switch_routes 关联（INNER JOIN + route_type 过滤）——"这条网段确实被
        识别为终端子网"；后者只按非 /32 过滤。
        """
        from app.core.enums import RouteNotes

        ids = list(room_ids)
        if not ids:
            return []
        rows = self.session.execute(
            text("""SELECT ipn.network FROM ip_networks ipn
            INNER JOIN switch_routes sr
              ON sr.network_id = ipn.id
              AND sr.switch_id = ipn.switch_id
            WHERE ipn.switch_id = :sid
              AND ipn.room_id IN :rids
              AND sr.route_type = :rt
              AND ipn.network NOT LIKE '%/32'""")
            .bindparams(bindparam("rids", expanding=True)),
            {"sid": switch_id, "rids": ids, "rt": int(RouteNotes.SUBNET)},
        ).fetchall()
        return [r[0] for r in rows]

    def list_non_host_networks(self, switch_id: int, room_ids) -> List[str]:
        """该交换机在机房集合内的**非 /32** 网段（不要求 SUBNET 关联）。

        兜底语义由调用方决定（查不到时用管理 IP 推算 /24，见 scan_degrader）。
        """
        ids = list(room_ids)
        if not ids:
            return []
        rows = self.session.execute(
            text("SELECT network FROM ip_networks WHERE switch_id=:sid "
                 "AND room_id IN :rids AND network NOT LIKE '%/32'")
            .bindparams(bindparam("rids", expanding=True)),
            {"sid": switch_id, "rids": ids},
        ).fetchall()
        return [r[0] for r in rows]

    def list_subnet_networks_by_rooms(self, room_ids) -> List[tuple]:
        """机房集合内全部 SUBNET 网段 ``(network, switch_id, room_id)``（排除 /32）。

        注意：不返回 port —— 路由表的 port 是 Vlanif，不是物理端口（原注释即如此）。
        """
        from app.core.enums import RouteNotes

        ids = list(room_ids)
        if not ids:
            return []
        return self.session.execute(
            text("""
                SELECT ipn.network, ipn.switch_id, ipn.room_id
                FROM ip_networks ipn
                INNER JOIN switch_routes sr
                  ON sr.network_id = ipn.id AND sr.switch_id = ipn.switch_id
                WHERE ipn.room_id IN :rids
                  AND sr.route_type = :subnet
                  AND ipn.network NOT LIKE '%/32'
            """).bindparams(bindparam("rids", expanding=True)),
            {"rids": ids, "subnet": int(RouteNotes.SUBNET)},
        ).fetchall()

    def list_probeable_networks(self, room_id: int) -> List[tuple]:
        """该机房**可探测**网段（排除黑洞/下一跳，含无路由关联的行；排除 /32）。

        [WARN] ``sr.route_type IS NULL`` 必须放行（LEFT JOIN 无关联的网段仍可探测）——
        写成 INNER JOIN 会静默丢掉这些网段（原实现即 LEFT JOIN + OR IS NULL）。
        """
        from app.core.enums import RouteNotes

        return self.session.execute(
            text("""
            SELECT DISTINCT ipn.network FROM ip_networks ipn
            LEFT JOIN switch_routes sr
              ON sr.network_id = ipn.id AND sr.switch_id = ipn.switch_id
            WHERE ipn.room_id = :rid
              AND (sr.route_type NOT IN (:bh, :nh) OR sr.route_type IS NULL)
              AND ipn.network NOT LIKE '%/32'
        """),
            {
                "rid": room_id,
                "bh": int(RouteNotes.BLACKHOLE),
                "nh": int(RouteNotes.NEXTHOP),
            },
        ).fetchall()

    def find_longest_prefix_match_route(
        self, room_id: int, ip_int: int,
    ) -> Optional["SwitchRoute"]:
        """取命中该 IP 的**最长前缀**路由（排除黑洞；B-44 扫尾批：封禁定位）。

        [WARN] 保留**原生 SQL**：``destination_int + POW(2, 32 - prefix) - 1``
        的范围算术引用了表列，ORM filter 表达不了（原注释即如此），勿"顺手"
        改写成 Python 侧过滤 —— 那会丢掉 ``ORDER BY prefix DESC LIMIT 1``
        的数据库端裁剪。
        """
        row = self.session.execute(
            text(
                "SELECT id FROM switch_routes "
                "WHERE room_id = :room_id "
                "  AND route_type != :blackhole_type "
                "  AND destination_int <= :ip_int "
                "  AND :ip_int <= destination_int + POW(2, 32 - destination_prefix) - 1 "
                "ORDER BY destination_prefix DESC LIMIT 1"
            ),
            {
                "ip_int": ip_int, "room_id": room_id,
                "blackhole_type": int(RouteNotes.BLACKHOLE),
            },
        ).first()
        if row is None:
            return None
        return self.session.get(SwitchRoute, row[0])

    def get_blackhole_for_ip(
        self, ip_address: str, switch_id: int,
    ) -> Optional["SwitchRoute"]:
        """查询指定 IP 在指定交换机上是否存在黑洞路由

        route_type 已迁移至 switch_routes 表，从 switch_routes 查询。

        Args:
            ip_address: IP地址
            switch_id: 交换机ID

        Returns:
            Optional[SwitchRoute]: 黑洞路由记录
        """
        return self.session.query(SwitchRoute).filter(
            SwitchRoute.destination == f"{ip_address}/32",
            SwitchRoute.switch_id == switch_id,
            SwitchRoute.route_type == int(RouteNotes.BLACKHOLE),
        ).first()

    def delete_blackhole_for_ip(self, ip_address: str, switch_id: int) -> int:
        """删除指定 IP 在指定交换机上的黑洞路由

        route_type 已迁移至 switch_routes 表，从 switch_routes 删除。

        Args:
            ip_address: IP地址
            switch_id: 交换机ID

        Returns:
            int: 删除行数
        """
        stmt = delete(SwitchRoute).where(
            SwitchRoute.destination == f"{ip_address}/32",
            SwitchRoute.switch_id == switch_id,
            SwitchRoute.route_type == int(RouteNotes.BLACKHOLE),
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def get_by_network_room(self, ip_network: str, room_id: int) -> List[IPNetwork]:
        """按网段+机房查询路由记录

        Args:
            ip_network: 网段CIDR
            room_id: 机房ID

        Returns:
            List[IPNetwork]: 路由记录列表
        """
        return self.find_all({"network": ip_network, "room_id": room_id})

    def find_by_switch_and_room(
        self, switch_id: int, room_id: int,
    ) -> List[IPNetwork]:
        """根据交换机ID和机房ID查找网络段"""
        return self.find_all({"switch_id": switch_id, "room_id": room_id})

    def find_exact_match(
        self, ip_network: str, switch_id: int, room_id: int,
    ) -> Optional[IPNetwork]:
        """精确匹配查找网络段记录"""
        return self.find_one({
            "network": ip_network, "switch_id": switch_id, "room_id": room_id,
        })

    def count_by_network_and_room(self, ip_network: str, room_id: int) -> int:
        """统计指定网段在指定机房的路由记录数"""
        return self.session.query(IPNetwork).filter(
            IPNetwork.network == ip_network, IPNetwork.room_id == room_id,
        ).count()

    def count_by_network(self, ip_network: str) -> int:
        """统计指定网段的路由记录数"""
        return self.session.query(IPNetwork).filter(
            IPNetwork.network == ip_network,
        ).count()

    def find_by_switch_and_route_type(
        self, switch_id: int, route_type: int,
    ) -> List["SwitchRoute"]:
        """根据交换机ID和route_type值查找路由条目

        route_type 已迁移至 switch_routes 表，从 switch_routes 查询。
        """
        return self.session.query(SwitchRoute).filter(
            SwitchRoute.switch_id == switch_id,
            SwitchRoute.route_type == route_type,
        ).all()

    find_by_switch_and_notes = find_by_switch_and_route_type

    def delete_by_switch_and_networks(
        self, switch_id: int, network_names: List[str],
    ) -> int:
        """删除指定交换机上指定网段名的路由记录"""
        stmt = delete(IPNetwork).where(
            IPNetwork.switch_id == switch_id,
            IPNetwork.network.in_(network_names),
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def delete_by_switch_and_room(self, switch_id: int, room_id: int) -> int:
        """删除指定交换机在指定机房的路由记录"""
        stmt = delete(IPNetwork).where(
            IPNetwork.switch_id == switch_id, IPNetwork.room_id == room_id,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def delete_by_switch(self, switch_id: int) -> int:
        """删除指定交换机的所有路由记录"""
        stmt = delete(IPNetwork).where(IPNetwork.switch_id == switch_id)
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def find_by_switch_id(self, switch_id: int) -> List[IPNetwork]:
        """根据交换机ID查找网络段"""
        return self.find_all({"switch_id": switch_id})

    def find_by_customer_id(self, customer_id: int) -> List[IPNetwork]:
        """根据客户ID查找网络段"""
        return self.find_all({"customer_id": customer_id})

    def clear_customer(self, customer_id: int) -> int:
        """批量解绑客户名下所有网段（customer_id 置 NULL）。

        Returns:
            int: 受影响行数
        """
        result = self.session.query(IPNetwork).filter(
            IPNetwork.customer_id == customer_id,
        ).update({IPNetwork.customer_id: None}, synchronize_session=False)
        return result

    def find_by_room_id(self, room_id: int) -> List[IPNetwork]:
        """根据机房ID查找网络段"""
        return self.find_all({"room_id": room_id})

    def bulk_upsert_network(self, network_data_list: List[dict]) -> int:
        """批量upsert ip_networks"""
        if not network_data_list:
            return 0
        stmt = mysql_insert(IPNetwork).values(network_data_list)
        stmt = stmt.on_duplicate_key_update(
            port=stmt.inserted.port,
            flags=stmt.inserted.flags,
            gateway=stmt.inserted.gateway,
            route_type=stmt.inserted.route_type,
            updated_at=func.now(),
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def search_networks(
        self, keyword: str = None, switch_id: int = None,
        customer_id: int = None, room_id: int = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        """搜索网络段"""
        query = self.session.query(IPNetwork)
        if keyword:
            query = query.filter(
                IPNetwork.network.contains(keyword)
            )
        if switch_id is not None:
            query = query.filter(IPNetwork.switch_id == switch_id)
        if customer_id is not None:
            query = query.filter(IPNetwork.customer_id == customer_id)
        if room_id is not None:
            query = query.filter(IPNetwork.room_id == room_id)
        items, total, total_pages = self._paginate(query, page, page_size)
        return {
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def find_network_ids_by_route_type(self, route_type: int) -> list[int]:
        """按 route_type 查询所有匹配的 network_id 列表。"""
        rows = self.session.query(SwitchRoute.network_id).filter(
            SwitchRoute.route_type == route_type,
        ).all()
        return [r[0] for r in rows]

    def find_switch_routes_by_network_ids(self, network_ids: list[int]) -> dict:
        """按 network_id 列表批量查询 SwitchRoute，返回 {network_id: SwitchRoute} 映射。"""
        if not network_ids:
            return {}
        rows = self.session.query(SwitchRoute).filter(
            SwitchRoute.network_id.in_(network_ids),
        ).all()
        return {sr.network_id: sr for sr in rows}

    def find_switch_route(self, switch_id: int, destination: str, room_id: int) -> Optional["SwitchRoute"]:
        """按 switch_id + destination + room_id 精确匹配查单条路由。"""
        return self.session.query(SwitchRoute).filter(
            SwitchRoute.switch_id == switch_id,
            SwitchRoute.destination == destination,
            SwitchRoute.room_id == room_id,
        ).first()

    def find_switch_routes_by_switch_destinations(
        self, switch_ids: set[int], destinations: set[str],
    ) -> list["SwitchRoute"]:
        """按 switch_id + destination 批量查询路由条目。"""
        if not switch_ids or not destinations:
            return []
        return self.session.query(SwitchRoute).filter(
            SwitchRoute.switch_id.in_(switch_ids),
            SwitchRoute.destination.in_(destinations),
        ).all()


    def delete_routes_by_switch(self, switch_id: int) -> int:
        """清空该交换机的全部路由行（B-44 收敛：设备彻底删除的清理面）。"""
        return (
            self.session.query(SwitchRoute)
            .filter_by(switch_id=switch_id)
            .delete()
        )


class IPBanRecordRepository(BaseRepository):
    """IPBanRecord 数据访问层

    提供封禁记录的查询、活跃封禁检测等方法。
    """

    def delete_by_switch(self, switch_id: int) -> int:
        """清空该交换机的封禁记录行（B-44 收敛：设备彻底删除的清理面）。"""
        from app.models.ip_model import IPBanRecord

        return (
            self.session.query(IPBanRecord)
            .filter_by(switch_id=switch_id)
            .delete()
        )

    def __init__(self, session=None):
        from app.models.ip_model import IPBanRecord
        super().__init__(IPBanRecord, session or db.session)

    def find_active_ban(self, ip_address: str, room_id: int):
        """查找指定 IP + 机房的活跃封禁记录

        Args:
            ip_address: IP 地址
            room_id: 机房 ID

        Returns:
            IPBanRecord 或 None
        """
        from app.models.ip_model import IPBanRecord
        return self.session.query(IPBanRecord).filter(
            IPBanRecord.ip_address == ip_address,
            IPBanRecord.room_id == room_id,
            IPBanRecord.is_active == True,
        ).first()

    def exists_active_ban(self, ip_address: str, room_id: int) -> bool:
        """检查指定 IP + 机房是否存在活跃封禁

        Args:
            ip_address: IP 地址
            room_id: 机房 ID

        Returns:
            bool: 是否存在活跃封禁
        """
        from app.models.ip_model import IPBanRecord
        return self.session.query(
            self.session.query(IPBanRecord).filter(
                IPBanRecord.ip_address == ip_address,
                IPBanRecord.room_id == room_id,
                IPBanRecord.is_active == True,
            ).exists()
        ).scalar()

    def find_all_active(self):
        """查找所有活跃封禁记录（用于一致性检查）

        Returns:
            List[IPBanRecord]
        """
        from app.models.ip_model import IPBanRecord
        return self.session.query(IPBanRecord).filter(
            IPBanRecord.is_active == True,
        ).all()
