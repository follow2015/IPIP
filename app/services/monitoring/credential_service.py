# -*- coding: utf-8 -*-
"""凭据加解密服务（共享凭据 + 关联 + 失效广播）

- 监控凭据为「共享凭据」实体（app/models/monitor_credential.MonitorCredential）：
  protocol + encrypted_payload（AES-256-GCM 密文）+ payload_hash（去重键）+ name + enabled。
- 设备关联经 device_monitor_credentials 多对多表。
- 同一份 (protocol, payload_hash) 凭据被多台设备复用：一处改密，所有关联设备下一轮探测覆盖。
- 凭据变更后对所有关联设备的旧快照 mark_stale，迫使重新探测。
"""
import hashlib
import json
from typing import List, Optional

from app.exceptions.business import BusinessLogicError
from app.utils.logging import get_logger
from app.utils.security.encryption import encrypt, decrypt

logger = get_logger(__name__)
from app.persistence.monitor_credential_repository import MonitorCredentialRepository
from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository


def _canonical_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(_canonical_payload(payload).encode("utf-8")).hexdigest()


class MonitorCredentialService:
    def __init__(self, repo=None, status_repo=None):
        self._repo = repo or MonitorCredentialRepository()
        self._status_repo = status_repo or DeviceMonitorStatusRepository()

    def get_decrypted(self, device_id: int, protocol: str) -> Optional[dict]:
        cred = self._repo.find_enabled(device_id, protocol)
        if not cred:
            return None
        return json.loads(decrypt(cred.encrypted_payload))

    def create_shared_credential(self, protocol: str, payload: dict, name: str):
        encrypted = encrypt(json.dumps(payload, ensure_ascii=False))
        return self._repo.create_or_reuse_credential(
            protocol, encrypted, _payload_hash(payload), name, strict_name_conflict=True
        )

    @staticmethod
    def _merge_payload(
        old_payload: dict, partial_payload: dict
    ) -> tuple[dict, List[str]]:
        merged = dict(old_payload)
        updated_fields: List[str] = []
        for key, new_value in partial_payload.items():
            if new_value is not None:
                if old_payload.get(key) != new_value:
                    merged[key] = new_value
                    updated_fields.append(key)
            elif key in merged:
                del merged[key]
                updated_fields.append(key)
        return merged, updated_fields

    def update_payload(
        self,
        device_id: int,
        credential_id: int,
        partial_payload: dict,
        name: Optional[str] = None,
    ) -> tuple[List[str], bool]:
        cred = self._repo.find_by_id(credential_id)
        if cred is None or device_id not in self._repo.linked_device_ids(credential_id):
            raise BusinessLogicError(f"凭据 {credential_id} 未关联到设备 {device_id}")

        old_payload = json.loads(decrypt(cred.encrypted_payload))
        merged, updated_fields = self._merge_payload(old_payload, partial_payload)
        if not updated_fields:
            return [], False, cred.id, cred.protocol

        encrypted = encrypt(json.dumps(merged, ensure_ascii=False))
        payload_hash = _payload_hash(merged)
        target_name = name or cred.name
        temp_name = f"{target_name}#{cred.id}" if target_name == cred.name else target_name
        new_cred = self._repo.create_or_reuse_credential(
            cred.protocol, encrypted, payload_hash, temp_name
        )
        if new_cred.id == cred.id:
            return updated_fields, False, cred.id, cred.protocol

        self._repo.unlink(cred.id, device_id)
        self._repo.link(new_cred.id, device_id)
        if not self._repo.linked_device_ids(cred.id):
            self._repo.delete_credential(cred.id)
            if temp_name != target_name:
                self._repo.update_credential(new_cred.id, name=target_name)
        self._status_repo.mark_stale(device_id)
        return updated_fields, True, new_cred.id, new_cred.protocol

    def update_shared_payload(
        self,
        credential_id: int,
        partial_payload: dict,
        name: Optional[str] = None,
    ) -> tuple[List[str], bool, int, str]:
        cred = self._repo.find_by_id(credential_id)
        if cred is None:
            raise BusinessLogicError(f"凭据 {credential_id} 不存在")

        old_payload = json.loads(decrypt(cred.encrypted_payload))
        merged, updated_fields = self._merge_payload(old_payload, partial_payload)
        if not updated_fields:
            return [], False, cred.id, cred.protocol

        encrypted = encrypt(json.dumps(merged, ensure_ascii=False))
        payload_hash = _payload_hash(merged)
        target_name = name or cred.name
        temp_name = f"{target_name}#{cred.id}" if target_name == cred.name else target_name
        new_cred = self._repo.create_or_reuse_credential(
            cred.protocol, encrypted, payload_hash, temp_name
        )
        if new_cred.id == cred.id:
            return updated_fields, False, cred.id, cred.protocol

        linked = self._repo.linked_device_ids(cred.id)
        for did in linked:
            self._repo.unlink(cred.id, did)
            self._repo.link(new_cred.id, did)
        self._status_repo.mark_stale_batch(linked)
        if not self._repo.linked_device_ids(cred.id):
            self._repo.delete_credential(cred.id)
        if temp_name != target_name:
            self._repo.update_credential(new_cred.id, name=target_name)
        return updated_fields, True, new_cred.id, new_cred.protocol

    def payload_meta(self, credential_id: int = None, encrypted_payload: str = None) -> dict:
        if encrypted_payload is None:
            cred = self._repo.find_by_id(credential_id)
            if cred is None:
                return {}
            encrypted_payload = cred.encrypted_payload
        try:
            payload = json.loads(decrypt(encrypted_payload))
        except Exception:
            logger.warning("凭据解密失败 credential_id=%s", getattr(cred, "id", None), exc_info=True)
            return {}
        from app.models.monitor_credential import NON_SECRET_KEYS

        meta: dict = {}
        for key, value in payload.items():
            if key in NON_SECRET_KEYS:
                meta[key] = value
        if "community" in payload:
            meta["has_community"] = True
        return meta

    def upsert(self, device_id: int, protocol: str, payload: dict, name: str) -> None:
        encrypted = encrypt(json.dumps(payload, ensure_ascii=False))
        payload_hash = _payload_hash(payload)
        old = self._repo.find_enabled(device_id, protocol)

        self._cleanup_other_protocols(device_id, protocol)

        if old is not None and name == old.name:
            old_linked = self._repo.linked_device_ids(old.id)
            self._repo.delete_credential(old.id)
        else:
            old_linked = None

        cred = self._repo.create_or_reuse_credential(
            protocol, encrypted, payload_hash, name, strict_name_conflict=True
        )
        if old_linked is not None:
            for did in old_linked:
                self._repo.link(cred.id, did)
        elif old is not None and old.id != cred.id:
            for did in self._repo.linked_device_ids(old.id):
                self._repo.unlink(old.id, did)
                self._repo.link(cred.id, did)
            if not self._repo.linked_device_ids(old.id):
                self._repo.delete_credential(old.id)
        else:
            self._repo.link(cred.id, device_id)
        linked_ids = self._repo.linked_device_ids(cred.id)
        self._status_repo.mark_stale_batch(linked_ids)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for did in linked_ids:
            if not self._status_repo.find_by_device(did):
                self._status_repo.upsert(
                    device_id=did,
                    protocol=protocol,
                    reachable=False,
                    ever_reachable=False,
                    down_alerted=False,
                    down_episode=0,
                    consecutive_failures=0,
                    last_checked_at=now,
                    monitor_enabled=True,
                )

    def _cleanup_other_protocols(self, device_id: int, keep_protocol: str) -> None:
        from app.models.device import Device
        from app.models.monitor_credential import DeviceMonitorCredential, MonitorCredential
        other_links = (
            self._repo.session.query(DeviceMonitorCredential, MonitorCredential)
            .join(MonitorCredential, MonitorCredential.id == DeviceMonitorCredential.credential_id)
            .filter(
                DeviceMonitorCredential.device_id == device_id,
                MonitorCredential.protocol != keep_protocol,
                MonitorCredential.enabled.is_(True),
            )
            .all()
        )
        if not other_links:
            return
        for link, cred in other_links:
            self._repo.unlink(cred.id, device_id)
        self._repo.session.query(Device).filter(Device.id == device_id).update(
            {Device.metric_template_group_id: None}, synchronize_session=False
        )
        from app.models.device_metric_latest import DeviceMetricLatest
        self._repo.session.query(DeviceMetricLatest).filter(
            DeviceMetricLatest.device_id == device_id
        ).delete(synchronize_session=False)
        self._repo.session.flush()

    def delete(self, device_id: int, protocol: str) -> None:
        cred = self._repo.find_enabled(device_id, protocol)
        if not cred:
            return
        self._repo.unlink(cred.id, device_id)
        self._status_repo.mark_stale(device_id)

    def link_existing(self, credential_id: int, device_ids: List[int]) -> None:
        cred = self._repo.find_by_id(credential_id)
        for did in device_ids:
            if cred and cred.protocol:
                self._cleanup_other_protocols(did, cred.protocol)
            self._repo.link(credential_id, did)
        self._status_repo.mark_stale_batch(list(device_ids))
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for did in device_ids:
            if not self._status_repo.find_by_device(did):
                self._status_repo.upsert(
                    device_id=did,
                    protocol=cred.protocol if cred else "unknown",
                    reachable=False,
                    ever_reachable=False,
                    down_alerted=False,
                    down_episode=0,
                    consecutive_failures=0,
                    last_checked_at=now,
                    monitor_enabled=True,
                )

    def credential_exists(self, credential_id: int) -> bool:
        return self._repo.find_by_id(credential_id) is not None

    def linked_device_ids(self, credential_id: int) -> list:
        return self._repo.linked_device_ids(credential_id)

    def patch_credential(self, credential_id: int, enabled: bool = None, name: str = None) -> None:
        self._repo.update_credential(credential_id, enabled=enabled, name=name)

    def delete_shared_credential(self, credential_id: int) -> None:
        self._repo.delete_credential(credential_id)

    def get_credential_protocol(self, credential_id: int) -> Optional[str]:
        cred = self._repo.find_by_id(credential_id)
        return cred.protocol if cred else None

    def linked_devices_detail(self, credential_id: int) -> list:
        return self._repo.linked_devices_detail(credential_id)

    def device_exists(self, device_id: int) -> bool:
        from app.persistence.device_repository import DeviceRepository
        return DeviceRepository().find_by_id(device_id) is not None


def list_credentials() -> list:
    from app.persistence.monitor_credential_repository import MonitorCredentialRepository
    credential_repo = MonitorCredentialRepository()
    rows = credential_repo.list_credentials()
    svc = MonitorCredentialService()
    for r in rows:
        try:
            r["payload_meta"] = svc.payload_meta(encrypted_payload=r.get("encrypted_payload"))
        except Exception:
            r["payload_meta"] = {}
        r.pop("encrypted_payload", None)
        r.pop("payload", None)
    return rows
