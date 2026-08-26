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

from sqlalchemy import update, delete, text, func, bindparam
from sqlalchemy.orm import joinedload
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.persistence.base import BaseRepository
from app.models.ip_model import IPManager
from app.models.switch_route import IPNetwork
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

        Args:
            ip_address: IP地址
            room_id: 机房ID
            status: IP状态
            customer_id: 客户ID（仅首次写入）
        """
        stmt = mysql_insert(IPManager).values(
            ip_address=ip_address,
            room_id=room_id,
            status=status,
            customer_id=customer_id,
        )
        stmt = stmt.on_duplicate_key_update(
            status=text("CASE WHEN ip_addresses.status = 2 THEN 2 ELSE VALUES(status) END"),
            updated_at=func.now(),
        )
        self.session.execute(stmt)
        self.session.flush()

    def update_status(self, ip: str, room_id: int, status: IPStatus) -> None:
        """更新 IP 状态及状态更新时间

        Args:
            ip: IP地址
            room_id: 机房ID
            status: 新状态
        """
        now = datetime.now()
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
            status=status, updated_at=datetime.now(),
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
        items = query.offset((page - 1) * page_size).limit(page_size).all()
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
            for r in self.session.query(Room).filter(Room.id.in_(room_ids), Room.deleted_at.is_(None)).all():
                room_map[r.id] = r.name

        customer_map = {}
        if customer_ids:
            for c in self.session.query(Customer).filter(Customer.id.in_(customer_ids), Customer.deleted_at.is_(None)).all():
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

    def delete_ip_switch_info_cross_room(self, ip: str, room_id: int) -> None:
        """清理跨房间残留 ip_switch_info"""
        self.session.execute(text(
            "DELETE FROM ip_switch_info WHERE ip_address = :ip AND room_id != :rid"
        ), {"ip": ip, "rid": room_id})

    def delete_ip_addresses_cross_room(self, ip: str, room_id: int) -> None:
        """清理跨房间残留 ip_addresses"""
        self.session.execute(text(
            "DELETE FROM ip_addresses WHERE ip_address = :ip AND room_id != :rid"
        ), {"ip": ip, "rid": room_id})

    def upsert_ip_switch_info_with_port(self, ip: str, mac: str,
                                         switch_id: int, port: str,
                                         room_id: int) -> None:
        """UPSERT ip_switch_info（终端IP：有端口定位）"""
        self.session.execute(text("""
            INSERT INTO ip_switch_info
                (ip_address, mac_address, switch_id, port, port_id, room_id, updated_at)
            VALUES (
                :ip, :mac, :sid, :port,
                (SELECT id FROM network_ports
                 WHERE device_id = :sid AND port_name = :port LIMIT 1),
                :rid, NOW()
            )
            AS _new
            ON DUPLICATE KEY UPDATE
                mac_address = _new.mac_address,
                switch_id   = _new.switch_id,
                port        = _new.port,
                port_id     = _new.port_id,
                updated_at  = NOW()
        """), {"ip": ip, "mac": mac, "sid": switch_id,
               "port": port, "rid": room_id})

    def upsert_ip_switch_info_no_port(self, ip: str, mac: str,
                                       switch_id: int, room_id: int) -> None:
        """UPSERT ip_switch_info（管理/网关IP：无端口）"""
        self.session.execute(text("""
            INSERT INTO ip_switch_info
                (ip_address, mac_address, switch_id, port, room_id, updated_at)
            VALUES (:ip, :mac, :sid, NULL, :rid, NOW())
            AS _new
            ON DUPLICATE KEY UPDATE
                mac_address = _new.mac_address,
                switch_id   = _new.switch_id,
                port        = NULL,
                port_id     = NULL,
                updated_at  = NOW()
        """), {"ip": ip, "mac": mac, "sid": switch_id, "rid": room_id})

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

    def find_existing_ips_in_other_rooms(self, batch: list[str], room_id: int) -> set[str]:
        """查找已在其他机房存在的 IP

        Args:
            batch: IP 列表
            room_id: 当前机房ID

        Returns:
            set[str]: 已在其他机房存在的 IP 集合
        """
        rows = self.session.execute(
            text(
                "SELECT ip_address FROM ip_addresses "
                "WHERE ip_address IN :ips AND room_id != :rid"
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
        if insert_batch:
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
        items = query.order_by(IPManager.ip_address).offset((page - 1) * page_size).limit(page_size).all()

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


class IPNetworkRepository(BaseRepository):
    """IPNetwork 数据访问层

    提供路由表查询、黑洞路由操作等方法。
    """

    def __init__(self, session=None):
        super().__init__(IPNetwork, session or db.session)

    def get_by_switch(self, switch_id: int, room_id: int) -> List[IPNetwork]:
        """查询指定交换机的所有路由

        Args:
            switch_id: 交换机ID
            room_id: 机房ID

        Returns:
            List[IPNetwork]: 路由记录列表
        """
        return self.find_all({"switch_id": switch_id, "room_id": room_id})

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
        from app.models.switch_route import SwitchRoute
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
        from app.models.switch_route import SwitchRoute
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
        from app.models.switch_route import SwitchRoute
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
        from app.models.switch_route import SwitchRoute
        rows = self.session.query(SwitchRoute.network_id).filter(
            SwitchRoute.route_type == route_type,
        ).all()
        return [r[0] for r in rows]

    def find_switch_routes_by_network_ids(self, network_ids: list[int]) -> dict:
        """按 network_id 列表批量查询 SwitchRoute，返回 {network_id: SwitchRoute} 映射。"""
        from app.models.switch_route import SwitchRoute
        if not network_ids:
            return {}
        rows = self.session.query(SwitchRoute).filter(
            SwitchRoute.network_id.in_(network_ids),
        ).all()
        return {sr.network_id: sr for sr in rows}

    def find_switch_route(self, switch_id: int, destination: str, room_id: int) -> Optional["SwitchRoute"]:
        """按 switch_id + destination + room_id 精确匹配查单条路由。"""
        from app.models.switch_route import SwitchRoute
        return self.session.query(SwitchRoute).filter(
            SwitchRoute.switch_id == switch_id,
            SwitchRoute.destination == destination,
            SwitchRoute.room_id == room_id,
        ).first()

    def find_switch_routes_by_switch_destinations(
        self, switch_ids: set[int], destinations: set[str],
    ) -> list["SwitchRoute"]:
        """按 switch_id + destination 批量查询路由条目。"""
        from app.models.switch_route import SwitchRoute
        if not switch_ids or not destinations:
            return []
        return self.session.query(SwitchRoute).filter(
            SwitchRoute.switch_id.in_(switch_ids),
            SwitchRoute.destination.in_(destinations),
        ).all()


class IPBanRecordRepository(BaseRepository):
    """IPBanRecord 数据访问层

    提供封禁记录的查询、活跃封禁检测等方法。
    """

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
