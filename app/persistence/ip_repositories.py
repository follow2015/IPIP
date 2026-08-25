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

    def __init__(self, session=None):
        super().__init__(IPManager, session or db.session)

    def get_by_ip_room(self, ip: str, room_id: int) -> Optional[IPManager]:
        return self.find_one({"ip_address": ip, "room_id": room_id})

    def get_by_ips_room(self, ip_list: List[str], room_id: int) -> Dict[str, IPManager]:
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
        filters = {"status": int(status)}
        if room_id is not None:
            filters["room_id"] = room_id
        return self.find_all(filters)

    def bulk_update_customer_where_null(
        self, room_id: int, network_cidr: str, customer_id: Optional[int],
    ) -> int:
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
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return items, total, total_pages

    def bulk_upsert_preserve_customer(self, rows: List[dict]) -> int:
        return self._bulk_upsert(rows, ["room_id"])

    def bulk_upsert_with_customer(self, rows: List[dict]) -> int:
        return self._bulk_upsert(rows, ["room_id", "customer_id", "status"])

    def bulk_upsert_room_only(self, rows: List[dict]) -> int:
        return self._bulk_upsert(rows, ["room_id"])

    def bulk_upsert_update_only(self, rows: List[dict]) -> int:
        return self._bulk_upsert(rows, [])

    def bulk_upsert_customer_with_room(
        self, updates: List[tuple],
    ) -> int:
        rows = [
            {"ip_address": ip, "customer_id": cid, "room_id": rid, "status": IPStatus.UNUSED}
            for ip, cid, rid in updates
        ]
        return self._bulk_upsert(rows, ["customer_id"])

    def batch_delete_by_ips_and_room(self, ip_list: List[str], room_id: int) -> int:
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
        stmt = delete(IPManager).where(
            IPManager.ip_address.in_(ip_list),
            IPManager.room_id == room_id,
            IPManager.customer_id == None,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_delete_by_ips(self, ip_list: List[str]) -> int:
        stmt = delete(IPManager).where(IPManager.ip_address.in_(ip_list))
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def find_by_ip_address(
        self, ip_address: str, room_id: Optional[int] = None,
    ) -> Optional[IPManager]:
        query = self.session.query(IPManager).filter(
            IPManager.ip_address == ip_address,
        )
        if room_id is not None:
            query = query.filter(IPManager.room_id == room_id)
        return query.first()

    def find_by_customer_id(
        self, customer_id: int, status: Optional[int] = None,
    ) -> List[IPManager]:
        query = self.session.query(IPManager).filter(
            IPManager.customer_id == customer_id,
        )
        if status is not None:
            query = query.filter(IPManager.status == status)
        return query.all()

    def clear_customer(self, customer_id: int) -> int:
        result = self.session.query(IPManager).filter(
            IPManager.customer_id == customer_id,
        ).update({IPManager.customer_id: None}, synchronize_session=False)
        return result

    def find_by_room_id(
        self, room_id: int, status: Optional[int] = None,
    ) -> List[IPManager]:
        query = self.session.query(IPManager).filter(
            IPManager.room_id == room_id,
        )
        if status is not None:
            query = query.filter(IPManager.status == status)
        return query.all()

    def get_status_statistics(
        self, room_id: Optional[int] = None, search: Optional[str] = None,
    ) -> dict:
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
        rows = self.session.execute(
            text("SELECT id FROM devices WHERE deleted_at IS NULL")
        ).fetchall()
        return {r[0] for r in rows}

    def load_device_room_map(self) -> dict[int, int]:
        rows = self.session.execute(text("""
            SELECT d.id, c.room_id
            FROM devices d JOIN cabinets c ON c.id = d.cabinet_id
            WHERE d.deleted_at IS NULL AND c.room_id IS NOT NULL
        """)).fetchall()
        return {r[0]: r[1] for r in rows}

    def delete_ip_switch_info_cross_room(self, ip: str, room_id: int) -> None:
        self.session.execute(text(
            "DELETE FROM ip_switch_info WHERE ip_address = :ip AND room_id != :rid"
        ), {"ip": ip, "rid": room_id})

    def delete_ip_addresses_cross_room(self, ip: str, room_id: int) -> None:
        self.session.execute(text(
            "DELETE FROM ip_addresses WHERE ip_address = :ip AND room_id != :rid"
        ), {"ip": ip, "rid": room_id})

    def upsert_ip_switch_info_with_port(self, ip: str, mac: str,
                                         switch_id: int, port: str,
                                         room_id: int) -> None:
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
        self.session.execute(text(
            "DELETE FROM ip_switch_info WHERE ip_address = :ip"
        ), {"ip": ip})


    def load_planned_networks(self, room_ids: list[int]) -> list[tuple[str, int]]:
        rows = self.session.execute(
            text("SELECT DISTINCT network, room_id FROM ip_networks WHERE room_id IN :rids AND network NOT LIKE '%/32'")
            .bindparams(bindparam("rids", expanding=True)),
            {"rids": list(room_ids)}
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def load_blackhole_ips(self, room_ids: list[int]) -> set[str]:
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
        rows = self.session.execute(
            text(
                "SELECT ip_address FROM ip_addresses "
                "WHERE ip_address IN :ips AND room_id != :rid"
            ).bindparams(bindparam("ips", expanding=True)),
            {"ips": batch, "rid": room_id}
        ).fetchall()
        return {r[0] for r in rows}

    def batch_insert_ignore_ips(self, insert_batch: list[str], room_id: int, status: int) -> None:
        if insert_batch:
            self.session.execute(text("""
                INSERT IGNORE INTO ip_addresses (ip_address, room_id, status)
                VALUES (:ip, :rid, :unused)
            """), [{"ip": ip, "rid": room_id, "unused": status}
                   for ip in insert_batch])

    def batch_update_active_status(self, active_ips: list[str], room_id: int) -> None:
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

    def __init__(self, session=None):
        super().__init__(IPSwitchInfo, session or db.session)

    def get_by_ip_room(self, ip: str, room_id: int) -> Optional[IPSwitchInfo]:
        return self.find_one({"ip_address": ip, "room_id": room_id})

    def upsert_ip_info(
        self, ip_address: str, room_id: int, switch_id: int,
        port: str = None, mac_address: str = None,
    ) -> IPSwitchInfo:
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
        stmt = delete(IPSwitchInfo).where(
            IPSwitchInfo.ip_address.in_(ip_list), IPSwitchInfo.room_id == room_id,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_delete_by_ips_and_switch_room(
        self, ip_list: List[str], switch_id: int, room_id: int,
    ) -> int:
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
        stmt = delete(IPSwitchInfo).where(
            IPSwitchInfo.ip_address.in_(ip_list), IPSwitchInfo.switch_id == switch_id,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def batch_delete_by_ips(self, ip_list: List[str]) -> int:
        stmt = delete(IPSwitchInfo).where(IPSwitchInfo.ip_address.in_(ip_list))
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def find_by_ip_address(self, ip_address: str) -> List[IPSwitchInfo]:
        return self.find_all({"ip_address": ip_address})

    def find_by_mac_address(self, mac_address: str) -> List[IPSwitchInfo]:
        return self.find_all({"mac_address": mac_address})

    def find_by_switch_id(self, switch_id: int) -> List[IPSwitchInfo]:
        return self.find_all({"switch_id": switch_id})

    def find_by_room_id(self, room_id: int) -> List[IPSwitchInfo]:
        return self.find_all({"room_id": room_id})

    def _bulk_upsert(self, rows: List[dict], update_cols: List[str]) -> int:
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
        return self._bulk_upsert(rows, ["switch_id", "port"])

    def bulk_upsert_switch_only(self, rows: List[dict]) -> int:
        return self._bulk_upsert(rows, ["switch_id"])

    def bulk_upsert_full(self, rows: List[dict]) -> int:
        return self._bulk_upsert(rows, ["mac_address", "switch_id", "port"])

    def bulk_upsert_full_with_room(self, rows: List[dict]) -> int:
        return self._bulk_upsert(rows, ["mac_address", "switch_id", "port", "room_id"])


class IPNetworkRepository(BaseRepository):

    def __init__(self, session=None):
        super().__init__(IPNetwork, session or db.session)

    def get_by_switch(self, switch_id: int, room_id: int) -> List[IPNetwork]:
        return self.find_all({"switch_id": switch_id, "room_id": room_id})

    def get_blackhole_for_ip(
        self, ip_address: str, switch_id: int,
    ) -> Optional["SwitchRoute"]:
        from app.models.switch_route import SwitchRoute
        return self.session.query(SwitchRoute).filter(
            SwitchRoute.destination == f"{ip_address}/32",
            SwitchRoute.switch_id == switch_id,
            SwitchRoute.route_type == int(RouteNotes.BLACKHOLE),
        ).first()

    def delete_blackhole_for_ip(self, ip_address: str, switch_id: int) -> int:
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
        return self.find_all({"network": ip_network, "room_id": room_id})

    def find_by_switch_and_room(
        self, switch_id: int, room_id: int,
    ) -> List[IPNetwork]:
        return self.find_all({"switch_id": switch_id, "room_id": room_id})

    def find_exact_match(
        self, ip_network: str, switch_id: int, room_id: int,
    ) -> Optional[IPNetwork]:
        return self.find_one({
            "network": ip_network, "switch_id": switch_id, "room_id": room_id,
        })

    def count_by_network_and_room(self, ip_network: str, room_id: int) -> int:
        return self.session.query(IPNetwork).filter(
            IPNetwork.network == ip_network, IPNetwork.room_id == room_id,
        ).count()

    def count_by_network(self, ip_network: str) -> int:
        return self.session.query(IPNetwork).filter(
            IPNetwork.network == ip_network,
        ).count()

    def find_by_switch_and_route_type(
        self, switch_id: int, route_type: int,
    ) -> List["SwitchRoute"]:
        from app.models.switch_route import SwitchRoute
        return self.session.query(SwitchRoute).filter(
            SwitchRoute.switch_id == switch_id,
            SwitchRoute.route_type == route_type,
        ).all()

    find_by_switch_and_notes = find_by_switch_and_route_type

    def delete_by_switch_and_networks(
        self, switch_id: int, network_names: List[str],
    ) -> int:
        stmt = delete(IPNetwork).where(
            IPNetwork.switch_id == switch_id,
            IPNetwork.network.in_(network_names),
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def delete_by_switch_and_room(self, switch_id: int, room_id: int) -> int:
        stmt = delete(IPNetwork).where(
            IPNetwork.switch_id == switch_id, IPNetwork.room_id == room_id,
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def delete_by_switch(self, switch_id: int) -> int:
        stmt = delete(IPNetwork).where(IPNetwork.switch_id == switch_id)
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount

    def find_by_switch_id(self, switch_id: int) -> List[IPNetwork]:
        return self.find_all({"switch_id": switch_id})

    def find_by_customer_id(self, customer_id: int) -> List[IPNetwork]:
        return self.find_all({"customer_id": customer_id})

    def clear_customer(self, customer_id: int) -> int:
        result = self.session.query(IPNetwork).filter(
            IPNetwork.customer_id == customer_id,
        ).update({IPNetwork.customer_id: None}, synchronize_session=False)
        return result

    def find_by_room_id(self, room_id: int) -> List[IPNetwork]:
        return self.find_all({"room_id": room_id})

    def bulk_upsert_network(self, network_data_list: List[dict]) -> int:
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
        from app.models.switch_route import SwitchRoute
        rows = self.session.query(SwitchRoute.network_id).filter(
            SwitchRoute.route_type == route_type,
        ).all()
        return [r[0] for r in rows]

    def find_switch_routes_by_network_ids(self, network_ids: list[int]) -> dict:
        from app.models.switch_route import SwitchRoute
        if not network_ids:
            return {}
        rows = self.session.query(SwitchRoute).filter(
            SwitchRoute.network_id.in_(network_ids),
        ).all()
        return {sr.network_id: sr for sr in rows}

    def find_switch_route(self, switch_id: int, destination: str, room_id: int) -> Optional["SwitchRoute"]:
        from app.models.switch_route import SwitchRoute
        return self.session.query(SwitchRoute).filter(
            SwitchRoute.switch_id == switch_id,
            SwitchRoute.destination == destination,
            SwitchRoute.room_id == room_id,
        ).first()

    def find_switch_routes_by_switch_destinations(
        self, switch_ids: set[int], destinations: set[str],
    ) -> list["SwitchRoute"]:
        from app.models.switch_route import SwitchRoute
        if not switch_ids or not destinations:
            return []
        return self.session.query(SwitchRoute).filter(
            SwitchRoute.switch_id.in_(switch_ids),
            SwitchRoute.destination.in_(destinations),
        ).all()


class IPBanRecordRepository(BaseRepository):

    def __init__(self, session=None):
        from app.models.ip_model import IPBanRecord
        super().__init__(IPBanRecord, session or db.session)

    def find_active_ban(self, ip_address: str, room_id: int):
        from app.models.ip_model import IPBanRecord
        return self.session.query(IPBanRecord).filter(
            IPBanRecord.ip_address == ip_address,
            IPBanRecord.room_id == room_id,
            IPBanRecord.is_active == True,
        ).first()

    def exists_active_ban(self, ip_address: str, room_id: int) -> bool:
        from app.models.ip_model import IPBanRecord
        return self.session.query(
            self.session.query(IPBanRecord).filter(
                IPBanRecord.ip_address == ip_address,
                IPBanRecord.room_id == room_id,
                IPBanRecord.is_active == True,
            ).exists()
        ).scalar()

    def find_all_active(self):
        from app.models.ip_model import IPBanRecord
        return self.session.query(IPBanRecord).filter(
            IPBanRecord.is_active == True,
        ).all()
