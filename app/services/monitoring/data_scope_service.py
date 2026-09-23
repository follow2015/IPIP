# -*- coding: utf-8 -*-
"""G6 数据范围服务（完整实现）

按 Role.data_scope 通知组模式隔离设备可见集，支撑：
1. 监控 list 端点注入可见设备过滤（get_visible_device_ids）
2. SSE 监控告警 target_user_ids 反查（get_users_with_device_access）

scope_mode 策略：
- all: 可见全部设备（admin / 监控管理角色默认）
- responsible_person: 仅可见 Device.responsible_person = 自己 的设备
- room: 可见 data_scope_config["room_ids"] 机房的设备
- custom: 可见 data_scope_config["device_ids"] 的设备

缓存：用户→可见设备集 + 设备→可见用户集，TTL 5 分钟。
注意：本服务只读 DB，不修改任何状态。


`None` 在本服务里是「**无限制**（data_scope=all 或任一角色豁免）」的**合法取值**。
因此**故障绝不能也返回 `None`** —— 两者一旦不可区分，「鉴权服务不可用」就静默
退化成「全放行」，受限用户在 DB 抖动期间拿到全量设备与拓扑可见性。
本缺陷已被登记三次（`2026-09-08` 复核文档、`IPIP-仓库增量评审报告-32cd10f`
P0-1），收口方式：

1. **依赖故障** ⇒ 抛 `DataScopeUnavailableError`（**不再** `return None`），
   由调用方显式选择放行或拒绝；
2. **未知 `role.data_scope`** ⇒ 空集（最小权限，**不再**回落无限制）；
3. 故障**不写缓存**（避免把故障态固化 5 分钟）。

[WARN] 反面教材：把 `get_visible_device_ids` 整体打桩成抛异常，测的是「调用方的
except 分支写得对不对」，**绕过了本服务内部的吞异常点** ⇒ 全绿也证明不了根因已修。
详见 `tests/test_data_scope_fault_contract.py` 的「注入深度」说明。
"""
from app.utils.logging import get_logger
import threading
import time
from typing import List, Optional, Set

from app.persistence.device_repository import DeviceRepository
from app.persistence.rbac_repository import RoleRepository, PermissionRepository


class DataScopeUnavailableError(RuntimeError):
    """数据域服务不可用：可见集无法判定（内部依赖故障）。

    仓内同款惯用法见 `app/services/ai/task_idempotency.IdempotencyUnavailableError`
    —— 故障信号用**专用异常**表达，使调用方无法在不知情的情况下把它当作正常值
    （这里的"正常值"就是 `None` = 无限制）。
    """


logger = get_logger(__name__)

MONITOR_VIEW_PERMISSION = "monitor:view"
_CACHE_TTL = 300  # 5 分钟

_visible_devices_cache: dict = {}  # user_id → (set[int] | None, ts)
_users_with_device_cache: dict = {}  # device_id → (list[int], ts)
_cache_lock = threading.Lock()

_device_repo = DeviceRepository()
_role_repo = RoleRepository()
_permission_repo = PermissionRepository()


def _now() -> float:
    return time.time()


def _get_user_roles(user_id: int) -> List:
    """获取用户的所有启用角色"""
    return _role_repo.find_active_roles_by_user(user_id)


def _resolve_visible_by_role(role, user_id: int) -> Optional[Set[int]]:
    """按单个角色的 data_scope 解析可见设备集。

    返回 None 表示该角色无限制（all），返回 set 表示受限。
    """
    scope = role.data_scope or "all"
    config = role.data_scope_config or {}

    if scope == "all":
        return None  # 无限制

    if scope == "responsible_person":
        return set(_device_repo.find_ids_by_responsible_person(user_id))

    if scope == "room":
        room_ids = config.get("room_ids") or []
        if not room_ids:
            return set()
        return set(_device_repo.find_ids_by_room_ids(room_ids))

    if scope == "custom":
        device_ids = config.get("device_ids") or []
        return set(device_ids)

    logger.error(
        "data_scope 未知取值，按最小权限处理 role=%s scope=%r",
        getattr(role, "id", None), scope,
    )
    return set()


def get_visible_device_ids(user_id: int) -> Optional[Set[int]]:
    """解析用户可见的设备 ID 集合。

    返回 None 表示无限制（data_scope=all 或任一角色豁免）。
    返回 set 表示受限（仅可见这些设备）。
    多角色取并集；任一角色为 all 则整体无限制。

    Raises:
        DataScopeUnavailableError: 内部依赖故障，可见集**无法判定**。
            调用方必须显式选择放行（`except → True/None`）或拒绝；**不得**忽略。
    """
    with _cache_lock:
        cached = _visible_devices_cache.get(user_id)
        if cached and cached[1] > _now():
            return cached[0]

    try:
        roles = _get_user_roles(user_id)
        if not roles:
            result: Optional[Set[int]] = set()
        else:
            merged: Optional[Set[int]] = set()
            for role in roles:
                visible = _resolve_visible_by_role(role, user_id)
                if visible is None:
                    merged = None  # 任一角色 all → 无限制
                    break
                if merged is not None:
                    merged |= visible
            result = merged
        with _cache_lock:
            _visible_devices_cache[user_id] = (result, _now() + _CACHE_TTL)
        return result
    except Exception as exc:
        logger.error(
            "data_scope 解析失败（fail-closed 信号，交由调用方裁决放行/拒绝）"
            " user_id=%s: %s",
            user_id, exc, exc_info=True,
        )
        raise DataScopeUnavailableError(
            f"数据域服务不可用，无法判定用户 {user_id} 的可见设备集"
        ) from exc


def get_users_with_device_access(device_id: int) -> List[int]:
    """反查能访问该设备的用户 id 列表（供 G1 target_user_ids）。

    按各用户的 data_scope 判定是否可见该设备，任一角色可见即命中。

    返回 `[]` 表示「**无人有权接收**」。[WARN] 调用方**不得**把 `[]` 归一成 `None`：
    网关口径（`realtime_gateway/redis_bus.py`）里 `None` = 全局广播 ⇒ 归一即
    「无权限者」静默升级为「跨数据域全量投递」（见 `alert_ingress` 的固化用例）。
    """
    with _cache_lock:
        cached = _users_with_device_cache.get(device_id)
        if cached and cached[1] > _now():
            return cached[0]

    try:
        user_ids: Set[int] = set()

        responsible = _device_repo.find_responsible_person_by_id(device_id)
        if responsible:
            user_ids.add(responsible)

        monitor_user_ids = _permission_repo.find_user_ids_by_permission_code(
            MONITOR_VIEW_PERMISSION
        )
        for uid in monitor_user_ids:
            try:
                visible = get_visible_device_ids(uid)
            except DataScopeUnavailableError as exc:
                logger.error(
                    "data_scope 故障：接收人本次不可判定，跳过 uid=%s device_id=%s: %s",
                    uid, device_id, exc,
                )
                continue
            if visible is None or device_id in visible:
                user_ids.add(uid)

        result = sorted(user_ids)
        with _cache_lock:
            _users_with_device_cache[device_id] = (result, _now() + _CACHE_TTL)
        return result
    except Exception as exc:
        logger.warning(
            "data_scope 反查设备可见用户失败 device_id=%s: %s",
            device_id, exc,
        )
        return []


def invalidate_cache(user_id: Optional[int] = None, device_id: Optional[int] = None):
    """失效缓存（角色/责任人/机房变更时调用）"""
    with _cache_lock:
        if user_id is not None:
            _visible_devices_cache.pop(user_id, None)
        if device_id is not None:
            _users_with_device_cache.pop(device_id, None)
        if user_id is None and device_id is None:
            _visible_devices_cache.clear()
            _users_with_device_cache.clear()
