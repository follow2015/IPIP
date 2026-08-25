# -*- coding: utf-8 -*-
"""交换机扩展信息 Repository

提供 SwitchCredentials 表的数据访问方法，
支持按 device_id 查询、upsert、按机房查询、无权限交换机查询。

注意：Phase 3 重构后，原 sw_switch_ext 表已合并到 switch_credentials，
本 Repository 直接操作 SwitchCredentials 模型。
"""
from app.models.switch_credentials import SwitchCredentials
from app.models.device import Device
from app.models.cabinet import Cabinet
from extensions import db


class SwitchExtRepository:

    def get_by_device_id(self, device_id: int) -> SwitchCredentials | None:
        return SwitchCredentials.query.filter_by(device_id=device_id).first()

    get_by_switch_id = get_by_device_id

    def upsert(self, device_id: int, **fields) -> SwitchCredentials:
        import warnings

        device_fields = {}
        for k in ("layer", "switch_role", "uplink_device_id", "core_device_id", "uplink_port_ids"):
            if k in fields:
                device_fields[k] = fields.pop(k)

        _DEPRECATED_MAP = {
            "is_core": "switch_role",
            "uplink_sw_id": "uplink_device_id",
            "core_sw_id": "core_device_id",
        }
        for old_key, new_key in _DEPRECATED_MAP.items():
            if old_key in fields:
                val = fields.pop(old_key)
                warnings.warn(
                    f"SwitchExtRepository.upsert: '{old_key}' is deprecated, use '{new_key}' instead",
                    DeprecationWarning,
                    stacklevel=2,
                )
                if old_key == "is_core":
                    val = 0 if val else 1
                device_fields[new_key] = val

        ext = self.get_by_device_id(device_id)
        if ext is None:
            ext = SwitchCredentials(device_id=device_id)
            db.session.add(ext)
        for k, v in fields.items():
            if hasattr(ext, k):
                setattr(ext, k, v)
        db.session.flush()

        if device_fields and ext.device:
            for k, v in device_fields.items():
                setattr(ext.device, k, v)
            db.session.flush()

        return ext

    def get_all_by_room(self, room_id: int) -> list[SwitchCredentials]:
        return SwitchCredentials.query.join(
            Device, SwitchCredentials.device_id == Device.id
        ).join(
            Cabinet, Device.cabinet_id == Cabinet.id
        ).filter(
            Cabinet.room_id == room_id
        ).all()

    def get_no_auth_switches(self, room_id: int) -> list[SwitchCredentials]:
        return SwitchCredentials.query.join(
            Device, SwitchCredentials.device_id == Device.id
        ).join(
            Cabinet, Device.cabinet_id == Cabinet.id
        ).filter(
            Cabinet.room_id == room_id,
            SwitchCredentials.has_ssh == False,
        ).all()

    def get_no_auth_switches_by_device_ids(self, device_ids: list[int]) -> list[SwitchCredentials]:
        if not device_ids:
            return []
        return SwitchCredentials.query.filter(
            SwitchCredentials.device_id.in_(device_ids),
            SwitchCredentials.has_ssh == False,
        ).all()

    def get_device_name_map_by_ids(self, device_ids: list[int]) -> dict[int, str]:
        if not device_ids:
            return {}
        from sqlalchemy.orm import joinedload
        rows = SwitchCredentials.query.options(
            joinedload(SwitchCredentials.device)
        ).filter(
            SwitchCredentials.device_id.in_(device_ids)
        ).all()
        return {sc.device_id: sc.device.device_name if sc.device else None for sc in rows}

    def get_has_ssh_map(self, device_ids: list[int]) -> dict[int, bool]:
        if not device_ids:
            return {}
        rows = SwitchCredentials.query.filter(
            SwitchCredentials.device_id.in_(device_ids)
        ).all()
        return {sc.device_id: sc.has_ssh for sc in rows}
