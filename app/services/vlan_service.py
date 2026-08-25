# -*- coding: utf-8 -*-
"""
VLAN服务模块

提供VLAN资源池管理的业务逻辑，通过 Repository 访问数据，不直接操作 ORM/DB。
"""
from app.utils.logging import get_logger
from typing import Optional, Dict, List

from app.models.vlan import VLAN
from app.persistence.vlan_repository import VLANRepository, VLANPortMemberRepository
from app.persistence.switch_port_repository import NetworkPortRepository
from app.exceptions.validation import ValidationError

logger = get_logger(__name__)


class VLANService:

    def __init__(self, repo: VLANRepository, vpm_repo: VLANPortMemberRepository = None, port_repo=None):
        self.repo = repo
        self.vpm_repo = vpm_repo or VLANPortMemberRepository()
        self.port_repo = port_repo or NetworkPortRepository()

    def get_all(self) -> List[VLAN]:
        return self.repo.find_all(order_by='vlan_id')

    def get_by_id(self, vlan_id: int) -> Optional[VLAN]:
        return self.repo.find_by_id(vlan_id)

    def get_paginated(self, page: int = 1, per_page: int = 20, **filters) -> dict:
        return self.repo.paginate(page=page, page_size=per_page, filters=filters, order_by='vlan_id')

    def create(self, data: Dict) -> VLAN:
        device_id = data.get('device_id')
        if not device_id:
            raise ValidationError("创建 VLAN 必须指定所属设备 (device_id)")

        existing = self.repo.find_by_device_and_vlan_id(device_id, data['vlan_id'])
        if existing:
            raise ValidationError(f"设备上 VLAN {data['vlan_id']} 已存在")

        if not data.get('room_id'):
            data['room_id'] = self._derive_room_id(device_id)

        return self.repo.create(data)

    def _derive_room_id(self, device_id: int) -> Optional[int]:
        from app.models.device import Device
        device = self.repo.session.query(Device).filter_by(id=device_id).first()
        if device and device.cabinet_id:
            from app.models.cabinet import Cabinet
            cabinet = self.repo.session.query(Cabinet).filter_by(id=device.cabinet_id).first()
            if cabinet and cabinet.room_id:
                return cabinet.room_id
        return None

    def update(self, vlan_id: int, data: Dict) -> VLAN:
        vlan = self.repo.find_by_id(vlan_id)
        if not vlan:
            raise ValidationError("VLAN不存在")
        return self.repo.update(vlan_id, data)

    def delete(self, vlan_id: int) -> bool:
        vlan = self.repo.find_by_id(vlan_id)
        if vlan and vlan.vlan_id:
            self.port_repo.clear_vlan_by_device_and_vlan(vlan.device_id, str(vlan.vlan_id))
        return self.repo.delete(vlan_id)


    def update_members_manual(self, vlan_db_id: int, port_ids: list) -> None:
        from app.models.vlan_port_member import VLANPortMember

        vlan = self.repo.find_by_id(vlan_db_id)
        if not vlan:
            return

        old_members = self.vpm_repo.find_by_vlan_id(vlan_db_id)
        old_port_ids = [m.port_id for m in old_members]
        if old_port_ids:
            self.port_repo.clear_vlan_by_port_ids_and_vlan(old_port_ids, str(vlan.vlan_id))

        self.vpm_repo.delete_by_vlan_id(vlan_db_id)
        self.repo.session.bulk_insert_mappings(VLANPortMember, [
            {"vlan_id": vlan_db_id, "port_id": pid, "port_mode": "access"}
            for pid in port_ids
        ])

        if port_ids:
            self.port_repo.set_vlan_by_port_ids(port_ids, str(vlan.vlan_id))

        self.repo.session.flush()

    def get_members(self, vlan_db_id: int) -> list:
        members = self.vpm_repo.find_by_vlan_id(vlan_db_id)
        return [m.to_dict() for m in members]

    def get_by_device(self, device_id: int) -> list:
        return self.repo.find_by_device(device_id)

    def ensure_vlan(self, device_id: int, vlan_id: int,
                    name: str = None, room_id: int = None,
                    status: int = 1) -> VLAN:
        existing = self.repo.find_by_device_and_vlan_id(device_id, vlan_id)
        if existing:
            if not existing.room_id and room_id:
                existing.room_id = room_id
                self.repo.session.flush()
            return existing
        if room_id is None:
            room_id = self._derive_room_id(device_id)
        data = {
            'device_id': device_id,
            'vlan_id': vlan_id,
            'name': name or f'VLAN{vlan_id}',
            'status': status,
        }
        if room_id is not None:
            data['room_id'] = room_id
        return self.repo.create(data)
