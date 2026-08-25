# -*- coding: utf-8 -*-
"""MonitorCredential 仓储（共享凭据 + 关联解析）

凭据密文永远不对外回显。

复用去重键为 `(protocol, payload_hash)`，其中 `payload_hash` 是明文 payload
规范化 JSON 的 SHA-256（见 `app/services/monitoring/credential_service`）。
密文 `encrypted_payload` 因 AES-256-GCM 每次 nonce 不同，不可作为去重键。
"""
import json
from typing import List, Optional

from sqlalchemy import case, func, or_

from app.models.device_monitor_status import DeviceMonitorStatus
from app.models.monitor_credential import DeviceMonitorCredential, MonitorCredential
from app.persistence.base import SQLAlchemyRepository
from app.utils.security.encryption import decrypt


class MonitorCredentialRepository(SQLAlchemyRepository):
    def __init__(self, session=None):
        super().__init__(MonitorCredential, session)

    def create_or_reuse_credential(
        self,
        protocol: str,
        encrypted_payload: str,
        payload_hash: str,
        name: str,
        strict_name_conflict: bool = False,
    ) -> MonitorCredential:
        existing = (
            self.session.query(MonitorCredential)
            .filter(
                MonitorCredential.protocol == protocol,
                MonitorCredential.payload_hash == payload_hash,
            )
            .order_by(MonitorCredential.id)
            .first()
        )
        if existing is not None:
            if strict_name_conflict and name and existing.name and name != existing.name:
                from app.exceptions.business import ResourceConflictError
                raise ResourceConflictError(
                    resource_type="MonitorCredential",
                    resource_id=name,
                    conflict_reason=(
                        f"该协议下已存在明文相同的凭据，名称为 '{existing.name}'（id={existing.id}），"
                        f"请直接关联该凭据或更换明文"
                    ),
                )
            if name and not existing.name:
                existing.name = name
            return existing
        name_conflict = (
            self.session.query(MonitorCredential)
            .filter(MonitorCredential.protocol == protocol, MonitorCredential.name == name)
            .first()
        )
        if name_conflict is not None:
            from app.exceptions.business import ResourceConflictError
            raise ResourceConflictError(
                resource_type="MonitorCredential",
                resource_id=name,
                conflict_reason=f"协议 {protocol} 下已存在同名凭据",
            )
        cred = MonitorCredential(
            protocol=protocol,
            encrypted_payload=encrypted_payload,
            payload_hash=payload_hash,
            name=name,
            enabled=True,
        )
        self.session.add(cred)
        try:
            with self.session.begin_nested():
                self.session.flush()
        except Exception as exc:
            from sqlalchemy.exc import IntegrityError
            if isinstance(exc, IntegrityError):
                existing = (
                    self.session.query(MonitorCredential)
                    .filter(
                        MonitorCredential.protocol == protocol,
                        MonitorCredential.payload_hash == payload_hash,
                    )
                    .order_by(MonitorCredential.id)
                    .first()
                )
                if existing is not None:
                    if name and not existing.name:
                        existing.name = name
                    return existing
            raise
        return cred

    def link(self, credential_id: int, device_id: int) -> None:
        exists = (
            self.session.query(DeviceMonitorCredential)
            .filter_by(credential_id=credential_id, device_id=device_id)
            .first()
        )
        if exists is None:
            self.session.add(
                DeviceMonitorCredential(credential_id=credential_id, device_id=device_id)
            )
        self.session.flush()

    def unlink(self, credential_id: int, device_id: int) -> None:
        self.session.query(DeviceMonitorCredential).filter_by(
            credential_id=credential_id, device_id=device_id
        ).delete(synchronize_session=False)
        self.session.flush()

    def linked_device_ids(self, credential_id: int) -> List[int]:
        return [
            r[0]
            for r in self.session.query(DeviceMonitorCredential.device_id)
            .filter_by(credential_id=credential_id)
            .all()
        ]

    def linked_devices_detail(self, credential_id: int) -> List[dict]:
        from app.models.device import Device
        from app.models.device_hardware import DeviceHardware

        display_ip = func.coalesce(
            case(
                (Device.device_type == "server", DeviceHardware.ipmi_address),
                else_=Device.management_ip,
            ),
            Device.management_ip,
        )

        rows = (
            self.session.query(
                Device.id,
                Device.device_name,
                Device.device_type,
                display_ip.label("management_ip"),
            )
            .join(
                DeviceMonitorCredential,
                DeviceMonitorCredential.device_id == Device.id,
            )
            .outerjoin(DeviceHardware, DeviceHardware.device_id == Device.id)
            .filter(DeviceMonitorCredential.credential_id == credential_id)
            .order_by(Device.device_name)
            .all()
        )
        return [
            {"device_id": r.id, "device_name": r.device_name,
             "device_type": r.device_type, "management_ip": r.management_ip}
            for r in rows
        ]

    def delete_credential(self, credential_id: int) -> None:
        self.session.query(MonitorCredential).filter_by(id=credential_id).delete(
            synchronize_session=False
        )
        self.session.flush()

    def update_credential(
        self, credential_id: int, enabled: Optional[bool] = None, name: Optional[str] = None,
    ) -> Optional[MonitorCredential]:
        cred = self.find_by_id(credential_id)
        if cred is None:
            return None
        if enabled is not None:
            cred.enabled = enabled
        if name is not None:
            cred.name = name
        self.session.flush()
        return cred

    def find_enabled_device_ids(
        self, protocols: List[str], monitor_enabled_only: bool = False
    ) -> List[int]:
        if not protocols:
            return []
        from app.models.device import Device
        q = (
            self.session.query(DeviceMonitorCredential.device_id)
            .join(
                MonitorCredential,
                MonitorCredential.id == DeviceMonitorCredential.credential_id,
            )
            .outerjoin(
                Device,
                Device.id == DeviceMonitorCredential.device_id,
            )
            .filter(
                MonitorCredential.enabled.is_(True),
                MonitorCredential.protocol.in_(protocols),
                or_(
                    Device.id.is_(None),
                    Device.deleted_at.is_(None),
                ),
            )
        )
        if monitor_enabled_only:
            q = (
                q.outerjoin(
                    DeviceMonitorStatus,
                    DeviceMonitorStatus.device_id == DeviceMonitorCredential.device_id,
                )
                .filter(
                    or_(
                        DeviceMonitorStatus.monitor_enabled.is_(True),
                        DeviceMonitorStatus.id.is_(None),
                    )
                )
            )
        rows = q.distinct().all()
        return [r[0] for r in rows]

    def find_enabled_device_ids_all(
        self, monitor_enabled_only: bool = False
    ) -> List[int]:
        from app.models.device import Device

        q = self.session.query(Device.id).filter(Device.deleted_at.is_(None))
        if monitor_enabled_only:
            q = (
                q.outerjoin(
                    DeviceMonitorStatus,
                    DeviceMonitorStatus.device_id == Device.id,
                )
                .filter(
                    or_(
                        DeviceMonitorStatus.monitor_enabled.is_(True),
                        DeviceMonitorStatus.id.is_(None),
                    )
                )
            )
        rows = q.all()
        return [r[0] for r in rows]

    def find_by_id(self, credential_id: int) -> Optional[MonitorCredential]:
        return (
            self.session.query(MonitorCredential)
            .filter(MonitorCredential.id == credential_id)
            .first()
        )

    def find_enabled(self, device_id: int, protocol: str) -> Optional[MonitorCredential]:
        return (
            self.session.query(MonitorCredential)
            .join(
                DeviceMonitorCredential,
                DeviceMonitorCredential.credential_id == MonitorCredential.id,
            )
            .filter(
                DeviceMonitorCredential.device_id == device_id,
                MonitorCredential.protocol == protocol,
                MonitorCredential.enabled.is_(True),
            )
            .first()
        )

    def find_enabled_protocols(self, device_id: int) -> List[str]:
        rows = (
            self.session.query(MonitorCredential.protocol)
            .join(
                DeviceMonitorCredential,
                DeviceMonitorCredential.credential_id == MonitorCredential.id,
            )
            .filter(
                DeviceMonitorCredential.device_id == device_id,
                MonitorCredential.enabled.is_(True),
            )
            .distinct()
            .all()
        )
        return [r[0] for r in rows]

    def get_decrypted(self, device_id: int, protocol: str) -> Optional[dict]:
        cred = self.find_enabled(device_id, protocol)
        if not cred:
            return None
        return json.loads(decrypt(cred.encrypted_payload))

    def list_credentials(self) -> List[dict]:
        count_subq = (
            self.session.query(
                DeviceMonitorCredential.credential_id,
                func.count(DeviceMonitorCredential.device_id).label("linked_count"),
            )
            .group_by(DeviceMonitorCredential.credential_id)
            .subquery()
        )
        rows = (
            self.session.query(
                MonitorCredential.id,
                MonitorCredential.name,
                MonitorCredential.protocol,
                MonitorCredential.enabled,
                MonitorCredential.encrypted_payload,
                func.coalesce(count_subq.c.linked_count, 0),
            )
            .outerjoin(count_subq, MonitorCredential.id == count_subq.c.credential_id)
            .order_by(MonitorCredential.id)
            .all()
        )
        result = []
        for cid, name, protocol, enabled, encrypted_payload, count in rows:
            result.append(
                {
                    "id": cid,
                    "name": name,
                    "protocol": protocol,
                    "enabled": enabled,
                    "encrypted_payload": encrypted_payload,
                    "linked_count": count,
                }
            )
        return result
