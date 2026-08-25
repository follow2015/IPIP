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
    """SwitchCredentials 扩展信息数据访问层

    封装 switch_credentials 表的扩展字段 CRUD 操作，
    与 devices 表 1:1 关联。
    """

    def get_by_device_id(self, device_id: int) -> SwitchCredentials | None:
        """根据 device_id 查询扩展信息

        Args:
            device_id: devices.id（即 switch_credentials.device_id）

        Returns:
            SwitchCredentials | None: 扩展信息记录，不存在返回 None
        """
        return SwitchCredentials.query.filter_by(device_id=device_id).first()

    get_by_switch_id = get_by_device_id

    def upsert(self, device_id: int, **fields) -> SwitchCredentials:
        """创建或更新扩展信息

        若 device_id 对应的记录不存在则创建，存在则更新指定字段。

        字段路由：
        - has_ssh → SwitchCredentials（凭据表）
        - layer, switch_role, uplink_device_id, core_device_id, uplink_port_ids → Device（已迁移）

        注意：is_core / uplink_sw_id / core_sw_id 为旧字段名兼容映射，
        调用方应迁移至 switch_role / uplink_device_id / core_device_id。

        Args:
            device_id: devices.id
            **fields: 需要更新的字段

        Returns:
            SwitchCredentials: 创建或更新后的记录
        """
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
        """获取机房内所有交换机扩展信息

        Args:
            room_id: 机房ID

        Returns:
            list[SwitchCredentials]: 该机房所有交换机的扩展信息列表
        """
        return SwitchCredentials.query.join(
            Device, SwitchCredentials.device_id == Device.id
        ).join(
            Cabinet, Device.cabinet_id == Cabinet.id
        ).filter(
            Cabinet.room_id == room_id
        ).all()

    def get_no_auth_switches(self, room_id: int) -> list[SwitchCredentials]:
        """返回 has_ssh=False 的所有交换机（含 uplink 信息）

        用于降级映射重建，获取所有无 SSH 权限的交换机及其上联信息。

        Args:
            room_id: 机房ID

        Returns:
            list[SwitchCredentials]: 无权限交换机的扩展信息列表
        """
        return SwitchCredentials.query.join(
            Device, SwitchCredentials.device_id == Device.id
        ).join(
            Cabinet, Device.cabinet_id == Cabinet.id
        ).filter(
            Cabinet.room_id == room_id,
            SwitchCredentials.has_ssh == False,
        ).all()

    def get_no_auth_switches_by_device_ids(self, device_ids: list[int]) -> list[SwitchCredentials]:
        """返回指定设备中 has_ssh=False 的所有交换机（含 uplink 信息）

        用于虚拟机房降级映射重建，获取成员中无 SSH 权限的交换机。

        Args:
            device_ids: 设备ID列表

        Returns:
            list[SwitchCredentials]: 无权限交换机的扩展信息列表
        """
        if not device_ids:
            return []
        return SwitchCredentials.query.filter(
            SwitchCredentials.device_id.in_(device_ids),
            SwitchCredentials.has_ssh == False,
        ).all()

    def get_device_name_map_by_ids(self, device_ids: list[int]) -> dict[int, str]:
        """批量查询 SwitchCredentials + Device，返回 device_id -> device_name 映射。"""
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
        """批量获取设备的 has_ssh 映射。

        Args:
            device_ids: 设备ID列表

        Returns:
            dict[int, bool]: device_id → has_ssh 映射
        """
        if not device_ids:
            return {}
        rows = SwitchCredentials.query.filter(
            SwitchCredentials.device_id.in_(device_ids)
        ).all()
        return {sc.device_id: sc.has_ssh for sc in rows}
