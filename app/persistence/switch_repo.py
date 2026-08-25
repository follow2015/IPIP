# -*- coding: utf-8 -*-
"""
交换机域 Repository

提供 SwitchCredentials 的数据访问方法。
端口操作已迁移到 NetworkPortRepository（统一端口表 network_ports）。
"""
import json
import ipaddress
from app.utils.logging import get_logger
from typing import List, Optional

from sqlalchemy import update, delete, or_, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload, contains_eager

from app.exceptions.data_access import QueryExecutionError

from app.persistence.base import BaseRepository
from app.models.switch_credentials import SwitchCredentials, SwitchPortIP
from app.models.network_port import NetworkPort
from app.models.device import Device
from app.models.cabinet import Cabinet
from app.models.device_connection import DeviceConnection
from app.core.enums import SwitchStatus
from extensions import db

logger = get_logger(__name__)


class SwitchRepository(BaseRepository):

    def __init__(self, session=None):
        super().__init__(SwitchCredentials, session or db.session)
        self.device_model = Device

    def find_by_device_id(self, device_id: int) -> Optional[SwitchCredentials]:
        try:
            return self.session.query(SwitchCredentials).filter_by(
                device_id=device_id
            ).first()
        except SQLAlchemyError as e:
            self.logger.error("根据 device_id 查找 SwitchCredentials 失败 (device_id=%d): %s", device_id, e)
            raise QueryExecutionError("查找交换机失败", original_error=e)

    def get_by_room(
        self, room_id: int, status: Optional[int] = None,
    ) -> List[SwitchCredentials]:
        query = (
            self.session.query(SwitchCredentials)
            .join(Device, SwitchCredentials.device_id == Device.id)
            .join(Cabinet, Device.cabinet_id == Cabinet.id)
            .filter(Cabinet.room_id == room_id, Device.deleted_at.is_(None))
        )
        if status is not None:
            from app.models.device_switch_ext import DeviceSwitchExt
            query = query.join(DeviceSwitchExt, DeviceSwitchExt.device_id == Device.id).filter(
                DeviceSwitchExt.switch_role == status
            )
        return query.all()

    def get_by_device_ids(
        self, device_ids: List[int],
    ) -> List[SwitchCredentials]:
        return (
            self.session.query(SwitchCredentials)
            .join(Device, SwitchCredentials.device_id == Device.id)
            .filter(
                SwitchCredentials.device_id.in_(device_ids),
                Device.deleted_at.is_(None),
            )
            .all()
        )

    def get_core_switches(self, room_id: int) -> List[SwitchCredentials]:
        return self.get_by_room(room_id, status=SwitchStatus.CORE)

    def name_ip_exists(
        self, name: str, ip: str, exclude_id: Optional[int] = None,
    ) -> bool:
        if ip:
            ip_query = self.session.query(SwitchCredentials.id).filter(
                SwitchCredentials.ip == ip
            )
            if exclude_id:
                ip_query = ip_query.filter(SwitchCredentials.id != exclude_id)
            if ip_query.first():
                return True

        if name:
            name_query = self.session.query(Device).with_entities(Device.id).filter(
                Device.device_name == name,
                Device.device_type == "network",
                Device.deleted_at.is_(None),
            )
            if exclude_id:
                cred = self.session.query(SwitchCredentials.device_id).filter(
                    SwitchCredentials.id == exclude_id
                ).first()
                if cred:
                    name_query = name_query.filter(Device.id != cred[0])
            if name_query.first() is not None:
                return True

        return False

    def create_switch_with_device(
        self,
        device_data: dict,
        switch_data: dict,
        ext_data: Optional[dict] = None,
    ) -> SwitchCredentials:
        device = Device(**device_data)
        self.session.add(device)
        self.session.flush()

        switch_data["device_id"] = device.id
        switch = SwitchCredentials(**switch_data)
        self.session.add(switch)
        self.session.flush()

        if ext_data:
            from app.models.device_switch_ext import DeviceSwitchExt
            ext = DeviceSwitchExt.query.get(device.id)
            if not ext:
                ext = DeviceSwitchExt(device_id=device.id)
                self.session.add(ext)
                self.session.flush()
            for k, v in ext_data.items():
                if v is not None:
                    if k == "hostname":
                        setattr(device, k, v)
                    else:
                        setattr(ext, k, v)

        return switch

    def has_ports(self, switch_id: int) -> bool:
        return self.session.query(
            self.session.query(NetworkPort.id)
            .filter(NetworkPort.device_id == switch_id)
            .exists()
        ).scalar()

    def find_room_switch_ids(self, room_id: int) -> List[int]:
        rows = self.session.query(SwitchCredentials.device_id).join(
            Device, SwitchCredentials.device_id == Device.id
        ).join(
            Cabinet, Device.cabinet_id == Cabinet.id
        ).filter(
            Cabinet.room_id == room_id,
        ).all()
        return [r[0] for r in rows]

    def find_all_switches(self) -> List[SwitchCredentials]:
        return self.find_all()

    def check_ip_exists(self, ip_address: str) -> bool:
        return self.session.query(SwitchCredentials.id).filter(
            SwitchCredentials.ip == ip_address,
        ).first() is not None

    def find_by_filters(
        self, room_id: int = None, name: str = None, ip: str = None,
        search: str = None, switch_role: int = None, device_type: str = None,
        cabinet_id: int = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        query = self.session.query(Device).options(
            joinedload(Device.cabinet).joinedload(Cabinet.room),
            contains_eager(Device.switch_credential),
            joinedload(Device.switch_ext),
            joinedload(Device.status_cache),
        ).outerjoin(
            SwitchCredentials, SwitchCredentials.device_id == Device.id,
        ).filter(
            Device.device_type == 'network',
            Device.deleted_at.is_(None),
        )
        if room_id is not None:
            query = query.join(Cabinet, Device.cabinet_id == Cabinet.id).filter(Cabinet.room_id == room_id)
        if name:
            query = query.filter(Device.device_name == name)
        if cabinet_id is not None:
            query = query.filter(Device.cabinet_id == cabinet_id)
        if ip:
            query = query.filter(SwitchCredentials.ip == ip)
        if search:
            query = query.filter(
                or_(
                    Device.device_name.contains(search),
                    SwitchCredentials.ip.contains(search),
                )
            )
        if switch_role is not None:
            from app.models.device_switch_ext import DeviceSwitchExt
            query = query.outerjoin(DeviceSwitchExt, DeviceSwitchExt.device_id == Device.id).filter(
                DeviceSwitchExt.switch_role == switch_role
            )
        if device_type:
            query = query.filter(SwitchCredentials.device_type == device_type)

        query = query.distinct()

        total = query.count()
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()

        device_ids_on_page = [item.id for item in items]
        count_map: dict[int, int] = {}
        if device_ids_on_page:
            count_rows = self.session.query(
                DeviceConnection.switch_device_id,
                func.count(DeviceConnection.id),
            ).filter(
                DeviceConnection.switch_device_id.in_(device_ids_on_page),
            ).group_by(
                DeviceConnection.switch_device_id,
            ).all()
            count_map = {row[0]: row[1] for row in count_rows}

        uplink_device_ids = {
            item.switch_ext.uplink_device_id
            for item in items
            if item.switch_ext and item.switch_ext.uplink_device_id
        }
        all_port_ids = [
            pid
            for item in items
            if item.switch_ext and item.switch_ext.uplink_port_ids
            for pid in item.switch_ext.uplink_port_ids
        ]
        uplink_device_map: dict = {}
        if uplink_device_ids:
            rows = self.session.query(Device).with_entities(Device.id, Device.device_name) \
                               .filter(Device.id.in_(uplink_device_ids), Device.deleted_at.is_(None)).all()
            uplink_device_map = {r[0]: r[1] for r in rows}
        port_name_map: dict = {}
        if all_port_ids:
            from app.models.network_port import NetworkPort
            port_rows = self.session.query(NetworkPort.id, NetworkPort.port_name) \
                                     .filter(NetworkPort.id.in_(all_port_ids)).all()
            port_name_map = {r[0]: r[1] for r in port_rows}

        result = []
        for item in items:
            sc = item.switch_credential
            if sc:
                data = sc.to_dict(exclude=["password"])
            else:
                data = {
                    "id": None,
                    "device_id": item.id,
                    "ip": None,
                    "port": None,
                    "username": None,
                    "protocol": None,
                    "authentication_method": None,
                    "device_type": None,
                    "has_ssh": False,
                }
            data["ip_address"] = data.pop("ip", None)
            data["name"] = item.device_name
            data["device_model"] = item.device_model
            data["serial_number"] = item.serial_number
            data["hostname"] = item.hostname
            if item.switch_ext:
                data["switch_role"] = item.switch_ext.switch_role
                data["layer"] = item.switch_ext.layer
                data["uplink_device_id"] = item.switch_ext.uplink_device_id
                data["core_device_id"] = item.switch_ext.core_device_id
                data["port_num"] = item.switch_ext.port_num
                if item.switch_ext.uplink_device_id:
                    data["uplink_device_name"] = uplink_device_map.get(item.switch_ext.uplink_device_id)
                if item.switch_ext.uplink_port_ids:
                    data["uplink_port_names"] = [
                        port_name_map.get(pid, f"(ID:{pid})")
                        for pid in item.switch_ext.uplink_port_ids
                    ]
                else:
                    data["uplink_port_names"] = None
            if item.status_cache:
                data["device_version"] = item.status_cache.device_version
                data["device_uptime"] = item.status_cache.device_uptime
            data["device_serial"] = item.serial_number
            if item.cabinet:
                data["room_id"] = item.cabinet.room_id
                if item.cabinet.room:
                    data["room_name"] = item.cabinet.room.name
            data["connected_device_count"] = count_map.get(item.id, 0)
            result.append(data)

        return {
            "items": result,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        }


    def get_switch_ports_list(self, switch_id: int) -> List[str]:
        rows = self.session.query(NetworkPort.port_name).filter(
            NetworkPort.device_id == switch_id,
        ).all()
        return [r[0] for r in rows]

    def update_port_status_vlan(
        self, switch_id: int, port: str, vlan: int,
    ) -> None:
        stmt = update(NetworkPort).where(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).values(vlan=vlan, updated_at=func.now())
        self.session.execute(stmt)
        self.session.flush()

    def get_ports_by_vlan(self, switch_id: int, vlan: int) -> List[str]:
        affected = self.session.query(NetworkPort.port_name).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.vlan == vlan,
        ).all()
        return [r[0] for r in affected]

    def reset_ports_vlan(self, switch_id: int, old_vlan: int, new_vlan: int = 1) -> List[str]:
        affected = self.session.query(NetworkPort.port_name).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.vlan == old_vlan,
        ).all()
        port_names = [r[0] for r in affected]

        if port_names:
            stmt = update(NetworkPort).where(
                NetworkPort.device_id == switch_id,
                NetworkPort.vlan == old_vlan,
            ).values(vlan=new_vlan, updated_at=func.now())
            self.session.execute(stmt)
            self.session.flush()

        return port_names

    def get_port_vlan(self, switch_id: int, port: str) -> Optional[int]:
        info = self.session.query(NetworkPort.vlan).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).first()
        if not info or info[0] is None:
            return None
        try:
            return int(info[0])
        except (ValueError, TypeError):
            return None

    def update_port_customer(
        self, switch_id: int, port: str, customer_id: int,
    ) -> None:
        stmt = update(NetworkPort).where(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).values(customer_id=customer_id, updated_at=func.now())
        self.session.execute(stmt)
        self.session.flush()

    def update_port_description(
        self, switch_id: int, port: str, description: str,
    ) -> None:
        stmt = update(NetworkPort).where(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).values(description=description, updated_at=func.now())
        self.session.execute(stmt)
        self.session.flush()

    def update_port_status(
        self, switch_id: int, port: str, status: str,
    ) -> None:
        usage_status = NetworkPort.derive_usage_status(status, port)
        stmt = update(NetworkPort).where(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).values(link_status=status, usage_status=usage_status, updated_at=func.now())
        self.session.execute(stmt)
        self.session.flush()

    def get_port_ips(self, switch_id: int, port: str) -> List[dict]:
        rows = self.session.query(SwitchPortIP).filter(
            SwitchPortIP.device_id == switch_id,
            SwitchPortIP.port_name == port,
        ).all()
        return [r.to_dict() for r in rows]

    def add_port_ip(
        self, switch_id: int, port: str, ip_address: str,
        subnet_mask: str = "255.255.255.0", is_primary: bool = True,
    ) -> None:
        record = SwitchPortIP(
            device_id=switch_id, port_name=port,
            ip_address=ip_address, subnet_mask=subnet_mask,
            is_primary=is_primary, vlan=None,
        )
        self.session.add(record)
        self.session.flush()

    def delete_port_ip(
        self, switch_id: int, port: str, ip_address: str, subnet_mask: str = None,
    ) -> None:
        stmt = delete(SwitchPortIP).where(
            SwitchPortIP.device_id == switch_id,
            SwitchPortIP.port_name == port,
            SwitchPortIP.ip_address == ip_address,
        )
        self.session.execute(stmt)
        self.session.flush()

    def sync_port_ips(
        self, switch_id: int, port: str, ip_list: List[dict],
    ) -> None:
        stmt = delete(SwitchPortIP).where(
            SwitchPortIP.device_id == switch_id,
            SwitchPortIP.port_name == port,
        )
        self.session.execute(stmt)
        for ip_data in ip_list:
            record = SwitchPortIP(
                device_id=switch_id, port_name=port,
                ip_address=ip_data["ip_address"],
                subnet_mask=ip_data.get("subnet_mask", "255.255.255.0"),
                prefix=ip_data.get("prefix"),
                is_primary=ip_data.get("is_primary", True),
                vlan=ip_data.get("vlan"),
            )
            self.session.add(record)
        self.session.flush()

    def check_ip_subnet_conflict(
        self, device_id: int, ip_address: str, subnet_mask: str, port: str,
    ) -> Optional[dict]:
        try:
            new_net = ipaddress.IPv4Network(f"{ip_address}/{subnet_mask}", strict=False)
        except (ValueError, TypeError):
            return None

        rows = self.session.query(
            SwitchPortIP.port_name, SwitchPortIP.ip_address, SwitchPortIP.subnet_mask,
        ).filter(
            SwitchPortIP.device_id == device_id,
            SwitchPortIP.port_name != port,
        ).all()

        for row_port, row_ip, row_mask in rows:
            try:
                existing_net = ipaddress.IPv4Network(
                    f"{row_ip}/{row_mask}", strict=False,
                )
            except (ValueError, TypeError):
                continue
            if new_net.overlaps(existing_net):
                return {
                    "port": row_port,
                    "ip": row_ip,
                    "subnet": str(existing_net),
                }
        return None

    def get_port_info_cache(
        self, switch_id: int, port: str,
    ) -> Optional[dict]:
        info = self.session.query(NetworkPort).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).first()
        return info.to_dict() if info else None

    @staticmethod
    def _parse_port_info_text(raw: str) -> str:
        if not raw:
            return raw
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "port_info" in data:
                return data["port_info"]
            return json.dumps(data, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            return raw

    def get_port_config_text(self, switch_id: int, port: str) -> Optional[str]:
        row = self.session.query(NetworkPort.raw_info).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).first()
        if not row or not row[0]:
            return None
        return self._parse_port_info_text(row[0])

    def get_port_config_with_time(
        self, switch_id: int, port: str,
    ) -> Optional[dict]:
        row = self.session.query(
            NetworkPort.raw_info, NetworkPort.updated_at,
        ).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).first()
        if not row or not row[0]:
            return None
        raw, updated_at = row
        return {
            "port_config": self._parse_port_info_text(raw),
            "updated_at": str(updated_at) if updated_at else None,
        }

    def upsert_port_info_cache(
        self, switch_id: int, port: str, data: dict,
    ) -> None:
        info = self.session.query(NetworkPort).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).first()
        if info:
            for key, value in data.items():
                if hasattr(info, key):
                    setattr(info, key, value)
        else:
            info = NetworkPort(device_id=switch_id, port_name=port, **data)
            self.session.add(info)
        self.session.flush()

    def upsert_port_config(
        self, switch_id: int, port: str, config_text: str,
    ) -> None:
        port_info_json = json.dumps(
            {"port_info": config_text}, ensure_ascii=False,
        )
        row = self.session.query(NetworkPort).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).first()
        if row:
            row.raw_info = port_info_json
        else:
            row = NetworkPort(
                device_id=switch_id, port_name=port, raw_info=port_info_json,
            )
            self.session.add(row)
        self.session.flush()

    def delete_port_config(self, switch_id: int, port: str) -> None:
        row = self.session.query(NetworkPort).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).first()
        if row:
            row.raw_info = None
            self.session.flush()

    def update_vlan_trunk_info(self, switch_id: int, port: str) -> None:
        existing = self.session.query(NetworkPort).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).first()
        if existing is None:
            self.session.add(NetworkPort(device_id=switch_id, port_name=port))
            self.session.flush()

    def delete_vlan_trunk_info(self, switch_id: int, port: str) -> None:
        self.session.query(NetworkPort).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.port_name == port,
        ).delete(synchronize_session=False)
        self.session.flush()

    def get_most_common_mac(self, switch_id: int) -> Optional[str]:
        result = self.session.query(
            NetworkPort.mac, func.count(NetworkPort.mac),
        ).filter(
            NetworkPort.device_id == switch_id,
            NetworkPort.mac != None,
            NetworkPort.mac != "",
        ).group_by(NetworkPort.mac).order_by(func.count(NetworkPort.mac).desc()).first()
        return result[0] if result else None

    def get_ports_with_customer(self, switch_id: int) -> List[dict]:
        ports = self.session.query(NetworkPort).filter(
            NetworkPort.device_id == switch_id,
        ).all()
        return [p.to_dict() for p in ports]


    def find_vlan_by_device_and_id(self, device_id: int, vlan_id: int):
        from app.models.vlan import VLAN
        return self.session.query(VLAN).filter_by(
            device_id=device_id, vlan_id=vlan_id,
        ).first()

    def delete_vlan_record(self, vlan_row) -> None:
        self.session.delete(vlan_row)

    def upsert_vlan_record(self, device_id: int, vlan_id: int,
                           room_id: int = None):
        from app.services.vlan_service import VLANService
        from app.persistence.vlan_repository import VLANRepository
        return VLANService(VLANRepository()).ensure_vlan(device_id, vlan_id, room_id=room_id)

    def find_lag_by_device_and_name(self, device_id: int, lag_name: str):
        from app.models.link_aggregation import LinkAggregationGroup
        return self.session.query(LinkAggregationGroup).filter_by(
            device_id=device_id, lag_name=lag_name,
        ).first()

    def upsert_lag_record(self, device_id: int, lag_name: str):
        from app.models.link_aggregation import LinkAggregationGroup
        lag_row = self.session.query(LinkAggregationGroup).filter_by(
            device_id=device_id, lag_name=lag_name,
        ).first()
        if not lag_row:
            lag_row = LinkAggregationGroup(
                device_id=device_id, lag_name=lag_name,
                member_count=0,
            )
            self.session.add(lag_row)
            self.session.flush()
            return lag_row, True
        return lag_row, False

    def delete_lag_record(self, device_id: int, lag_name: str) -> None:
        from app.models.link_aggregation import LinkAggregationGroup
        lag_row = self.session.query(LinkAggregationGroup).filter_by(
            device_id=device_id, lag_name=lag_name,
        ).first()
        if lag_row:
            self.session.delete(lag_row)

    def delete_lag_record_by_obj(self, lag_row) -> None:
        self.session.delete(lag_row)

    def find_port_by_device_and_name(self, device_id: int, port_name: str):
        return self.session.query(NetworkPort).filter_by(
            device_id=device_id, port_name=port_name,
        ).first()

    def set_port_lag_group(self, device_id: int, port_name: str,
                           lag_group_id: int) -> None:
        port_row = self.session.query(NetworkPort).filter_by(
            device_id=device_id, port_name=port_name,
        ).first()
        if port_row:
            port_row.lag_group_id = lag_group_id
            self.session.flush()

    def clear_port_lag_group(self, device_id: int, port_name: str) -> Optional[int]:
        port_row = self.session.query(NetworkPort).filter_by(
            device_id=device_id, port_name=port_name,
        ).first()
        if not port_row or port_row.lag_group_id is None:
            return None
        lag_id = port_row.lag_group_id
        port_row.lag_group_id = None
        self.session.flush()
        return lag_id

    def count_lag_members(self, lag_group_id: int) -> int:
        return self.session.query(NetworkPort).filter_by(
            lag_group_id=lag_group_id,
        ).count()

    def sync_lag_member_count(self, lag_group_id: int) -> None:
        from app.models.link_aggregation import LinkAggregationGroup
        actual_count = self.session.query(NetworkPort).filter_by(
            lag_group_id=lag_group_id,
        ).count()
        lag_row = self.session.query(LinkAggregationGroup).get(lag_group_id)
        if lag_row:
            lag_row.member_count = actual_count
            self.session.flush()

    def delete_port_ips_by_vlan(self, device_id: int, vlan_id: int) -> None:
        SwitchPortIP.query.filter_by(
            device_id=device_id, vlan=vlan_id,
        ).update({SwitchPortIP.vlan: None}, synchronize_session=False)

    def clear_connection_vlan_refs(self, device_id: int, vlan_id: int) -> None:
        from app.models.device_connection import DeviceConnection
        from app.models.network_connection import NetworkConnection

        self.session.query(DeviceConnection).filter(
            DeviceConnection.switch_device_id == device_id,
            DeviceConnection.vlan_id == vlan_id,
        ).update({DeviceConnection.vlan_id: None}, synchronize_session=False)

        self.session.query(NetworkConnection).filter(
            or_(
                NetworkConnection.local_device_id == device_id,
                NetworkConnection.peer_device_id == device_id,
            ),
            NetworkConnection.vlan_id == vlan_id,
        ).update({NetworkConnection.vlan_id: None}, synchronize_session=False)

    def update_vlan_member_relation(self, device_id: int, port_name: str,
                                    vlan_id: int, mode: str,
                                    room_id: int = None) -> None:
        from app.models.vlan_port_member import VLANPortMember
        from app.services.vlan_service import VLANService
        from app.persistence.vlan_repository import VLANRepository

        vlan_row = VLANService(VLANRepository()).ensure_vlan(device_id, vlan_id, room_id=room_id)

        port_row = self.session.query(NetworkPort).filter_by(
            device_id=device_id, port_name=port_name,
        ).first()
        if not port_row:
            return

        self.session.query(VLANPortMember).filter_by(
            port_id=port_row.id,
        ).delete()

        existing = self.session.query(VLANPortMember).filter_by(
            vlan_id=vlan_row.id, port_id=port_row.id,
        ).first()
        if not existing:
            vpm = VLANPortMember(
                vlan_id=vlan_row.id, port_id=port_row.id,
                port_mode=mode if mode in ("access", "trunk", "hybrid") else "access",
            )
            self.session.add(vpm)
        self.session.flush()

    def update_lag_member_relation(self, device_id: int, port_name: str,
                                   channel_id: int, device_type: str = None) -> None:
        from app.utils.port_name_utils import get_trunk_name
        trunk_name = get_trunk_name(device_type, channel_id) if device_type else f"Eth-Trunk{channel_id}"
        lag_row, _ = self.upsert_lag_record(device_id, trunk_name)

        port_row = self.session.query(NetworkPort).filter_by(
            device_id=device_id, port_name=port_name,
        ).first()
        if port_row:
            port_row.lag_group_id = lag_row.id
            self.session.flush()

        actual_count = self.session.query(NetworkPort).filter_by(
            lag_group_id=lag_row.id,
        ).count()
        lag_row.member_count = actual_count
        self.session.flush()

    def clear_lag_member_relation(self, device_id: int, port_name: str) -> None:
        port_row = self.session.query(NetworkPort).filter_by(
            device_id=device_id, port_name=port_name,
        ).first()
        if not port_row or port_row.lag_group_id is None:
            return

        lag_id = port_row.lag_group_id
        port_row.lag_group_id = None
        self.session.flush()

        from app.models.link_aggregation import LinkAggregationGroup
        lag_row = self.session.query(LinkAggregationGroup).get(lag_id)
        if lag_row:
            lag_row.member_count = self.session.query(NetworkPort).filter_by(
                lag_group_id=lag_id,
            ).count()
            self.session.flush()

    def sync_vlan_members(self, device_id: int, port: str, members: list) -> None:
        import re
        from app.models.vlan import VLAN
        from app.models.vlan_port_member import VLANPortMember

        id_match = re.search(r"\d+", port)
        if not id_match:
            return
        vlan_id = int(id_match.group())
        if not (1 <= vlan_id <= 4094):
            return

        row = self.session.query(VLAN).filter(
            VLAN.device_id == device_id,
            VLAN.vlan_id == vlan_id,
        ).first()
        if not row:
            row = VLAN(
                device_id=device_id,
                vlan_id=vlan_id,
                name=port,
            )
            try:
                nested = self.session.begin_nested()
                self.session.add(row)
                self.session.flush()
                nested.commit()
            except IntegrityError:
                row = self.session.query(VLAN).filter(
                    VLAN.device_id == device_id,
                    VLAN.vlan_id == vlan_id,
                ).first()
                if not row:
                    raise

        self.session.query(VLANPortMember).filter(
            VLANPortMember.vlan_id == row.id,
        ).delete()
        if members:
            port_rows = self.session.query(NetworkPort.id, NetworkPort.port_name).filter(
                NetworkPort.device_id == device_id,
                NetworkPort.port_name.in_(members),
            ).all()
            port_id_map = {name: pid for pid, name in port_rows}
            for member_name in members:
                port_id = port_id_map.get(member_name)
                if port_id:
                    vpm = VLANPortMember(
                        vlan_id=row.id,
                        port_id=port_id,
                        port_mode="access",
                    )
                    self.session.add(vpm)
        self.session.flush()

    def sync_trunk_members(self, device_id: int, port: str, members: list) -> None:
        from app.models.link_aggregation import LinkAggregationGroup

        row = self.session.query(LinkAggregationGroup).filter(
            LinkAggregationGroup.device_id == device_id,
            LinkAggregationGroup.lag_name == port,
        ).first()
        if not row:
            row = LinkAggregationGroup(
                device_id=device_id,
                lag_name=port,
                member_count=0,
                purpose='',
            )
            self.session.add(row)
            self.session.flush()

        self.session.query(NetworkPort).filter(
            NetworkPort.device_id == device_id,
            NetworkPort.lag_group_id == row.id,
        ).update({"lag_group_id": None}, synchronize_session="fetch")

        member_count = 0
        if members:
            port_rows = self.session.query(NetworkPort).filter(
                NetworkPort.device_id == device_id,
                NetworkPort.port_name.in_(members),
            ).all()
            for np_row in port_rows:
                np_row.lag_group_id = row.id
            member_count = len(port_rows)

        row.member_count = member_count
        self.session.flush()


    def get_port_ips_by_device_ids(
        self, device_ids: list[int],
    ) -> list[tuple[int, str, str, int | None]]:
        if not device_ids:
            return []
        from sqlalchemy import text, bindparam
        rows = self.session.execute(
            text(
                "SELECT device_id, port_name, ip_address, prefix "
                "FROM switch_port_ips "
                "WHERE device_id IN :dids AND prefix IS NOT NULL"
            ).bindparams(bindparam("dids", expanding=True)),
            {"dids": tuple(device_ids)},
        ).fetchall()
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    def get_port_ips_by_device_id(
        self, device_id: int,
    ) -> list[tuple[int, str, str, int | None]]:
        rows = self.session.execute(
            text(
                "SELECT device_id, port_name, ip_address, prefix "
                "FROM switch_port_ips "
                "WHERE device_id = :did AND prefix IS NOT NULL"
            ),
            {"did": device_id},
        ).fetchall()
        return [(r[0], r[1], r[2], r[3]) for r in rows]
