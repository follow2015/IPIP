# -*- coding: utf-8 -*-
"""
机房服务模块

提供机房管理的全部业务逻辑，通过 Repository 访问数据，不直接操作 ORM/DB。
"""
import unicodedata

from sqlalchemy.exc import IntegrityError

from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional, Tuple

from app.exceptions.business import ResourceConflictError
from app.exceptions.data_access import DataAccessError
from app.exceptions.validation import ValidationError
from app.persistence.room_repository import RoomRepository
from app.persistence.cabinet_repository import CabinetRepository
from app.persistence.device_repository import DeviceRepository
from app.persistence.room_channel_repository import RoomChannelRepository
from app.persistence.room_layout_marker_repository import RoomLayoutMarkerRepository
from app.models.room import Room
from app.services.switch_events import emit_resource_change_global
from app.utils.cache import cache_manager

logger = get_logger(__name__)

ROOM_CACHE_TTL = 3600  # 机房基础信息缓存时间（秒）

_GROUPING_FIELDS = ("building", "floor")


_FORCE_DELETE_DEVICE_SCOPED: Tuple[Tuple[str, str], ...] = (
    ("device_asset", "device_id"),
    ("device_config_backups", "device_id"),
    ("device_config_changes", "device_id"),
    ("device_connections", "device_id"),
    ("device_connections", "switch_device_id"),
    ("device_hardware", "device_id"),
    ("device_metric_alert_state", "device_id"),
    ("device_metric_baseline", "device_id"),
    ("device_metric_latest", "device_id"),
    ("device_metric_override", "device_id"),
    ("device_monitor_credentials", "device_id"),
    ("device_monitor_status", "device_id"),
    ("device_monitor_timeseries_daily", "device_id"),
    ("device_monitor_timeseries_hourly", "device_id"),
    ("device_nics_port", "device_id"),
    ("device_server_ext", "device_id"),
    ("device_server_ext", "parent_device_id"),
    ("device_storage", "device_id"),
    ("device_switch_ext", "device_id"),
    ("device_switch_ext", "uplink_device_id"),
    ("device_switch_ext", "core_device_id"),
    ("ip_ban_records", "switch_id"),
    ("ip_networks", "switch_id"),
    ("ip_switch_info", "switch_id"),
    ("link_aggregation_groups", "device_id"),
    ("monitor_alert_dependency_rule", "downstream_device_id"),
    ("monitor_alert_dependency_rule", "upstream_device_id"),
    ("monitor_alert_outbox", "device_id"),
    ("network_connections", "peer_device_id"),
    ("network_connections", "local_device_id"),
    ("network_ports", "device_id"),
    ("switch_credentials", "device_id"),
    ("switch_port_ips", "device_id"),
    ("switch_routes", "switch_id"),
    ("switch_status_cache", "device_id"),
    ("virtual_room_members", "device_id"),
    ("vlans", "device_id"),
)

_FORCE_DELETE_ROOM_SCOPED: Tuple[Tuple[str, str], ...] = (
    ("ip_addresses", "room_id"),
    ("ip_allocation_logs", "room_id"),
    ("ip_ban_records", "room_id"),
    ("ip_networks", "room_id"),
    ("ip_switch_info", "room_id"),
    ("switch_routes", "room_id"),
    ("vlans", "room_id"),
    ("room_channels", "room_id"),
    ("room_layout_markers", "room_id"),
)

_FORCE_DELETE_ALLOWED = frozenset(
    _FORCE_DELETE_DEVICE_SCOPED + _FORCE_DELETE_ROOM_SCOPED
) | {
    ("devices", "cabinet_id"),
    ("cabinets", "room_id"),
    ("rooms", "id"),
}

_FORCE_DELETE_DISPOSED = frozenset(
    {
        ("ai_diagnosis_sessions", "device_id"),
        ("monitor_incident", "root_device_id"),
        ("monitor_suppressed_alert_log", "device_id"),
        ("monitor_suppressed_alert_log", "upstream_device_id"),
    }
)


def _normalize_grouping_value(value: str) -> Optional[str]:
    """归一化单个分组键值：剔除 Cf 格式字符 → NFKC 全半角归一 → 去首尾空白。

    顺序说明：先剔除再归一再 strip——NFKC 会把全角空格（\\u3000）转成普通空格，
    放在 strip 之前可以一并吃掉；Cf 类字符（零宽空格、BOM 等）不属于空白，
    strip 去不掉，必须显式剔除。

    Returns:
        归一化后的值；纯空白/不可见字符输入返回 None。
    """
    cleaned = "".join(ch for ch in value if unicodedata.category(ch) != "Cf")
    normalized = unicodedata.normalize("NFKC", cleaned).strip()
    return normalized or None


def _normalize_grouping_fields(data: Dict[str, Any]) -> None:
    """就地归一化分组键字段（不可见字符剔除 + 全半角归一 + 去首尾空白）；空串归一为 None。

    只在键**存在**时处理，以兼容部分更新（PUT 里没带 building 时不应改动它）。
    大小写不做归一（见 _GROUPING_FIELDS 的已知限制说明）。
    """
    for key in _GROUPING_FIELDS:
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, str):
            data[key] = _normalize_grouping_value(value)


ROOM_SHORT_CACHE_TTL = 600  # 机房统计信息缓存时间（秒）


def _usage_rate(used: int, total: int) -> int:
    """利用率百分比（0-100，四舍五入）。分母为 0（未填容量）时返回 0 而不是抛错。"""
    if total <= 0:
        return 0
    return round(used * 100 / total)


def _raise_position_conflict(error: DataAccessError, conflict_message: str) -> None:
    """把唯一键竞态导致的写入失败还原为可读 409；非唯一键冲突时不做任何事（调用方补 raise）。

    服务层前置校验（find_by_room_and_col 等）与写入之间存在竞态窗口：并发请求
    可能在校验通过后抢先插入同键数据，由数据库唯一约束兜底。基类把 IntegrityError
    包装为 DataAccessError(500)，此处还原为带坐标上下文的 ResourceConflictError(409)，
    避免前端只看到泛化的"创建失败"（代码审查 m3）。
    """
    if not isinstance(getattr(error, "original_error", None), IntegrityError):
        return
    raise ResourceConflictError(
        resource_type="机房位置配置",
        conflict_reason=conflict_message,
        message=f"{conflict_message}，请刷新后重试",
    ) from error


class RoomService:
    """机房服务

    所有业务逻辑入口，统一通过 RoomRepository 访问数据库。
    对外只暴露一套 CRUD 接口，旧的双份方法已合并删除。
    """

    def __init__(self, room_repository: RoomRepository,
                 cabinet_repository: CabinetRepository,
                 device_repository: DeviceRepository,
                 channel_repository: RoomChannelRepository = None,
                 marker_repository: RoomLayoutMarkerRepository = None):
        self.room_repository = room_repository
        self.cabinet_repository = cabinet_repository
        self.device_repository = device_repository
        self.channel_repository = channel_repository or RoomChannelRepository()
        self.marker_repository = marker_repository or RoomLayoutMarkerRepository()



    def get_overview(self) -> List[Dict[str, Any]]:
        """跨机房总览：按机房名称（name）分组返回各机房汇总。

        分组键为 `name`（实施计划《机房房间号与名称分组改造》D5）：同一物理机房
        拆成多条 Room 记录时共用同一名称，总览天然归为一组；楼栋/楼层退出分组、
        仅作筛选维度（rooms 内保留字段）。

        **刻意不缓存**：总览的价值在于"当下"的利用率与状态分布，机房内设备增删改
        会实时改变冗余字段 `used_u` / `used_power`，缓存会让人刚上架完设备却看不到
        数字变化。机房是十几个的量级，两次分组聚合足够便宜。

        数据口径：
        - 机柜数与容量取 `cabinets` 的冗余字段一次性聚合（见
          `CabinetRepository.get_overview_stats_by_room` 的口径说明）；
        - 可见范围与 `list_rooms` 保持一致（都按 `room:view` 权限）。机房级的数据
          权限裁剪现状并不存在于 `list_rooms`，故此处不单方面引入不一致；
          若将来要做机房级 data scope，应与列表接口一并处理。

        Returns:
            [{name, room_count, cabinet_count, u_usage_rate,
              power_usage_rate, rooms: [...]}]
        """
        rooms = self.room_repository.find_all(filters={"status": 0}, order_by="name")
        stats = self.cabinet_repository.get_overview_stats_by_room()

        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for room in rooms:
            s = stats.get(room.id) or {}
            total_u = int(s.get("total_u", 0))
            used_u = int(s.get("used_u", 0))
            total_power = int(s.get("total_power", 0))
            used_power = int(s.get("used_power", 0))
            buckets.setdefault(room.name or "", []).append(
                {
                    "id": room.id,
                    "name": room.name,
                    "room_number": room.room_number,
                    "status": room.status,
                    "location": room.location,
                    "building": room.building,
                    "floor": room.floor,
                    "cabinet_count": int(s.get("cabinet_count", 0)),
                    "u_usage_rate": _usage_rate(used_u, total_u),
                    "power_usage_rate": _usage_rate(used_power, total_power),
                    "status_distribution": s.get("status_counts", {}),
                    "_totals": (used_u, total_u, used_power, total_power),
                }
            )

        ordered = sorted(b for b in buckets if b)
        if "" in buckets:
            ordered.append("")

        groups: List[Dict[str, Any]] = []
        for name_key in ordered:
            entries = buckets[name_key]
            used_u = sum(e["_totals"][0] for e in entries)
            total_u = sum(e["_totals"][1] for e in entries)
            used_power = sum(e["_totals"][2] for e in entries)
            total_power = sum(e["_totals"][3] for e in entries)
            groups.append(
                {
                    "name": name_key or None,
                    "room_count": len(entries),
                    "cabinet_count": sum(e["cabinet_count"] for e in entries),
                    "u_usage_rate": _usage_rate(used_u, total_u),
                    "power_usage_rate": _usage_rate(used_power, total_power),
                    "rooms": [
                        {k: v for k, v in e.items() if k != "_totals"} for e in entries
                    ],
                }
            )
        return groups

    def get_buildings(self) -> List[str]:
        """当前已使用的楼栋去重值（供机房表单的联想选项，设计文档 §2.4）"""
        return self.room_repository.find_distinct_buildings()

    def get_floors(self, building: Optional[str] = None) -> List[str]:
        """当前已使用的楼层去重值（供表单联想与总览页楼层筛选）

        Args:
            building: 限定楼栋。前端在楼栋变更后须重新拉取，否则 A 栋与 B 栋的
                同号楼层会混在一个下拉里（见 repository 层的说明）。
        """
        return self.room_repository.find_distinct_floors(building)

    def get_room_name_options(self) -> List[Dict[str, Any]]:
        """机房名称联想选项 [{name, room_count}]（供表单强联想，实施计划 D3）

        前端据此提示"将并入「X」机房组（现有 N 条记录）"；输入不在选项中的名称
        视为新建机房组，需显式确认。
        """
        return self.room_repository.find_name_options()

    def get_all_rooms(self) -> List[Dict[str, Any]]:
        """获取所有正常状态机房列表（带缓存）

        返回字典列表而非 ORM 对象，因为 Redis 缓存反序列化后无法还原 ORM 对象。
        """
        return cache_manager.get_or_set(
            "room:list:all",
            lambda: [r.to_dict() for r in self.room_repository.find_all(filters={"status": 0}, order_by="name")],
            ttl=ROOM_CACHE_TTL,
        )

    def get_by_id(self, room_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取机房（含停用状态，供存在性检查用，带缓存）

        返回字典而非 ORM 对象，因为 Redis 缓存反序列化后无法还原 ORM 对象。
        """
        room = self.room_repository.find_by_id(room_id)
        return cache_manager.get_or_set(
            f"room:{room_id}",
            lambda: room.to_dict() if room else None,
            ttl=ROOM_CACHE_TTL,
        )

    def get_active_by_id(self, room_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取正常状态的机房（带缓存）

        返回字典而非 ORM 对象，因为 Redis 缓存反序列化后无法还原 ORM 对象。
        """
        room = self.room_repository.find_one({"id": room_id, "status": 0})
        return cache_manager.get_or_set(
            f"room:active:{room_id}",
            lambda: room.to_dict() if room else None,
            ttl=ROOM_CACHE_TTL,
        )

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取正常状态的机房（带缓存）

        返回字典而非 ORM 对象，因为 Redis 缓存反序列化后无法还原 ORM 对象。
        """
        room = self.room_repository.find_one({"name": name, "status": 0})
        return cache_manager.get_or_set(
            f"room:name:{name}",
            lambda: room.to_dict() if room else None,
            ttl=ROOM_CACHE_TTL,
        )

    def get_paginated(
        self,
        page: int = 1,
        per_page: int = 20,
        filters: Optional[Dict] = None,
    ) -> Tuple[List[Room], int]:
        """分页获取机房列表

        Returns:
            (机房列表, 总数)
        """
        result = self.room_repository.paginate(
            filters=filters or {},
            page=page,
            page_size=per_page,
        )
        return result.get("data", []), result.get("total_count", 0)

    def search_rooms(self, keyword: str) -> List[Room]:
        """按关键词搜索机房（匹配名称或位置）"""
        result = self.room_repository.search(
            search_fields=["name", "location"],
            keyword=keyword,
            filters={"status": 0},
        )
        return result.get("data", [])

    def get_room_with_stats(self, room_id: int) -> Optional[Dict[str, Any]]:
        """获取机房详情 + 统计信息（机柜数、交换机数，带缓存）"""
        return cache_manager.get_or_set(
            f"room:stats:{room_id}",
            lambda: self._load_room_with_stats(room_id),
            ttl=ROOM_SHORT_CACHE_TTL,
        )

    def _load_room_with_stats(self, room_id: int) -> Optional[Dict[str, Any]]:
        """从数据库加载机房详情+统计（内部方法）"""
        room = self.room_repository.find_one({"id": room_id, "status": 0})
        if not room:
            return None

        room_dict = room.to_dict()
        room_dict.update(self.room_repository.get_room_statistics(room_id))
        return room_dict

    def get_cabinets(self, room_id: int) -> List:
        """获取机房下的所有机柜"""
        return self.cabinet_repository.find_by_room_id(room_id)


    def get_channels(self, room_id: int) -> List:
        """获取机房全部通道（按列号升序）"""
        return self.channel_repository.find_by_room_id(room_id)

    def create_channel(self, room_id: int, data: Dict[str, Any]):
        """新增通道配置

        Raises:
            ValidationError: 该列位已存在通道配置（唯一键 uk_room_col_channel）
            ResourceConflictError: 竞态下唯一约束兜底命中（HTTP 409，带列位信息）
        """
        col_number = data.get("col_number")
        if self.channel_repository.find_by_room_and_col(room_id, col_number):
            raise ValidationError(f"第 {col_number} 列位已存在通道配置")

        try:
            channel = self.channel_repository.create({"room_id": room_id, **data})
        except DataAccessError as e:
            _raise_position_conflict(
                e, f"第 {col_number} 列位已存在通道配置（可能由并发操作创建）"
            )
            raise
        self.channel_repository.session.flush()
        logger.info(f"新增机房通道成功 (room_id={room_id}, col={col_number})")
        return channel

    def update_channel(self, room_id: int, channel_id: int, data: Dict[str, Any]):
        """编辑通道配置

        Raises:
            ValidationError: 通道不存在 / 不属于该机房 / 改后列位与其他通道冲突
            ResourceConflictError: 竞态下唯一约束兜底命中（HTTP 409，带列位信息）
        """
        channel = self.channel_repository.find_by_id(channel_id)
        if not channel or channel.room_id != room_id:
            raise ValidationError("通道配置不存在")

        new_col = data.get("col_number", channel.col_number)
        if new_col != channel.col_number and self.channel_repository.find_by_room_and_col(
            room_id, new_col
        ):
            raise ValidationError(f"第 {new_col} 列位已存在通道配置")

        try:
            updated = self.channel_repository.update(
                channel_id,
                data,
                allowed=["col_number", "channel_type", "enclosed", "supply", "label", "notes"],
            )
        except DataAccessError as e:
            _raise_position_conflict(e, f"第 {new_col} 列位已存在通道配置（可能由并发操作创建）")
            raise
        self.channel_repository.session.flush()
        logger.info(f"更新机房通道成功 (room_id={room_id}, id={channel_id})")
        return updated

    def delete_channel(self, room_id: int, channel_id: int) -> bool:
        """删除通道配置

        Raises:
            ValidationError: 通道不存在或不属于该机房
        """
        channel = self.channel_repository.find_by_id(channel_id)
        if not channel or channel.room_id != room_id:
            raise ValidationError("通道配置不存在")

        result = self.channel_repository.delete(channel_id)
        if result:
            self.channel_repository.session.flush()
        logger.info(f"删除机房通道成功 (room_id={room_id}, id={channel_id})")
        return result


    def get_layout_markers(self, room_id: int) -> List:
        """获取机房全部占位标记（按行列升序，与网格渲染顺序一致）"""
        return self.marker_repository.find_by_room_id(room_id)

    def create_layout_marker(self, room_id: int, data: Dict[str, Any]):
        """新增占位标记

        Raises:
            ValidationError: 该坐标已存在标记（唯一键 uk_marker_position）
            ResourceConflictError: 竞态下唯一约束兜底命中（HTTP 409，带坐标信息）
        """
        row_number = data.get("row_number")
        col_number = data.get("col_number")
        if self.marker_repository.find_by_position(room_id, row_number, col_number):
            raise ValidationError(f"位置（第{row_number}行 第{col_number}列）已存在占位标记")

        try:
            marker = self.marker_repository.create({"room_id": room_id, **data})
        except DataAccessError as e:
            _raise_position_conflict(
                e,
                f"位置（第{row_number}行 第{col_number}列）已存在占位标记"
                "（可能由并发操作创建）",
            )
            raise
        self.marker_repository.session.flush()
        logger.info(f"新增机房占位标记成功 (room_id={room_id}, pos=({row_number},{col_number}))")
        return marker

    def update_layout_marker(self, room_id: int, marker_id: int, data: Dict[str, Any]):
        """编辑占位标记

        Raises:
            ValidationError: 标记不存在 / 不属于该机房 / 改后坐标与其他标记冲突
            ResourceConflictError: 竞态下唯一约束兜底命中（HTTP 409，带坐标信息）
        """
        marker = self.marker_repository.find_by_id(marker_id)
        if not marker or marker.room_id != room_id:
            raise ValidationError("占位标记不存在")

        new_row = data.get("row_number", marker.row_number)
        new_col = data.get("col_number", marker.col_number)
        if (new_row, new_col) != (marker.row_number, marker.col_number) and (
            self.marker_repository.find_by_position(room_id, new_row, new_col)
        ):
            raise ValidationError(f"位置（第{new_row}行 第{new_col}列）已存在占位标记")

        try:
            updated = self.marker_repository.update(
                marker_id,
                data,
                allowed=["row_number", "col_number", "marker_type", "label", "notes"],
            )
        except DataAccessError as e:
            _raise_position_conflict(
                e, f"位置（第{new_row}行 第{new_col}列）已存在占位标记（可能由并发操作创建）"
            )
            raise
        self.marker_repository.session.flush()
        logger.info(f"更新机房占位标记成功 (room_id={room_id}, id={marker_id})")
        return updated

    def delete_layout_marker(self, room_id: int, marker_id: int) -> bool:
        """删除占位标记

        Raises:
            ValidationError: 标记不存在或不属于该机房
        """
        marker = self.marker_repository.find_by_id(marker_id)
        if not marker or marker.room_id != room_id:
            raise ValidationError("占位标记不存在")

        result = self.marker_repository.delete(marker_id)
        if result:
            self.marker_repository.session.flush()
        logger.info(f"删除机房占位标记成功 (room_id={room_id}, id={marker_id})")
        return result

    def get_statistics(self, room_id: int) -> Dict[str, Any]:
        """获取机房详细统计信息（机柜、设备、U 位等，带缓存）"""
        return cache_manager.get_or_set(
            f"room:detail_stats:{room_id}",
            lambda: self._load_statistics(room_id),
            ttl=ROOM_SHORT_CACHE_TTL,
        )

    def _load_statistics(self, room_id: int) -> Dict[str, Any]:
        """从数据库加载机房详细统计（内部方法）"""
        cabinet_stats = self.cabinet_repository.get_room_cabinet_statistics(room_id)

        device_stats = self.device_repository.get_room_device_statistics(room_id)

        total_u = cabinet_stats["total_u"]
        used_u = device_stats["used_u"]

        return {
            "cabinet_count": cabinet_stats["cabinet_count"],
            "device_count": device_stats["device_count"],
            "available_cabinets": cabinet_stats["available_cabinets"],
            "used_u": used_u,
            "total_u": total_u,
            "u_utilization": round(used_u / total_u * 100, 2) if total_u > 0 else 0,
            "power_statistics": cabinet_stats.get("power_statistics", {}),
            "type_statistics": device_stats.get("type_statistics", {}),
            "type_u_statistics": device_stats.get("type_u_statistics", {}),
        }


    def create(self, data: Dict[str, Any]) -> Room:
        """创建机房

        身份语义（实施计划 D1/D2）：name 是分组键可重复；room_number 组内唯一、必填。

        Args:
            data: 机房字段字典（必须包含 name 与 room_number）

        Raises:
            ValidationError: 名称/房间号为空，或 (name, room_number) 组合已存在
            ResourceConflictError: 竞态下组合唯一约束兜底命中（HTTP 409）
        """
        name = _normalize_grouping_value(data.get("name") or "")
        if not name:
            raise ValidationError("机房名称不能为空")
        data["name"] = name

        room_number = _normalize_grouping_value(data.get("room_number") or "")
        if not room_number:
            raise ValidationError("房间号不能为空")
        data["room_number"] = room_number

        if self.room_repository.check_room_number_exists(name, room_number):
            raise ValidationError(f"机房「{name}」下已存在房间号 {room_number}")

        _normalize_grouping_fields(data)
        data.setdefault("status", 0)
        try:
            room = self.room_repository.create(data)
        except DataAccessError as e:
            _raise_position_conflict(
                e, f"机房「{name}」下已存在房间号 {room_number}（可能由并发操作创建）"
            )
            raise
        self.room_repository.session.flush()
        logger.info(f"创建机房成功: {name}/{room_number} (ID: {room.id})")
        return room

    def update(self, room_id: int, data: Dict[str, Any]) -> Room:
        """更新机房信息（部分更新：只处理传入的键）

        Raises:
            ValidationError: 机房不存在，或 (name, room_number) 组合与其他机房冲突
            ResourceConflictError: 竞态下组合唯一约束兜底命中（HTTP 409）
        """
        if not self.room_repository.exists({"id": room_id}):
            raise ValidationError("机房不存在")

        new_name = _normalize_grouping_value(data.get("name") or "")
        if "name" in data and not new_name:
            raise ValidationError("机房名称不能为空")
        if new_name:
            data["name"] = new_name

        new_number = _normalize_grouping_value(data.get("room_number") or "")
        if "room_number" in data and not new_number:
            raise ValidationError("房间号不能为空")
        if new_number:
            data["room_number"] = new_number

        old = self.room_repository.find_by_id(room_id)
        eff_name = new_name or (old.name if old else None)
        eff_number = new_number or (old.room_number if old else None)
        if eff_name and eff_number and self.room_repository.check_room_number_exists(
            eff_name, eff_number, exclude_id=room_id
        ):
            raise ValidationError(f"机房「{eff_name}」下已存在房间号 {eff_number}")

        _normalize_grouping_fields(data)
        try:
            room = self.room_repository.update(room_id, data)
        except DataAccessError as e:
            _raise_position_conflict(
                e,
                f"机房「{eff_name}」下已存在房间号 {eff_number}（可能由并发操作创建）",
            )
            raise
        self.room_repository.session.flush()
        logger.info(f"更新机房成功 (ID: {room_id})")
        return room

    def delete(self, room_id: int) -> bool:
        """删除机房（物理删除，含依赖检查）

        与 ``force_delete`` 的区别：本方法会拒绝非空机房（有交换机或机柜即 409），
        只删一个**空机房**及其布局配置（通道/占位标记）；不触碰设备及其关联数据。

        Raises:
            ValidationError: 机房不存在或存在关联交换机/机柜
        """
        if not self.room_repository.find_by_id(room_id):
            raise ValidationError("机房不存在")

        deps = self.room_repository.check_room_dependencies(room_id)
        if deps["switch_count"] > 0:
            raise ValidationError("该机房下有交换机，无法删除")
        if deps["cabinet_count"] > 0:
            raise ValidationError(
                f"该机房下还有 {deps['cabinet_count']} 台机柜，无法删除（请先清空机柜）"
            )

        self.channel_repository.delete_by_room_id(room_id)
        self.marker_repository.delete_by_room_id(room_id)

        result = self.room_repository.delete(room_id)
        if result:
            self.room_repository.session.flush()
        logger.info(f"删除机房成功 (ID: {room_id})")
        return result

    def force_delete(self, room_id: int) -> Dict[str, int]:
        """强制删除机房：跳过一切依赖检查，级联**物理删除**机柜、设备及其全部关联数据。

        ⚠️ **不可恢复**。与 `delete()` 的区别：
        - 不检查依赖（有机柜/交换机也照删）；
        - 机柜**物理删除**（而非留下空机房）；
        - 机房内设备的**硬件与运行数据**一并物理删除（硬件描述、端口、凭据、监控状态…）。

        **保留两类**：
        - `audit_logs`——它没有指向 devices/rooms 的外键，不会成为孤儿行，
          且删机房这个动作本身也需要被审计；
        - **留痕三表**（`monitor_incident` / `monitor_suppressed_alert_log` /
          `ai_diagnosis_sessions`）——2026-09-18 拍板：与设备/机柜路径**统一保留**，
          只做「写设备名快照 + 置空设备引用」，行本身不删（见步骤 1.5）。

        **执行顺序不可颠倒**（子表 → 父表）：
        0. 先取出机房内全部设备 ID（下面两步都要用，且必须早于 `devices` 被删）；
        0.5 **释放对端端口占用** —— 机房内设备与**机房外**设备的连接，对端端口不属于
            本机房、不会随之删除，只能显式释放。**必须在 1 之前**：连接行里存着
            "该释放哪个端口"，先删行就是静默 0 释放；
        1. 先按 device 维度清（此时 `devices` 尚未删除，子查询可用）；
        1.5 留痕三表处置（快照 + 置空）——**必须在 2 之前**，设备名是本步唯一的快照来源；
        2. 删 `devices`；
        3. 删 `cabinets`；
        4. 再按 room 维度兜底（交换机类表同时带 room_id）；
        5. 最后删 `rooms`。

        ⚠️ **IP 池 `ip_addresses` 在机房路径上是"删"而不是"释放"**（见
        `_FORCE_DELETE_ROOM_SCOPED`）—— 机房都没了，池也没有存在的意义。
        这与设备/机柜路径刻意不同（后者只释放池状态、不删池行）。

        漏掉任何一张表都会触发外键错误而整体回滚——**失败得很响，不会留下半删状态**，
        这是有意的：宁可整个操作失败，也不要一个删了一半的机房。

        Returns:
            {表名: 删除行数}，供 API 回给前端展示、也便于测试断言"确实清干净了"。
        """
        from sqlalchemy import text

        if not self.room_repository.find_by_id(room_id):
            raise ValidationError("机房不存在")

        session = self.room_repository.session
        counts: Dict[str, int] = {}

        cabinet_ids_sql = "SELECT id FROM cabinets WHERE room_id = :rid"
        device_ids_sql = f"SELECT id FROM devices WHERE cabinet_id IN ({cabinet_ids_sql})"

        def run(table: str, col: str, scope_sql: str, scope_param: str = "rid") -> None:
            if (table, col) not in _FORCE_DELETE_ALLOWED:
                raise ValueError(f"force_delete: (表, 列) 不在白名单内：{(table, col)!r}")
            result = session.execute(
                text(f"DELETE FROM `{table}` WHERE `{col}` IN ({scope_sql})"),
                {scope_param: room_id},
            )
            deleted = result.rowcount or 0
            if deleted:
                counts[table] = counts.get(table, 0) + deleted

        room_device_ids = [
            row[0]
            for row in session.execute(
                text(f"SELECT id FROM devices WHERE cabinet_id IN ({cabinet_ids_sql})"),
                {"rid": room_id},
            ).fetchall()
        ]

        from app.services.device_connection_service import DeviceConnectionService

        released_ports = 0
        for did in room_device_ids:
            released_ports += DeviceConnectionService.release_peer_occupations(
                session, did
            )["released_network_ports"]
        if released_ports:
            counts["_released_network_ports"] = released_ports

        for table, col in _FORCE_DELETE_DEVICE_SCOPED:
            run(table, col, device_ids_sql)

        from app.services.device_service import DeviceService

        DeviceService._dispose_monitor_trace_batch(session, room_device_ids)

        run("devices", "cabinet_id", cabinet_ids_sql)
        run("cabinets", "room_id", "SELECT :rid")

        for table, col in _FORCE_DELETE_ROOM_SCOPED:
            run(table, col, "SELECT :rid")

        result = session.execute(
            text("DELETE FROM `rooms` WHERE `id` = :rid"), {"rid": room_id}
        )
        counts["rooms"] = result.rowcount or 0

        session.flush()
        logger.warning(
            f"【强制删除】机房及其全部关联数据已物理删除 (room_id={room_id})：{counts}"
        )
        return counts
