# -*- coding: utf-8 -*-
"""凭据加解密服务（共享凭据 + 设备绑定 + 失效广播）

- 监控凭据为「共享凭据」实体（app/models/monitor_credential.MonitorCredential）：
  protocol + encrypted_payload（AES-256-GCM 密文）+ payload_hash（去重键）+ name + enabled。
- 设备关联经 device_monitor_credentials 多对多表。
- 同一份 (protocol, payload_hash) 凭据可被多台设备复用。

**两个正交域（勿混，见 docs/design/监控凭据语义分层与入口收敛-20261010.md）**：

- **设备域**（`bind_device` / `update_payload` / `delete` / `link_existing`）：
  只动 `(credential_id, device_id=<本机>)` 这一行的关联；旧行无人引用才 GC；
  只 `mark_stale(本机)`。入口 = 设备详情、批量修改监控。
- **凭据域**（`create_shared_credential` / `update_shared_payload` /
  `patch_credential` / `delete_shared_credential`）：
  可影响该凭据的**全部**关联设备（共享凭据的本质），前端须显式提示影响台数。
  入口 = 凭据中心。

判据：任何「用户以为只影响一台」的入口，落到的必须是设备域。
"""
import hashlib
import json
from typing import List, Optional
from app.utils.time_utils import now_utc_naive

from app.exceptions.business import BusinessLogicError
from app.utils.logging import get_logger
from app.utils.security.encryption import encrypt, decrypt

from app.persistence.monitor_credential_repository import MonitorCredentialRepository
from app.persistence.device_monitor_status_repository import DeviceMonitorStatusRepository
logger = get_logger(__name__)


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
        """读取设备某协议的启用凭据并解密为 payload dict（短事务）。

        P0-MDL（2026-09-04 生产实测）：SELECT 后立即 commit 再返回明文 dict。
        SNMP/Zabbix 等探测可持续分钟级，若凭据事务横跨探测期，
        monitor_credentials 的共享 MDL 会一直被持有，该表的任何 DDL
        （如 0001 清理冗余索引）都拿不到排他锁，表现为 db-upgrade 卡死。
        返回值为纯 dict、无 ORM 对象逃逸，提前提交不引发过期刷新。

        前提：调用时本 session 无未提交写操作——已逐一核对全部调用点
        （monitor_worker._resolve_monitor_credential / monitor_service.
        _select_adapter / monitor_oid、monitor_config 路由），均为探测或
        读取前的只读阶段。
        """
        try:
            cred = self._repo.find_enabled(device_id, protocol)
            if not cred:
                return None
            payload = json.loads(decrypt(cred.encrypted_payload))
        finally:
            self._repo.session.commit()
        return payload

    @staticmethod
    def _enforce_snmp_gate(protocol: str, payload: dict) -> None:
        """SNMP 写入期闸门（安全中心一期强制点②）。

        四条写路径（创建共享 / 设备级部分更新 / 共享级部分更新 / 设备绑定）共用此处 ——
        分散内联 4 份很容易出现"改了 3 处漏 1 处"的静默缺口。

        调用点必须在**合并 partial 之后的完整 payload** 上：只校验增量时，分两次把
        community 改成 `public` 就能绕过（每次单看都不违规）。

        非 SNMP 协议直接放行 —— 闸门只对 SNMP 版本/团体名有意见。
        """
        if protocol != "snmp":
            return
        from app.services.security.snmp_gate import validate_credential
        validate_credential(payload)

    def create_shared_credential(self, protocol: str, payload: dict, name: str):
        """仅创建共享凭据（不关联设备），供 post_credentials 路由在无 device_ids 时调用。

        P1 修复：把原路由层直接 encrypt + 访问私有 _payload_hash 的逻辑下沉到服务层，
        路由层不再绕过服务封装。返回新建/复用的 MonitorCredential。
        """
        self._enforce_snmp_gate(protocol, payload)
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
    ) -> tuple[List[str], bool, int, Optional[str]]:
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
            raise BusinessLogicError(
                f"凭据 {credential_id} 未关联到设备 {device_id}", status_code=404
            )

        old_payload = json.loads(decrypt(cred.encrypted_payload))
        merged, updated_fields = self._merge_payload(old_payload, partial_payload)
        if not updated_fields:
            return [], False, cred.id, cred.protocol

        self._enforce_snmp_gate(cred.protocol, merged)
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
            raise BusinessLogicError(f"凭据 {credential_id} 不存在", status_code=404)

        old_payload = json.loads(decrypt(cred.encrypted_payload))
        merged, updated_fields = self._merge_payload(old_payload, partial_payload)
        if not updated_fields:
            return [], False, cred.id, cred.protocol

        self._enforce_snmp_gate(cred.protocol, merged)
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

    def bind_device(self, device_id: int, protocol: str, payload: dict, name: str) -> int:
        """设备域：为本机绑定监控凭据（整份替换语义）。**只影响本设备**。

        这是「设备详情」与「批量修改监控」两个 UI 入口唯一应有的写入口。
        不变量（设计 `docs/design/监控凭据语义分层与入口收敛-20261010.md` §2.2）：

        - **I1/I3**：只增删 `(cred, device_id=<本机>)` 这一行的关联，
          绝不解绑其它设备、绝不把其它设备迁到新凭据；
        - **I2**：旧凭据行**仅在已无任何关联**时才 GC（唯一合法删除路径）；
        - **I4**：只 `mark_stale(本机)`，不广播；
        - **I5**：不抢占他人的 `name` —— 与旧行同名时先建临时名，
          待旧行腾空被 GC 后再恢复目标名。

        「一处改密 = 全部更新」是**凭据域**语义，入口是 `update_shared_payload()`
        （凭据中心「编辑密文」，UI 已提示「影响 N 台设备」），**不是**本方法。

        历史教训（2026-10-10 事故）：本方法的前身 `upsert` 在改密时会连带把旧凭据的
        **全部**关联设备一起迁走并删除旧行，导致「设备详情页改 1 台 = 实际改 8 台」，
        且 community / 口令明文随行删除而**永久不可恢复**。
        详见 `docs/review/监控凭据全链路评审-20261010.md` P0-1 / P0-3。

        Returns:
            本机最终绑定的 credential_id。
        """
        self._enforce_snmp_gate(protocol, payload)
        encrypted = encrypt(json.dumps(payload, ensure_ascii=False))
        payload_hash = _payload_hash(payload)
        old = self._repo.find_enabled(device_id, protocol)

        self._cleanup_other_protocols(device_id, protocol)

        target_name = name
        if old is not None and name == old.name:
            target_name = f"{name}#{old.id}"

        cred = self._repo.create_or_reuse_credential(
            protocol, encrypted, payload_hash, target_name, strict_name_conflict=True
        )

        if old is not None and old.id != cred.id:
            self._repo.unlink(old.id, device_id)
            if not self._repo.linked_device_ids(old.id):  # I2：无人引用才 GC
                self._repo.delete_credential(old.id)
                if target_name != name:  # I5：名字腾出来了才恢复
                    self._repo.update_credential(cred.id, name=name)

        self._repo.link(cred.id, device_id)
        self._status_repo.mark_stale(device_id)
        if not self._status_repo.find_by_device(device_id):
            self._status_repo.upsert(
                device_id=device_id,
                protocol=protocol,
                reachable=False,
                ever_reachable=False,
                down_alerted=False,
                down_episode=0,
                consecutive_failures=0,
                last_checked_at=now_utc_naive(),
                monitor_enabled=True,
            )
        return cred.id

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
        other_links = self._repo.list_other_protocol_links(device_id, keep_protocol)
        if not other_links:
            return
        for _link, cred in other_links:
            self._repo.unlink(cred.id, device_id)
        from app.persistence.device_repository import DeviceRepository

        DeviceRepository(session=self._repo.session).clear_metric_template_group(device_id)
        from app.persistence.device_metric_latest_repository import (
            DeviceMetricLatestRepository,
        )

        DeviceMetricLatestRepository(
            session=self._repo.session
        ).delete_by_device(device_id)

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
        now = now_utc_naive()
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
        except Exception:  # noqa: BLE001 -- 凭证元数据解析失败降级为空：列表永不回显密文，解析失败不应阻断
            r["payload_meta"] = {}
        r.pop("encrypted_payload", None)
        r.pop("payload", None)
    return rows
