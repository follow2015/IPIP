# -*- coding: utf-8 -*-
"""
客户Repository实现

提供客户相关的数据访问方法。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional

from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

from app.models.customer import Customer
from app.models.cabinet import Cabinet
from app.models.device import Device
from app.models.room import Room
from app.models.switch_route import IPNetwork
from app.models.ip_model import IPManager
from app.core.enums import CustomerStatus, DeviceStatus
from app.persistence.base import SQLAlchemyRepository
from app.exceptions.data_access import QueryExecutionError

logger = get_logger(__name__)


class CustomerRepository(SQLAlchemyRepository):
    
    def __init__(self, session=None):
        super().__init__(Customer, session)

    def _customer_count_query(self):
        return (
            self.session.query(
                Customer.id, Customer.customer_name, Customer.contact_person,
                Customer.contact_phone, Customer.email, Customer.address,
                Customer.customer_status, Customer.notes,
                Customer.created_at, Customer.updated_at,
                func.count(func.distinct(Cabinet.id)).label("cabinet_count"),
                func.count(func.distinct(Device.id)).label("device_count"),
            )
            .outerjoin(Cabinet, (Cabinet.customer_id == Customer.id) & (Cabinet.status != DeviceStatus.SCRAPPED))
            .outerjoin(Device, Device.customer_id == Customer.id)
            .group_by(Customer.id)
        )

    @staticmethod
    def _map_customer_row(r) -> Dict[str, Any]:
        return {
            "id": r.id,
            "name": r.customer_name,
            "contact": r.contact_person or "",
            "phone": r.contact_phone or "",
            "email": r.email or "",
            "address": r.address or "",
            "status": 0 if r.customer_status == CustomerStatus.ACTIVE else 1,
            "cabinet_count": r.cabinet_count or 0,
            "device_count": r.device_count or 0,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
    
    def find_by_customer_name(self, customer_name: str) -> Optional[Customer]:
        try:
            return self._base_query().filter(Customer.customer_name == customer_name).first()
        except SQLAlchemyError as e:
            self.logger.error(f"根据客户名称查找客户失败 (customer_name={customer_name}): {e}")
            raise QueryExecutionError(f"查找客户失败", original_error=e)
    
    def check_customer_name_exists(self, customer_name: str, exclude_id: int = None) -> bool:
        if not customer_name:
            return False
        
        try:
            query = self._base_query().filter(Customer.customer_name == customer_name)
            
            if exclude_id:
                query = query.filter(Customer.id != exclude_id)
            
            return self.session.query(query.exists()).scalar()
        except SQLAlchemyError as e:
            self.logger.error(f"检查客户名称存在性失败 (customer_name={customer_name}): {e}")
            raise QueryExecutionError(f"检查客户名称存在性失败", original_error=e)
    
    def get_customer_statistics(self) -> Dict[str, Any]:
        try:
            total_customers = self.count()
            
            customers_with_devices = (
                self.session.query(func.count(func.distinct(Device.customer_id)))
                .filter(Device.customer_id.isnot(None))
                .scalar()
            )
            
            customers_with_cabinets = (
                self.session.query(func.count(func.distinct(Cabinet.customer_id)))
                .filter(Cabinet.customer_id.isnot(None))
                .scalar()
            )
            
            return {
                "total_customers": total_customers,
                "customers_with_devices": customers_with_devices or 0,
                "customers_with_cabinets": customers_with_cabinets or 0,
                "customers_without_resources": total_customers - max(customers_with_devices or 0, customers_with_cabinets or 0),
            }
        except SQLAlchemyError as e:
            self.logger.error(f"获取客户统计信息失败: {e}")
            raise QueryExecutionError(f"获取客户统计信息失败", original_error=e)

    def get_all_customers_with_counts(self) -> List[Dict[str, Any]]:
        try:
            rows = (
                self._customer_count_query()
                .filter(Customer.customer_status.in_([CustomerStatus.ACTIVE, CustomerStatus.DISABLED]))
                .order_by(Customer.customer_name)
                .all()
            )
            return [self._map_customer_row(r) for r in rows]
        except SQLAlchemyError as e:
            self.logger.error(f"获取客户列表(含计数)失败: {e}")
            raise QueryExecutionError("获取客户列表失败", original_error=e)

    def get_customer_with_counts(self, customer_id: int) -> Optional[Dict[str, Any]]:
        try:
            row = (
                self._customer_count_query()
                .filter(Customer.id == customer_id)
                .first()
            )
            if not row:
                return None
            return self._map_customer_row(row)
        except SQLAlchemyError as e:
            self.logger.error(f"获取客户信息(含计数)失败 (id={customer_id}): {e}")
            raise QueryExecutionError("获取客户信息失败", original_error=e)

    def soft_delete(self, customer_id: int) -> bool:
        try:
            customer = self._base_query().filter(Customer.id == customer_id).first()
            if not customer:
                return False
            customer.customer_status = CustomerStatus.DISABLED
            self.session.flush()
            return True
        except SQLAlchemyError as e:
            self.logger.error(f"软删除客户失败 (id={customer_id}): {e}")
            raise QueryExecutionError("软删除客户失败", original_error=e)

    def check_customer_has_resources(self, customer_id: int) -> Dict[str, int]:
        try:
            cabinet_count = (
                self.session.query(func.count(Cabinet.id))
                .filter(Cabinet.customer_id == customer_id, Cabinet.status != DeviceStatus.SCRAPPED)
                .scalar()
            ) or 0

            device_count = (
                self.session.query(func.count(Device.id))
                .filter(Device.customer_id == customer_id)
                .scalar()
            ) or 0

            return {"cabinet_count": cabinet_count, "device_count": device_count}
        except SQLAlchemyError as e:
            self.logger.error(f"检查客户资源失败 (id={customer_id}): {e}")
            raise QueryExecutionError("检查客户资源失败", original_error=e)

    def get_customer_cabinets(self, customer_id: int) -> List[Dict[str, Any]]:
        try:
            rows = (
                self.session.query(
                    Cabinet.id,
                    Cabinet.cabinet_number,
                    Cabinet.room_id,
                    Cabinet.total_u,
                    Cabinet.total_power,
                    Cabinet.location,
                    Cabinet.max_weight,
                    Cabinet.notes,
                    Cabinet.created_at,
                    Cabinet.updated_at,
                    Room.name.label("room_name"),
                    func.count(Device.id).label("device_count"),
                )
                .join(Room, Cabinet.room_id == Room.id)
                .outerjoin(Device, Device.cabinet_id == Cabinet.id)
                .filter(Cabinet.customer_id == customer_id, Cabinet.status != DeviceStatus.SCRAPPED)
                .group_by(Cabinet.id, Room.name)
                .order_by(Room.name, Cabinet.cabinet_number)
                .all()
            )

            return [
                {
                    "id": r.id,
                    "cabinet_number": r.cabinet_number or "",
                    "room_id": r.room_id,
                    "total_u": r.total_u or 0,
                    "total_power": float(r.total_power or 0),
                    "location": r.location or "",
                    "max_weight": float(r.max_weight or 0),
                    "notes": r.notes or "",
                    "room_name": r.room_name or "",
                    "device_count": r.device_count or 0,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]
        except SQLAlchemyError as e:
            self.logger.error(f"获取客户机柜列表失败 (customer_id={customer_id}): {e}")
            raise QueryExecutionError("获取客户机柜列表失败", original_error=e)

    def get_customer_devices(self, customer_id: int) -> List[Dict[str, Any]]:
        try:
            rows = (
                self.session.query(
                    Device.id,
                    Device.device_name.label("name"),
                    Device.device_model.label("model"),
                    Device.device_type,
                    Device.management_ip.label("ip_address"),
                    Device.cabinet_id,
                    Device.u_position,
                    Device.height_u.label("u_height"),
                    Device.power.label("power_consumption"),
                    Device.status,
                    Device.notes,
                    Device.created_at,
                    Device.updated_at,
                    Cabinet.cabinet_number,
                    Room.name.label("room_name"),
                )
                .outerjoin(Cabinet, Device.cabinet_id == Cabinet.id)
                .outerjoin(Room, Cabinet.room_id == Room.id)
                .filter(Device.customer_id == customer_id)
                .order_by(Room.name, Cabinet.cabinet_number, Device.u_position, Device.device_name)
                .all()
            )

            return [
                {
                    "id": r.id,
                    "name": r.name or "",
                    "model": r.model or "",
                    "device_type": r.device_type or "",
                    "ip_address": r.ip_address or "",
                    "cabinet_id": r.cabinet_id,
                    "u_position": r.u_position,
                    "u_height": r.u_height,
                    "power_consumption": r.power_consumption,
                    "weight": None,
                    "status": r.status or 0,
                    "notes": r.notes or "",
                    "cabinet_number": r.cabinet_number or "",
                    "room_name": r.room_name or "",
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]
        except SQLAlchemyError as e:
            self.logger.error(f"获取客户设备列表失败 (customer_id={customer_id}): {e}")
            raise QueryExecutionError("获取客户设备列表失败", original_error=e)

    def get_customer_resource_stats(self, customer_id: int) -> Dict[str, Any]:
        try:
            from sqlalchemy import case, distinct

            full_cabinet_row = (
                self.session.query(
                    func.count(distinct(Cabinet.id)).label("cabinet_count"),
                    func.count(distinct(Device.id)).label("device_count"),
                    func.sum(Cabinet.total_u).label("total_u"),
                    func.sum(Cabinet.total_power).label("total_power"),
                    func.sum(Cabinet.max_weight).label("total_weight"),
                    func.sum(Device.height_u).label("used_u"),
                    func.sum(Device.power).label("used_power"),
                    func.count(distinct(case((Device.status == DeviceStatus.ONLINE, Device.id)))).label("active_devices"),
                    func.count(distinct(case((Device.status == DeviceStatus.OFFLINE, Device.id)))).label("fault_devices"),
                    func.count(distinct(case((Device.status == DeviceStatus.MAINTENANCE, Device.id)))).label("maintenance_devices"),
                )
                .outerjoin(Device, Cabinet.id == Device.cabinet_id)
                .filter(Cabinet.customer_id == customer_id, Cabinet.status != DeviceStatus.SCRAPPED)
                .first()
            )

            partial_cabinet_row = (
                self.session.query(
                    func.count(distinct(Cabinet.id)).label("cabinet_count"),
                    func.count(distinct(Device.id)).label("device_count"),
                    func.sum(Device.height_u).label("used_u"),
                    func.sum(Device.power).label("used_power"),
                    func.count(distinct(case((Device.status == DeviceStatus.ONLINE, Device.id)))).label("active_devices"),
                    func.count(distinct(case((Device.status == DeviceStatus.OFFLINE, Device.id)))).label("fault_devices"),
                    func.count(distinct(case((Device.status == DeviceStatus.MAINTENANCE, Device.id)))).label("maintenance_devices"),
                )
                .join(Device, Device.cabinet_id == Cabinet.id)
                .filter(
                    Device.customer_id == customer_id,
                    Device.deleted_at.is_(None),
                    Cabinet.customer_id != customer_id,
                    Cabinet.status != DeviceStatus.SCRAPPED,
                )
                .first()
            )

            fc = full_cabinet_row
            pc = partial_cabinet_row

            total_u = int(fc.total_u or 0)
            total_power = float(fc.total_power or 0)
            total_weight = float(fc.total_weight or 0)
            used_u = int((fc.used_u or 0) or 0) + int((pc.used_u or 0) or 0)
            used_power = float((fc.used_power or 0) or 0) + float((pc.used_power or 0) or 0)

            return {
                "cabinet_count": (fc.cabinet_count or 0) + (pc.cabinet_count or 0),
                "device_count": (fc.device_count or 0) + (pc.device_count or 0),
                "total_u": total_u,
                "total_power": total_power,
                "total_weight": total_weight,
                "used_u": used_u,
                "used_power": used_power,
                "used_weight": 0,
                "active_devices": (fc.active_devices or 0) + (pc.active_devices or 0),
                "fault_devices": (fc.fault_devices or 0) + (pc.fault_devices or 0),
                "maintenance_devices": (fc.maintenance_devices or 0) + (pc.maintenance_devices or 0),
            }
        except SQLAlchemyError as e:
            self.logger.error(f"获取客户资源统计失败 (customer_id={customer_id}): {e}")
            raise QueryExecutionError("获取客户资源统计失败", original_error=e)

    def get_customer_asset_statistics(self, customer_id: int) -> Dict[str, Any]:
        try:
            result = {
                'customer_id': customer_id,
                'rooms': [],
                'cabinets': {
                    'full_cabinets': [],
                    'partial_cabinets': [],
                    'total_count': 0,
                    'total_u_used': 0
                },
                'devices': {
                    'total_count': 0,
                    'by_type': {},
                    'by_cabinet': {}
                },
                'networks': {
                    'full_networks': [],
                    'partial_ips': [],
                    'total_networks': 0,
                    'total_ips': 0
                }
            }
            
            full_cabinets_query = (
                self.session.query(
                    Cabinet.id,
                    Cabinet.cabinet_number,
                    Cabinet.total_u,
                    Cabinet.used_u,
                    Cabinet.room_id,
                    Room.name.label('room_name')
                )
                .join(Room, Cabinet.room_id == Room.id)
                .filter(
                    Cabinet.customer_id == customer_id,
                    Cabinet.status != DeviceStatus.SCRAPPED,
                    Cabinet.deleted_at.is_(None),
                )
                .all()
            )

            full_cabinet_ids = []
            for cabinet in full_cabinets_query:
                full_cabinet_ids.append(cabinet.id)
                result['cabinets']['full_cabinets'].append({
                    'id': cabinet.id,
                    'cabinet_number': cabinet.cabinet_number,
                    'total_u': cabinet.total_u,
                    'used_u': cabinet.used_u,
                    'room_id': cabinet.room_id,
                    'room_name': cabinet.room_name,
                    'type': 'full'
                })
                
                if cabinet.room_id not in [r['room_id'] for r in result['rooms']]:
                    result['rooms'].append({
                        'room_id': cabinet.room_id,
                        'room_name': cabinet.room_name
                    })
            
            partial_cabinets_query = (
                self.session.query(
                    Cabinet.id,
                    Cabinet.cabinet_number,
                    Cabinet.total_u,
                    Cabinet.room_id,
                    Room.name.label('room_name'),
                    func.count(Device.id).label('device_count'),
                    func.sum(Device.height_u).label('u_used')
                )
                .join(Device, Device.cabinet_id == Cabinet.id)
                .join(Room, Cabinet.room_id == Room.id)
                .filter(
                    Device.customer_id == customer_id,
                    Device.status != DeviceStatus.SCRAPPED,
                    Device.deleted_at.is_(None),
                    Cabinet.deleted_at.is_(None),
                    ~Cabinet.id.in_(full_cabinet_ids) if full_cabinet_ids else True
                )
                .group_by(Cabinet.id)
                .all()
            )
            
            for cabinet in partial_cabinets_query:
                result['cabinets']['partial_cabinets'].append({
                    'id': cabinet.id,
                    'cabinet_number': cabinet.cabinet_number,
                    'total_u': cabinet.total_u,
                    'u_used': cabinet.u_used or 0,
                    'device_count': cabinet.device_count,
                    'room_id': cabinet.room_id,
                    'room_name': cabinet.room_name,
                    'type': 'partial'
                })
                
                if cabinet.room_id not in [r['room_id'] for r in result['rooms']]:
                    result['rooms'].append({
                        'room_id': cabinet.room_id,
                        'room_name': cabinet.room_name
                    })
            
            result['cabinets']['total_count'] = len(full_cabinet_ids) + len(partial_cabinets_query)
            result['cabinets']['total_u_used'] = sum(
                c['used_u'] or 0 for c in result['cabinets']['full_cabinets']
            ) + sum(
                c['u_used'] or 0 for c in result['cabinets']['partial_cabinets']
            )
            
            devices_query = (
                self.session.query(
                    Device.id,
                    Device.device_name,
                    Device.device_type,
                    Device.height_u,
                    Device.cabinet_id,
                    Cabinet.cabinet_number
                )
                .outerjoin(Cabinet, Device.cabinet_id == Cabinet.id)
                .filter(
                    Device.customer_id == customer_id,
                    Device.status != DeviceStatus.SCRAPPED,
                    Device.deleted_at.is_(None),
                )
                .all()
            )
            
            result['devices']['total_count'] = len(devices_query)
            result['devices']['full_cabinet_count'] = 0
            result['devices']['partial_cabinet_count'] = 0
            
            for device in devices_query:
                device_type = device.device_type or 'unknown'
                if device_type not in result['devices']['by_type']:
                    result['devices']['by_type'][device_type] = 0
                result['devices']['by_type'][device_type] += 1
                
                if device.cabinet_id:
                    if device.cabinet_id not in result['devices']['by_cabinet']:
                        result['devices']['by_cabinet'][device.cabinet_id] = {
                            'cabinet_number': device.cabinet_number,
                            'count': 0
                        }
                    result['devices']['by_cabinet'][device.cabinet_id]['count'] += 1
                
                if device.cabinet_id and device.cabinet_id in full_cabinet_ids:
                    result['devices']['full_cabinet_count'] += 1
                else:
                    result['devices']['partial_cabinet_count'] += 1
            
            full_networks_query = (
                self.session.query(
                    IPNetwork.id,
                    IPNetwork.network,
                    IPNetwork.room_id,
                    Room.name.label('room_name')
                )
                .join(Room, IPNetwork.room_id == Room.id)
                .filter(IPNetwork.customer_id == customer_id)
                .all()
            )
            
            full_network_ids = []
            for network in full_networks_query:
                full_network_ids.append(network.id)
                try:
                    import ipaddress
                    network_obj = ipaddress.ip_network(network.network, strict=False)
                    ip_count = network_obj.num_addresses
                    mask = network_obj.prefixlen
                except Exception:
                    ip_count = 0
                    mask = 0
                
                result['networks']['full_networks'].append({
                    'id': network.id,
                    'ip_network': network.network,
                    'mask': mask,
                    'ip_count': ip_count,
                    'room_id': network.room_id,
                    'room_name': network.room_name,
                    'type': 'full'
                })
                
                if network.room_id not in [r['room_id'] for r in result['rooms']]:
                    result['rooms'].append({
                        'room_id': network.room_id,
                        'room_name': network.room_name
                    })
            
            if full_network_ids:
                covered_ips_subq = (
                    self.session.query(IPManager.ip_address)
                    .join(
                        IPNetwork,
                        text(
                            "ip_addresses.ip_int BETWEEN ip_networks.network_int "
                            "AND (ip_networks.network_int "
                            "  + POW(2, 32 - ip_networks.prefix) - 1)"
                        ),
                    )
                    .filter(
                        IPNetwork.customer_id == customer_id,
                    )
                    .subquery()
                )
                partial_ips_query = (
                    self.session.query(
                        IPManager.id, IPManager.ip_address,
                        IPManager.room_id, Room.name.label('room_name'),
                    )
                    .join(Room, IPManager.room_id == Room.id)
                    .filter(
                        IPManager.customer_id == customer_id,
                        ~IPManager.ip_address.in_(covered_ips_subq),
                    )
                    .all()
                )
            else:
                partial_ips_query = (
                    self.session.query(
                        IPManager.id, IPManager.ip_address,
                        IPManager.room_id, Room.name.label('room_name'),
                    )
                    .join(Room, IPManager.room_id == Room.id)
                    .filter(IPManager.customer_id == customer_id)
                    .all()
                )

            for ip in partial_ips_query:
                result['networks']['partial_ips'].append({
                    'id': ip.id,
                    'ip_address': ip.ip_address,
                    'room_id': ip.room_id,
                    'room_name': ip.room_name,
                    'network': None,
                    'type': 'partial'
                })
                if ip.room_id not in [r['room_id'] for r in result['rooms']]:
                    result['rooms'].append({
                        'room_id': ip.room_id,
                        'room_name': ip.room_name
                    })
            
            result['networks']['total_networks'] = len(full_network_ids)
            result['networks']['total_ips'] = sum(
                n['ip_count'] for n in result['networks']['full_networks']
            ) + len(result['networks']['partial_ips'])
            
            return result
            
        except SQLAlchemyError as e:
            self.logger.error(f"获取客户资产统计失败 (customer_id={customer_id}): {e}")
            raise QueryExecutionError(f"获取客户资产统计失败", original_error=e)

    def get_customer_switch_ports_data(self, customer_id: int) -> Dict[str, Any]:
        try:
            from app.models.switch_credentials import SwitchCredentials, IPSwitchInfo
            from app.models.network_port import NetworkPort
            from app.models.device import Device
            from app.models.cabinet import Cabinet
            from app.models.room import Room
            from app.models.switch_route import IPNetwork
            from app.models.ip_model import IPManager
            from sqlalchemy import func as sa_func

            port_rows = (
                self.session.query(
                    NetworkPort.port_name.label("port"),
                    NetworkPort.device_id.label("switch_id"),
                    NetworkPort.link_status.label("port_status"),
                    Device.device_name.label("switch_name"),
                    SwitchCredentials.ip.label("switch_ip"),
                    Room.name.label("room_name"),
                    Room.id.label("room_id"),
                )
                .join(SwitchCredentials, NetworkPort.device_id == SwitchCredentials.device_id)
                .join(Device, SwitchCredentials.device_id == Device.id)
                .join(Cabinet, Device.cabinet_id == Cabinet.id)
                .join(Room, Cabinet.room_id == Room.id)
                .filter(NetworkPort.customer_id == customer_id)
                .order_by(Room.name, Device.device_name, NetworkPort.port_name)
                .all()
            )

            switch_ids_with_ports: set = set()
            result = {}
            for port in port_rows:
                room_name = str(port.room_name or "")
                switch_id = port.switch_id
                port_status = port.port_status or ""

                if room_name not in result:
                    result[room_name] = {"ports": [], "ip_networks": []}

                status_display = "开启" if port_status.lower() == "up" else "关闭"
                result[room_name]["ports"].append(
                    {
                        "port_name": str(port.port or ""),
                        "port_status": status_display,
                        "switch_name": str(port.switch_name or ""),
                        "switch_ip": str(port.switch_ip or ""),
                    }
                )
                if switch_id:
                    switch_ids_with_ports.add(switch_id)

            networks = []
            if switch_ids_with_ports:
                network_rows = (
                    self.session.query(
                        IPNetwork.network,
                        IPNetwork.customer_id.label("network_customer_id"),
                        Device.device_name.label("switch_name"),
                        SwitchCredentials.ip.label("switch_ip"),
                        Room.name.label("room_name"),
                        Cabinet.room_id.label("room_id"),
                        Device.id.label("switch_id"),
                        IPNetwork.port,
                    )
                    .join(Device, IPNetwork.switch_id == Device.id)
                    .join(Cabinet, Device.cabinet_id == Cabinet.id)
                    .join(Room, Cabinet.room_id == Room.id)
                    .filter(Device.id.in_(switch_ids_with_ports))
                    .filter(IPNetwork.customer_id == customer_id)
                    .order_by(Room.name, Device.device_name, IPNetwork.network)
                    .all()
                )
                networks = [
                    {
                        "ip_network": r.network,
                        "network_customer_id": r.network_customer_id,
                        "switch_name": r.switch_name,
                        "switch_ip": r.switch_ip,
                        "room_name": r.room_name,
                        "room_id": r.room_id,
                        "switch_id": r.switch_id,
                        "port": r.port,
                    }
                    for r in network_rows
                ]

            all_ip_rows = (
                self.session.query(
                    IPManager.ip_address,
                    IPManager.customer_id,
                    IPManager.status,
                    IPManager.room_id,
                )
                .filter(IPManager.customer_id.isnot(None))
                .order_by(IPManager.ip_address)
                .all()
            )

            customer_direct_ip_rows = (
                self.session.query(
                    IPManager.ip_address,
                    IPManager.status,
                    IPManager.room_id,
                )
                .filter(IPManager.customer_id == customer_id)
                .order_by(IPManager.ip_address)
                .all()
            )

            ip_switch_rows = []
            if switch_ids_with_ports:
                ip_switch_rows = (
                    self.session.query(
                        IPSwitchInfo.ip_address,
                        Device.device_name.label("switch_name"),
                        SwitchCredentials.ip.label("switch_ip"),
                        Room.name.label("room_name"),
                        IPSwitchInfo.switch_id,
                        IPSwitchInfo.room_id,
                    )
                    .join(SwitchCredentials, IPSwitchInfo.switch_id == SwitchCredentials.device_id)
                    .join(Device, SwitchCredentials.device_id == Device.id)
                    .join(Cabinet, Device.cabinet_id == Cabinet.id)
                    .join(Room, Cabinet.room_id == Room.id)
                    .filter(IPSwitchInfo.switch_id.in_(switch_ids_with_ports))
                    .all()
                )

            ip_status_rows = (
                self.session.query(
                    IPManager.status,
                    sa_func.count(sa_func.distinct(IPManager.ip_address)).label("count"),
                    IPManager.room_id,
                    IPManager.ip_int,
                )
                .filter(IPManager.customer_id == customer_id)
                .group_by(IPManager.status, IPManager.room_id)
                .all()
            )

            return {
                "port_rows": port_rows,
                "networks": networks,
                "all_ip_rows": all_ip_rows,
                "customer_direct_ip_rows": customer_direct_ip_rows,
                "ip_switch_rows": ip_switch_rows,
                "ip_status_rows": ip_status_rows,
                "switch_ids_with_ports": switch_ids_with_ports,
                "result": result,
            }

        except SQLAlchemyError as e:
            self.logger.error(f"获取客户交换机端口数据失败 (customer_id={customer_id}): {e}")
            raise QueryExecutionError(f"获取客户交换机端口数据失败", original_error=e)

    def find_id_name_map_by_ids(self, customer_ids: set[int]) -> Dict[int, str]:
        if not customer_ids:
            return {}
        try:
            rows = (
                self._base_query().with_entities(Customer.id, Customer.customer_name)
                .filter(Customer.id.in_(customer_ids))
                .all()
            )
            return {r[0]: r[1] for r in rows}
        except SQLAlchemyError as e:
            self.logger.error(f"批量查询客户ID→名称映射失败: {e}")
            raise QueryExecutionError("批量查询客户ID→名称映射失败", original_error=e)
