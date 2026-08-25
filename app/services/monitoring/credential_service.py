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
    """规范化为稳定字符串（键排序、ensure_ascii=False），供 SHA-256 去重用。"""
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
        """仅创建共享凭据（不关联设备），供 post_credentials 路由在无 device_ids 时调用。

        P1 修复：把原路由层直接 encrypt + 访问私有 _payload_hash 的逻辑下沉到服务层，
        路由层不再绕过服务封装。返回新建/复用的 MonitorCredential。
        """
        encrypted = encrypt(json.dumps(payload, ensure_ascii=False))
        return self._repo.create_or_reuse_credential(
            protocol, encrypted, _payload_hash(payload), name, strict_name_conflict=True
        )

    @staticmethod
    def _merge_payload(
        old_payload: dict, partial_payload: dict
    ) -> tuple[dict, List[str]]:
        """解密旧值 → 合并部分更新 → 返回 (merged, updated_fields)。

        - 字段有值（非 None）：覆盖（值相同则不计为变更）
        - 字段为 None：清空该键（键不存在则不计为变更）
        - 字段未传：保持不变
        """
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
        """按【设备】维度部分更新凭据密文（P0-2 设备级编辑）。

        语义：只影响 `device_id` 这一台设备，其余共享该凭据的设备保持不变。
        解密旧值 → 合并 → 复用 upsert 的「按 hash 新建/复用 + 迁移关联」原语，
        但仅把当前设备从旧共享凭据迁移到新凭据，并对当前设备 mark_stale。
        不直接改写共享凭据行，避免静默影响其它设备。

        Returns:
            (updated_fields, credential_migrated, new_credential_id, protocol)
            credential_migrated: 本次是否触发了「迁移到新凭据行」（hash 与其它设备不同）
            new_credential_id: 迁移后本设备实际关联的凭据 id（旧行可能已被 GC）
            protocol: 凭据协议（避免调用方二次查询）
        """
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
        """按【共享凭据】维度部分更新密文（P0-2 凭据管理页编辑）。

        语义：影响所有关联设备（共享凭据的本质）。解密旧值 → 合并 → 新建/复用
        新凭据 → 把【全部】关联设备从旧凭据迁移到新凭据 → 全部 mark_stale。
        前端须显式提示「此操作将影响 N 台设备」。

        Returns:
            (updated_fields, credential_migrated, new_credential_id, protocol)
        """
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
        """返回某凭据的非敏感字段（编辑弹窗预填用）。不存在/解密失败返回空 dict。

        优先使用 encrypted_payload 直接解密（避免 N+1：list_credentials 已返回密文，
        无需再 find_by_id）。缺省时按 credential_id 查询（向后兼容）。
        """
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
        """按【凭据】维度配置/更新监控凭据，并传播到所有共享该凭据的设备。

        共享凭据语义（设计如此，勿删）：一份共享凭据（相同明文 hash）关联多台设备时，
        「一处改密 = 全部更新」——本方法会把旧共享凭据的**所有**关联设备一起迁移到新凭据
        （L188-196），保证真正共享同一密码的设备始终一致。

        单台设备的密码编辑（不想影响其它共享设备）应走 `update_payload()`
        （PUT .../payload 端点），它仅把当前设备从共享凭据迁移出去、其余设备不变。
        两者分工：upsert=共享凭据级编辑（传播）；update_payload=设备级编辑（隔离）。

        注意 P20 审查结论：原报告「upsert 传播过激进」为误读——传播是预期共享语义，
        正确的单设备入口是 update_payload，不是删除 upsert 的传播逻辑。
        """
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
        """解除设备与 keep_protocol 以外协议的凭据关联。

        一台设备同一时刻只用一种监控协议，切换协议时旧协议关联必须清理，
        否则 _select_adapter（对 server 类型优先试 Redfish）仍会走旧协议。

        仅解除关联，不删除凭据行——共享凭据是全局资源，即使当前无设备引用
        也应保留，用户可能后续关联其他设备。

        协议切换时同步清空 Device.metric_template_group_id：模板组按协议绑定，
        旧协议的模板组对新协议无意义，保留会导致监控数据页展示旧协议指标。
        用户可在新协议下手动重新绑定模板组。
        """
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
        """把设备关联到已存在的共享凭据（不改动凭据密文）。

        与 `upsert` 的区别：这里不新建或修改凭据，仅建立关联并把关联
        设备的旧监控快照标记失效，迫使下一轮探测用该共享凭据覆盖。
        同时为尚无状态记录的设备创建初始快照，使其立即出现在监控总览中。

        一台设备同一时刻只用一种监控协议，关联新协议前先清理旧协议关联。
        """
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
        """共享凭据是否存在（I14：route handler 不再直访 repo）。"""
        return self._repo.find_by_id(credential_id) is not None

    def linked_device_ids(self, credential_id: int) -> list:
        """共享凭据关联的设备 id 列表。"""
        return self._repo.linked_device_ids(credential_id)

    def patch_credential(self, credential_id: int, enabled: bool = None, name: str = None) -> None:
        """更新共享凭据启用状态 / 名称（不触及密文）。"""
        self._repo.update_credential(credential_id, enabled=enabled, name=name)

    def delete_shared_credential(self, credential_id: int) -> None:
        """删除共享凭据（调用方须先确认无关联设备）。"""
        self._repo.delete_credential(credential_id)

    def get_credential_protocol(self, credential_id: int) -> Optional[str]:
        """获取共享凭据的 protocol（供 payload 更新响应回填）。"""
        cred = self._repo.find_by_id(credential_id)
        return cred.protocol if cred else None

    def linked_devices_detail(self, credential_id: int) -> list:
        """共享凭据关联的设备详情列表。"""
        return self._repo.linked_devices_detail(credential_id)

    def device_exists(self, device_id: int) -> bool:
        """设备是否存在（跨资源边界检查，供 route handler 使用）。"""
        from app.persistence.device_repository import DeviceRepository
        return DeviceRepository().find_by_id(device_id) is not None


def list_credentials() -> list:
    """返回共享凭据列表（含 payload_meta，剔除密文）。

    P1-1：读路径下沉 service，路由层不再直访 repository。
    """
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
