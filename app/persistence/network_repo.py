# -*- coding: utf-8 -*-
"""网络段 Repository"""
from app.utils.logging import get_logger
from typing import Any, Dict

from sqlalchemy import or_, text
from sqlalchemy.orm import joinedload

from app.models.switch_route import IPNetwork
from app.models.device import Device
from app.models.customer import Customer
from app.persistence.base import BaseRepository
from extensions import db

logger = get_logger(__name__)


class NetworkRepository(BaseRepository):

    def __init__(self, session=None):
        super().__init__(IPNetwork, session or db.session)

    def find_networks_by_filters(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        query = self.session.query(IPNetwork).outerjoin(
            IPNetwork.switch
        ).outerjoin(
            IPNetwork.customer
        ).options(
            joinedload(IPNetwork.switch),
            joinedload(IPNetwork.room),
            joinedload(IPNetwork.customer)
        )

        if filters.get("room_id"):
            query = query.filter(IPNetwork.room_id == filters["room_id"])
        if filters.get("switch_id"):
            query = query.filter(IPNetwork.switch_id == filters["switch_id"])
        if filters.get("customer_id"):
            query = query.filter(IPNetwork.customer_id == filters["customer_id"])
        if filters.get("search"):
            search_term = f"%{filters['search']}%"
            query = query.filter(
                or_(
                    IPNetwork.network.ilike(search_term),
                    Device.device_name.ilike(search_term),
                    Customer.customer_name.ilike(search_term),
                )
            )
        if filters.get("route_type") is not None:
            try:
                route_type_value = int(filters["route_type"])
                from app.models.switch_route import SwitchRoute
                query = query.filter(
                    IPNetwork.id.in_(
                        self.session.query(SwitchRoute.network_id)
                        .filter(SwitchRoute.route_type == route_type_value)
                    )
                )
            except (ValueError, TypeError):
                pass
        if filters.get("notes") is not None and filters.get("route_type") is None:
            try:
                notes_value = int(filters["notes"])
                from app.models.switch_route import SwitchRoute
                query = query.filter(
                    IPNetwork.id.in_(
                        self.session.query(SwitchRoute.network_id)
                        .filter(SwitchRoute.route_type == notes_value)
                    )
                )
            except (ValueError, TypeError):
                pass

        page = filters.get("page", 1)
        page_size = filters.get("page_size", 20)
        total = query.count()
        offset = (page - 1) * page_size
        networks = query.order_by(IPNetwork.network).offset(offset).limit(page_size).all()

        from app.models.switch_route import SwitchRoute

        network_ids = [n.id for n in networks]
        sr_map: dict[int, SwitchRoute] = {}
        if network_ids:
            sr_rows = self.session.query(SwitchRoute).filter(
                SwitchRoute.network_id.in_(network_ids)
            ).all()
            for sr in sr_rows:
                if sr.network_id not in sr_map:
                    sr_map[sr.network_id] = sr

            matched_ids = set(sr_map.keys())
            unmatched = [n for n in networks if n.id not in matched_ids]
            if unmatched:
                fallback_conditions = []
                fallback_params = {}
                for i, n in enumerate(unmatched):
                    fallback_conditions.append(
                        f"(sr.destination = :dest{i} AND sr.switch_id = :sid{i} AND sr.room_id = :rid{i})"
                    )
                    fallback_params[f"dest{i}"] = n.network
                    fallback_params[f"sid{i}"] = n.switch_id
                    fallback_params[f"rid{i}"] = n.room_id
                fallback_sql = (
                    "SELECT sr.* FROM switch_routes sr WHERE "
                    + " OR ".join(fallback_conditions)
                )
                fallback_rows = self.session.execute(text(fallback_sql), fallback_params).fetchall()
                for sr_row in fallback_rows:
                    for n in unmatched:
                        if (sr_row.destination == n.network
                                and sr_row.switch_id == n.switch_id
                                and sr_row.room_id == n.room_id):
                            if n.id not in sr_map:
                                sr_map[n.id] = sr_row
                            break

        data = []
        for network in networks:
            network_dict = network.to_dict()
            network_dict["room_name"] = network.room.name if network.room else None
            network_dict["customer_name"] = network.customer.customer_name if network.customer else None
            network_dict["switch_name"] = network.switch.device_name if network.switch else None
            sr = sr_map.get(network.id)
            network_dict["route_type"] = sr.route_type if sr else None
            network_dict["nexthop"] = sr.nexthop if sr else None
            data.append(network_dict)

        return {
            "data": data,
            "pagination": {
                "total": total,
                "page": page,
                "per_page": page_size,
                "total_pages": (total + page_size - 1) // page_size if page_size else 0,
            },
        }

    def create_network(self, data: Dict[str, Any]) -> int:
        if data.get("port") is None:
            data["port"] = ""
        network = IPNetwork(**data)
        self.session.add(network)
        self.session.flush()
        return network.id

    def update_network(self, network_id: int, data: Dict[str, Any]) -> bool:
        allowed = {"network", "notes", "customer_id", "room_id", "switch_id", "port", "gateway"}
        if "port" in data and data["port"] is None:
            data["port"] = ""
        network = self.find_by_id(network_id)
        if not network:
            return False
        for key, value in data.items():
            if key in allowed:
                setattr(network, key, value)
        self.session.flush()
        return True

    def delete_network(self, network_id: int) -> bool:
        network = self.find_by_id(network_id)
        if not network:
            return False
        self.session.delete(network)
        self.session.flush()
        return True
