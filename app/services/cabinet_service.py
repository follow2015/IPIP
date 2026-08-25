# -*- coding: utf-8 -*-
"""
机柜服务模块

业务逻辑层：
- 所有数据访问必须经由 CabinetRepository，禁止直接使用 db_manager / 裸 SQL
- Service 方法为实例方法，便于测试与依赖注入
"""
from app.utils.logging import get_logger
from typing import Any, Dict, List, Optional

from app.exceptions.data_access import RecordNotFoundError
from app.exceptions.validation import ValidationError
from app.models.cabinet import Cabinet
from app.persistence.cabinet_repository import CabinetRepository
from app.utils.cabinet_utils import (
    CabinetUCalculator,
    UPositionStrategy,
)
from app.services.switch_events import emit_resource_change_global
from app.utils.cache import cache_manager, cached
from config import get_config

logger = get_logger(__name__)
config = get_config()

_STRATEGY_MAP: Dict[str, UPositionStrategy] = {
    "auto_bottom_up": UPositionStrategy.AUTO_BOTTOM_UP,
    "bottom_up":      UPositionStrategy.AUTO_BOTTOM_UP,
    "auto_top_down":  UPositionStrategy.AUTO_TOP_DOWN,
    "top_down":       UPositionStrategy.AUTO_TOP_DOWN,
    "auto_best_fit":  UPositionStrategy.AUTO_BEST_FIT,
    "best_fit":       UPositionStrategy.AUTO_BEST_FIT,
    "auto_first_fit": UPositionStrategy.AUTO_FIRST_FIT,
    "first_fit":      UPositionStrategy.AUTO_FIRST_FIT,
}


def _parse_strategy(strategy: str) -> UPositionStrategy:
    """将策略字符串转换为枚举，未知策略降级为 AUTO_BOTTOM_UP。"""
    return _STRATEGY_MAP.get(str(strategy).lower(), UPositionStrategy.AUTO_BOTTOM_UP)


class CabinetService:
    """机柜服务

    提供机柜的 CRUD、U 位管理、布局优化、容量验证等全部业务逻辑。

    重构说明：
    1. 全部 @staticmethod 方法迁移为实例方法，通过 repository 访问数据，
       消除直接 db_manager / 裸 SQL 调用
    2. 修复 update_cabinet 中字段映射方向矛盾（total_u↔u_count）
    3. 删除重复 @staticmethod 装饰器及方法末尾的死代码块
    4. 统一缓存失效逻辑至 _invalidate_cabinet_cache
    """

    def __init__(self, cabinet_repository: CabinetRepository):
        self.cabinet_repository = cabinet_repository
        self.cache_ttl: int = getattr(config, "CACHE_TTL_CABINET", 300)


    def get_by_id(self, cabinet_id: int) -> Optional[Cabinet]:
        """根据 ID 获取机柜，不存在时返回 None。"""
        return self.cabinet_repository.find_by_id(cabinet_id)

    def get_by_id_or_raise(self, cabinet_id: int) -> Cabinet:
        """根据 ID 获取机柜，不存在时抛出 RecordNotFoundError。"""
        cabinet = self.get_by_id(cabinet_id)
        if cabinet is None:
            raise RecordNotFoundError(f"机柜 {cabinet_id} 不存在")
        return cabinet

    def get_by_cabinet_number(self, cabinet_number: str) -> Optional[Cabinet]:
        """根据机柜编号查找机柜。"""
        return self.cabinet_repository.find_by_cabinet_number(cabinet_number)

    def get_paginated(
        self,
        page: int = 1,
        per_page: int = 20,
        filters: Optional[Dict[str, Any]] = None,
    ) -> tuple[list[Cabinet], int]:
        """获取分页机柜列表。"""
        normalized = self._normalize_filters(filters)
        result = self.cabinet_repository.paginate(page=page, page_size=per_page, filters=normalized)
        return result["data"], result["total_count"]

    @cached(key_pattern="cabinet:with_devices:{cabinet_id}")
    def get_cabinet_with_devices(self, cabinet_id: int) -> Optional[Dict[str, Any]]:
        """获取机柜及设备详情（含缓存）。"""
        cabinet = self.get_by_id(cabinet_id)
        return cabinet.to_dict(include_relations=True) if cabinet else None

    def search_cabinets(
        self,
        keyword: Optional[str] = None,
        room_id: Optional[int] = None,
        status: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """搜索机柜（关键词 + 精确过滤 + 分页）。"""
        filters: Dict[str, Any] = {}
        if room_id is not None:
            filters["room_id"] = room_id
        if status is not None:
            filters["status"] = status

        result = self.cabinet_repository.search(
            search_fields=["cabinet_number", "location"],
            keyword=keyword,
            filters=filters,
            page=page,
            page_size=page_size,
        )
        result["data"] = [c.to_dict() for c in result["data"]]
        return result

    def get_cabinets_by_room(self, room_id: int) -> List[Dict[str, Any]]:
        """获取指定机房的全部机柜（含使用统计）。"""
        return [c.to_dict() for c in self.cabinet_repository.find_by_room_id(room_id)]

    def get_all_cabinets_list(self) -> List[Dict[str, Any]]:
        """获取全部机柜列表（用于导出等场景）。"""
        return [c.to_dict() for c in self.cabinet_repository.find_all()]

    def get_available_cabinets(
        self, room_id: Optional[int] = None, min_available_u: int = 1,
        all_status: bool = False, statuses: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """获取可用机柜列表（默认status=1 且可用 U 位 >= min_available_u）。

        all_status=True 时不限制状态，用于筛选场景。
        statuses 优先级高于 all_status，指定允许的状态码列表。
        """
        cabinets = self.cabinet_repository.find_available_cabinets(
            room_id, min_available_u, all_status=all_status, statuses=statuses,
        )
        result = []
        for c in cabinets:
            data = c.to_dict()
            data["available_u"] = c.get_available_u_count()
            result.append(data)
        return result

    def get_cabinet_count(self, room_id: Optional[int] = None) -> int:
        """获取机柜总数，可按机房过滤。"""
        filters = {"room_id": room_id} if room_id is not None else None
        return self.cabinet_repository.count(filters)

    def cabinet_exists(self, cabinet_id: int) -> bool:
        """检查机柜是否存在。"""
        return self.get_by_id(cabinet_id) is not None


    def check_cabinet_number_exists(
        self, cabinet_number: str, exclude_id: Optional[int] = None
    ) -> bool:
        """检查机柜编号是否已存在。"""
        return self.cabinet_repository.check_cabinet_number_exists(cabinet_number, exclude_id)

    def create_cabinet(self, data: Dict[str, Any]) -> Cabinet:
        """创建机柜。

        Raises:
            ValidationError: 机柜编号已存在
        """
        payload = self._normalize_cabinet_payload(data)
        if self.check_cabinet_number_exists(payload.get("cabinet_number", "")):
            raise ValidationError(f"机柜编号 '{payload.get('cabinet_number')}' 已存在")

        cabinet = self.cabinet_repository.create(payload)
        self._invalidate_cabinet_cache(cabinet.id, cabinet.room_id)
        emit_resource_change_global("cabinet", "create", ids=[cabinet.id])
        return cabinet

    def update_cabinet(self, cabinet_id: int, data: Dict[str, Any]) -> Cabinet:
        """更新机柜。

        修复：原代码在此处将 total_u 映射为 u_count（data["u_count"] = data.pop("total_u")），
        与 _normalize_cabinet_payload 中 u_count→total_u 的方向相反，导致字段错乱。
        现统一通过 _normalize_cabinet_payload 处理，不再在此单独映射。

        Raises:
            RecordNotFoundError: 机柜不存在
            ValidationError: 编号已被其他机柜占用
        """
        old_cabinet = self.get_by_id_or_raise(cabinet_id)
        payload     = self._normalize_cabinet_payload(data)

        if "cabinet_number" in payload:
            if self.check_cabinet_number_exists(payload["cabinet_number"], exclude_id=cabinet_id):
                raise ValidationError(f"机柜编号 '{payload['cabinet_number']}' 已存在")

        if payload.get("customer_id") == "":
            payload["customer_id"] = None

        old_customer_id = old_cabinet.customer_id
        new_customer_id = payload.get("customer_id", old_customer_id)

        if "customer_id" in payload and new_customer_id is not None:
            from app.services.customer_service import CustomerService
            from app.persistence.customer_repository import CustomerRepository
            CustomerService(CustomerRepository()).assert_allocatable(new_customer_id)

        cabinet = self.cabinet_repository.update(cabinet_id, payload)
        self._invalidate_cabinet_cache(cabinet_id, old_cabinet.room_id)
        if cabinet and cabinet.room_id != old_cabinet.room_id:
            cache_manager.invalidate_pattern(f"room:{cabinet.room_id}:*")

        if new_customer_id != old_customer_id:
            self._sync_devices_customer(cabinet_id, new_customer_id)

        emit_resource_change_global("cabinet", "update", ids=[cabinet_id])
        return cabinet

    def _sync_devices_customer(self, cabinet_id: int, customer_id: Optional[int]) -> None:
        """机柜客户变更时，同步更新该机柜下所有设备的客户ID。

        使用批量 UPDATE 语句，避免逐条加载设备对象导致 N+1 查询。
        本方法不提交事务，由 API 层 @transactional 统一管理。

        Args:
            cabinet_id: 机柜ID
            customer_id: 新的客户ID（可为 None，表示清除客户）
        """
        from app.models.device import Device

        self.cabinet_repository.session.query(Device).filter(
            Device.cabinet_id == cabinet_id,
            Device.deleted_at.is_(None),
        ).update({Device.customer_id: customer_id}, synchronize_session="fetch")

        logger.info(
            "机柜 %s 客户变更为 %s，已同步更新机柜下设备的客户ID",
            cabinet_id, customer_id,
        )

    def delete_cabinet(self, cabinet_id: int, force: bool = False) -> bool:
        """删除机柜。

        Args:
            force: True 时强制删除（即使有关联设备）

        Raises:
            RecordNotFoundError: 机柜不存在
            ValidationError: 有关联设备且非强制删除
        """
        cabinet = self.get_by_id_or_raise(cabinet_id)
        room_id = cabinet.room_id

        if not force and cabinet.devices:
            raise ValidationError(
                f"机柜下还有 {len(cabinet.devices)} 个设备，无法删除。"
                "请先删除所有设备或使用强制删除（force=True）。"
            )

        result = self.cabinet_repository.delete(cabinet_id)
        if result:
            self._invalidate_cabinet_cache(cabinet_id, room_id)
            emit_resource_change_global("cabinet", "delete", ids=[cabinet_id])
        return result

    def batch_delete_cabinets(
        self, cabinet_ids: List[int], force: bool = False
    ) -> Dict[str, Any]:
        """批量删除机柜，返回各 ID 的成功/失败情况。"""
        deleted: List[int]         = []
        failed:  List[int]         = []
        errors:  Dict[int, str]    = {}

        for cid in cabinet_ids:
            try:
                self.delete_cabinet(cid, force=force)
                deleted.append(cid)
            except (RecordNotFoundError, ValidationError) as e:
                failed.append(cid)
                errors[cid] = str(e)

        if deleted:
            emit_resource_change_global("cabinet", "batch_delete", ids=deleted)
        return {"deleted": deleted, "failed": failed, "errors": errors}
    def update_cabinet_customer(
        self, cabinet_id: int, new_customer_id: Optional[int]
    ) -> Cabinet:
        """更新机柜绑定客户（整柜租赁）。

        Args:
            new_customer_id: 新客户 ID；None 表示解绑

        Raises:
            RecordNotFoundError: 机柜不存在
        """
        old_cabinet = self.get_by_id_or_raise(cabinet_id)
        if new_customer_id is not None:
            from app.services.customer_service import CustomerService
            from app.persistence.customer_repository import CustomerRepository
            CustomerService(CustomerRepository()).assert_allocatable(new_customer_id)
        cabinet = self.cabinet_repository.update(cabinet_id, {"customer_id": new_customer_id})
        if new_customer_id != old_cabinet.customer_id:
            self._sync_devices_customer(cabinet_id, new_customer_id)
        cache_manager.invalidate_pattern(f"cabinet:{cabinet_id}:*")
        cache_manager.invalidate_pattern(f"cabinet:with_devices:{cabinet_id}")
        cache_manager.invalidate_pattern(f"cabinet:layout:{cabinet_id}")
        logger.info(f"机柜 {cabinet_id} 客户已更新为 {new_customer_id}")
        emit_resource_change_global("cabinet", "update", ids=[cabinet_id])
        return cabinet


    def get_devices(self, cabinet_id: int) -> List:
        """获取机柜下的全部设备。"""
        cabinet = self.get_by_id(cabinet_id)
        return cabinet.devices if cabinet else []

    def update_cabinet_usage(self, cabinet_id: int) -> bool:
        """重新计算并持久化 used_u / used_power 冗余字段。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return False
        cabinet.update_usage()
        self.cabinet_repository.session.flush()
        cache_manager.invalidate_pattern(f"cabinet:{cabinet_id}:*")
        cache_manager.invalidate_pattern(f"cabinet:with_devices:{cabinet_id}")
        cache_manager.invalidate_pattern(f"cabinet:layout:{cabinet_id}")
        return True

    def check_u_position_available(
        self,
        cabinet_id: int,
        u_position: int,
        height_u: int,
        exclude_device_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """检查指定 U 位区间是否可用（无冲突）。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return {"available": False, "message": "机柜不存在"}

        devices  = [d.to_dict() for d in cabinet.devices]
        conflict = CabinetUCalculator.check_u_position_conflict(
            devices=devices,
            cabinet_id=cabinet_id,
            u_position=u_position,
            height_u=height_u,
            total_u=cabinet.total_u,
            exclude_device_id=exclude_device_id,
            filter_parent_only=True,
        )

        if conflict["has_conflict"]:
            return {
                "available":           False,
                "message":             conflict["message"],
                "conflicting_devices": conflict["conflict_devices"],
            }
        return {"available": True, "message": "U位可用"}

    def get_available_u_positions(
        self, cabinet_id: int, height_u: int = 1, device_spacing: int = 2
    ) -> Optional[Dict[str, Any]]:
        """获取可放置指定高度设备的 U 位列表。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return None
        devices = [d.to_dict() for d in cabinet.devices]
        return CabinetUCalculator.get_available_u_positions(
            devices=devices, total_u=cabinet.total_u,
            height_u=height_u, device_spacing=device_spacing,
        )

    def auto_allocate_u_position(
        self,
        cabinet_id: int,
        height_u: int,
        strategy: str = "auto_bottom_up",
        device_spacing: int = 2,
    ) -> Optional[int]:
        """智能分配 U 位，返回推荐起始 U 位。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return None
        devices = [d.to_dict() for d in cabinet.devices]
        return CabinetUCalculator.auto_allocate_u_position(
            devices=devices, total_u=cabinet.total_u,
            height_u=height_u, strategy=_parse_strategy(strategy),
            device_spacing=device_spacing,
        )

    def batch_allocate_devices(
        self,
        cabinet_id: int,
        devices_to_allocate: List[Dict],
        default_strategy: str = "auto_bottom_up",
        allow_partial: bool = False,
        device_spacing: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """批量为多个设备分配 U 位。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return None
        existing = [d.to_dict() for d in cabinet.devices]
        return CabinetUCalculator.batch_allocate_devices(
            devices_to_allocate=devices_to_allocate,
            existing_devices=existing,
            total_u=cabinet.total_u,
            default_strategy=_parse_strategy(default_strategy),
            allow_partial=allow_partial,
            device_spacing=device_spacing,
        )


    def get_utilization(self, cabinet_id: int) -> Optional[Dict[str, Any]]:
        """获取机柜 U 位与功率利用率。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return None

        total_u     = cabinet.total_u or 0
        used_u      = len(cabinet.get_used_u_positions())
        total_power = cabinet.total_power or 0
        used_power  = cabinet.used_power or 0

        return {
            "cabinet_id":       cabinet_id,
            "cabinet_number":   cabinet.cabinet_number,
            "total_u":          total_u,
            "used_u":           used_u,
            "available_u":      total_u - used_u,
            "u_usage_rate":     round(used_u / total_u * 100, 2) if total_u else 0,
            "total_power":      total_power,
            "used_power":       used_power,
            "available_power":  total_power - used_power,
            "power_usage_rate": round(used_power / total_power * 100, 2) if total_power else 0,
        }

    @cached(key_pattern="cabinet:layout:{cabinet_id}")
    def get_cabinet_layout(self, cabinet_id: int) -> Optional[Dict[str, Any]]:
        """获取机柜布局（含 U 位占用映射）。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return None

        devices     = [d.to_dict() for d in cabinet.devices]
        usage       = CabinetUCalculator.calculate_u_usage(devices, cabinet.total_u)
        free_ranges = CabinetUCalculator.get_free_ranges(devices, cabinet.total_u)

        u_map: Dict[int, Dict[str, Any]] = {}
        for dev in cabinet.devices:
            if dev.parent_device_id or not (dev.u_position and dev.height_u):
                continue
            for u in range(dev.u_position, dev.u_position + dev.height_u):
                u_map[u] = {
                    "device_id":   dev.id,
                    "device_name": dev.device_name,
                    "device_type": dev.device_type,
                    "is_start":    u == dev.u_position,
                    "height_u":    dev.height_u,
                    "power":       getattr(dev, "power", None),
                }

        return {
            "cabinet_id":      cabinet_id,
            "cabinet_number":  cabinet.cabinet_number,
            "room_name":       cabinet.room.name if cabinet.room else None,
            "total_u":         cabinet.total_u,
            "used_u":          usage["used_u"],
            "available_u":     usage["free_u"],
            "usage_rate":      usage["usage_rate"],
            "device_count":    len([d for d in cabinet.devices if not d.parent_device_id]),
            "u_map":           u_map,
            "available_ranges":[
                {"start": r.start, "end": r.end, "height": r.height} for r in free_ranges
            ],
        }

    def get_u_usage_map(self, cabinet_id: int) -> Optional[Dict[str, Any]]:
        """获取完整 U 位使用映射（每个 U 位的状态与设备信息）。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return None

        total_u = cabinet.total_u or 42
        u_map   = {u: {"u_position": u, "status": "free", "device": None}
                   for u in range(1, total_u + 1)}

        for dev in cabinet.devices:
            if not dev.u_position:
                continue
            h = int(dev.height_u or 1)
            for u in range(dev.u_position, min(dev.u_position + h, total_u + 1)):
                u_map[u] = {
                    "u_position": u,
                    "status":     "used",
                    "device": {
                        "id":               dev.id,
                        "device_name":      dev.device_name,
                        "device_type":      dev.device_type,
                        "is_chassis":       getattr(dev, "is_chassis", False),
                        "parent_device_id": dev.parent_device_id,
                        "u_position":       dev.u_position,
                        "height_u":         h,
                    },
                }

        used_count = sum(1 for v in u_map.values() if v["status"] == "used")
        return {
            "cabinet_id":     cabinet_id,
            "cabinet_number": cabinet.cabinet_number,
            "total_u":        total_u,
            "u_map":          u_map,
            "used_u_count":   used_count,
            "free_u_count":   total_u - used_count,
        }

    def get_cabinet_stats(self, cabinet_id: int) -> Optional[Dict[str, Any]]:
        """获取机柜统计信息（设备数、U 位、功率）。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return None

        parent_devices = [d for d in cabinet.devices if not d.parent_device_id]
        total_u        = cabinet.total_u or 42
        used_u         = len(cabinet.get_used_u_positions())
        total_power    = cabinet.total_power or 0
        used_power     = sum(float(d.power or 0) for d in parent_devices)
        chassis_count  = sum(1 for d in cabinet.devices if getattr(d, "is_chassis", False))
        node_count     = sum(1 for d in cabinet.devices if d.parent_device_id)

        return {
            "cabinet_id":      cabinet_id,
            "cabinet_number":  cabinet.cabinet_number,
            "room_id":         cabinet.room_id,
            "room_name":       cabinet.room.name if cabinet.room else None,
            "total_u":         total_u,
            "used_u":          used_u,
            "available_u":     total_u - used_u,
            "u_usage_rate":    round(used_u / total_u * 100, 2) if total_u else 0,
            "total_power":     total_power,
            "used_power":      int(used_power),
            "available_power": total_power - int(used_power),
            "power_usage_rate":round(used_power / total_power * 100, 2) if total_power else 0,
            "max_weight":      cabinet.max_weight,
            "device_count":    len(cabinet.devices),
            "chassis_count":   chassis_count,
            "node_count":      node_count,
        }

    def get_cabinet_usage_with_spacing(
        self, cabinet_id: int, device_spacing: int = 2
    ) -> Optional[Dict[str, Any]]:
        """获取机柜使用情况（含设备间距）。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return None

        devices  = [d.to_dict() for d in cabinet.devices]
        total_u  = cabinet.total_u or 42
        usage    = CabinetUCalculator.calculate_total_u_with_spacing(
            devices, total_u, device_spacing=device_spacing
        )
        actual_u_used       = usage["total_height"]
        u_used_with_spacing = usage["total_with_spacing"]

        return {
            "cabinet_id":             cabinet_id,
            "cabinet_number":         cabinet.cabinet_number,
            "total_u":                total_u,
            "device_count":           usage["device_count"],
            "actual_u_used":          actual_u_used,
            "actual_usage_rate":      round(actual_u_used / total_u * 100, 2) if total_u else 0,
            "u_used_with_spacing":    u_used_with_spacing,
            "usage_rate_with_spacing":usage["usage_rate"],
            "available_u":            total_u - u_used_with_spacing,
            "device_spacing":         device_spacing,
        }

    def optimize_cabinet_layout(
        self, cabinet_id: int, strategy: str = "compact", device_spacing: int = 2
    ) -> Optional[Dict[str, Any]]:
        """优化机柜布局。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return None
        devices = [d.to_dict() for d in cabinet.devices]
        return CabinetUCalculator.optimize_cabinet_layout(
            devices=devices, total_u=cabinet.total_u, device_spacing=device_spacing
        )

    def validate_cabinet_capacity(
        self,
        cabinet_id: int,
        additional_u: int = 0,
        additional_power: int = 0,
        device_spacing: int = 2,
        max_usage_rate: float = 90.0,
    ) -> Optional[Dict[str, Any]]:
        """验证机柜容量规划，支持模拟新增设备后的预检。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return None

        devices = [d.to_dict() for d in cabinet.devices]
        result  = CabinetUCalculator.validate_cabinet_capacity(
            devices=devices, total_u=cabinet.total_u,
            device_spacing=device_spacing, max_usage_rate=max_usage_rate,
        )

        if additional_u > 0:
            check = CabinetUCalculator.check_capacity_with_spacing(
                devices=devices, total_u=cabinet.total_u,
                new_height=additional_u, device_spacing=device_spacing,
            )
            result["u_summary"] = (
                f"模拟新增 {additional_u}U 后：{check['new_total']}/{cabinet.total_u}U"
            )
            if check["exceeds"]:
                result["warnings"].append(
                    f"新增 {additional_u}U 设备后超出总容量 {check['over_limit']}U"
                )
                result["valid"] = False

        if additional_power > 0 and cabinet.total_power:
            new_power  = (cabinet.used_power or 0) + additional_power
            power_rate = round(new_power / cabinet.total_power * 100, 2)
            result["power_summary"] = (
                f"模拟新增 {additional_power}W 后：{new_power}/{cabinet.total_power}W ({power_rate}%)"
            )
            if power_rate > max_usage_rate:
                result["warnings"].append(
                    f"功率使用率 {power_rate}% 超过阈值 {max_usage_rate}%"
                )
                result["valid"] = False

        return result

    def check_capacity_with_spacing(
        self, cabinet_id: int, new_height: int, device_spacing: int = 2
    ) -> Dict[str, Any]:
        """检查添加新设备后是否超出容量（含间距）。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return {"can_fit": False, "message": "机柜不存在"}

        devices = [d.to_dict() for d in cabinet.devices]
        check   = CabinetUCalculator.check_capacity_with_spacing(
            devices=devices, total_u=cabinet.total_u,
            new_height=new_height, device_spacing=device_spacing,
        )
        return {
            "can_fit":       not check["exceeds"],
            "total_u":       check["total_u"],
            "current_used":  check["current_total"],
            "new_total":     check["new_total"],
            "over_limit":    check.get("over_limit", 0),
            "device_spacing":device_spacing,
            "message": (
                "可以容纳新设备"
                if not check["exceeds"]
                else f"空间不足，需要 {check['new_total']}U，总容量 {check['total_u']}U"
            ),
        }

    def check_u_position_conflict(
        self,
        cabinet_id: int,
        u_position: int,
        height_u: int,
        exclude_device_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """检查指定U位区间是否与已有设备冲突。"""
        cabinet = self.get_by_id(cabinet_id)
        if not cabinet:
            return {
                "has_conflict": True,
                "conflict_devices": [],
                "conflict_ranges": [],
                "message": "机柜不存在",
            }

        devices = [d.to_dict() for d in cabinet.devices]
        return CabinetUCalculator.check_u_position_conflict(
            devices=devices,
            cabinet_id=cabinet_id,
            u_position=u_position,
            height_u=height_u,
            total_u=cabinet.total_u,
            exclude_device_id=exclude_device_id,
        )

    def allocate_u_position(
        self,
        cabinet_id: int,
        height_u: int,
        strategy: str = "auto_bottom_up",
        device_spacing: int = 2,
    ) -> Optional[int]:
        """智能分配U位（兼容旧API）。"""
        return self.auto_allocate_u_position(
            cabinet_id=cabinet_id,
            height_u=height_u,
            strategy=strategy,
            device_spacing=device_spacing,
        )

    def get_global_statistics(self) -> Dict[str, Any]:
        """获取全局机柜统计汇总。"""
        return self.cabinet_repository.get_cabinet_statistics()


    def _normalize_cabinet_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """统一字段命名（兼容旧 API 字段名 → 标准字段名）。

        修复：原代码 _normalize_cabinet_payload 将 u_count 映射到 total_u，
        但 update_cabinet 同时又把 total_u 映射回 u_count，两者方向矛盾。
        现统一：旧字段 u_count → 标准字段 total_u（单向）。
        """
        payload = dict(data or {})
        for src, dst in {
            "name":           "cabinet_number",
            "position":       "location",
            "u_count":        "total_u",       # 旧字段兼容
            "power_capacity": "total_power",
            "description":    "notes",
        }.items():
            if src in payload and dst not in payload:
                payload[dst] = payload.pop(src)

        if "status" in payload and isinstance(payload["status"], str):
            payload["status"] = self._convert_cabinet_status(payload["status"])

        return payload

    def _normalize_filters(self, filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """标准化过滤条件（状态字符串转整数）。"""
        normalized = dict(filters or {})
        if "status" in normalized and isinstance(normalized["status"], str):
            normalized["status"] = self._convert_cabinet_status(normalized["status"])
        return normalized

    @staticmethod
    def _convert_cabinet_status(status_value: Any) -> int:
        """将字符串状态转换为机柜状态码。"""
        if isinstance(status_value, int):
            return status_value
        return {
            "available":   1,
            "occupied":    2,
            "maintenance": 3,
            "reserved":    4,
            "disabled":    0,
        }.get(str(status_value).lower(), 1)

    def _invalidate_cabinet_cache(self, cabinet_id: int, room_id: Optional[int] = None) -> None:
        """统一失效机柜相关全部缓存。"""
        cache_manager.invalidate_pattern(f"cabinet:{cabinet_id}:*")
        cache_manager.invalidate_pattern(f"cabinet:with_devices:{cabinet_id}")
        cache_manager.invalidate_pattern(f"cabinet:layout:{cabinet_id}")
        if room_id:
            cache_manager.invalidate_pattern(f"room:{room_id}:*")


cabinet_service = CabinetService(CabinetRepository())
