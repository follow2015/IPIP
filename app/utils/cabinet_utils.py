# -*- coding: utf-8 -*-
"""机柜U位计算工具类

提供统一的U位计算、验证、冲突检测等功能。
解决前后端、不同服务之间U位计算逻辑不一致的问题。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class UPositionStrategy(Enum):
    """U位分配策略"""

    MANUAL          = "manual"
    AUTO_BOTTOM_UP  = "auto_bottom_up"   # 从底部（1U）向上分配
    AUTO_TOP_DOWN   = "auto_top_down"    # 从顶部（最大U）向下分配
    AUTO_BEST_FIT   = "auto_best_fit"    # 最小空隙优先（减少碎片）
    AUTO_FIRST_FIT  = "auto_first_fit"   # 选第一个合适空隙


class DeviceType(Enum):
    """设备类型"""

    SERVER      = "server"
    SWITCH      = "switch"
    STORAGE     = "storage"
    PDU         = "pdu"
    UPS         = "ups"
    PATCH_PANEL = "patch_panel"
    OTHER       = "other"


@dataclass
class UPositionRange:
    """U位连续范围"""

    start: int
    end:   int

    @property
    def height(self) -> int:
        return self.end - self.start + 1

    def overlaps(self, other: "UPositionRange") -> bool:
        """检查是否与另一个范围重叠"""
        return self.start <= other.end and other.start <= self.end

    def contains(self, u: int) -> bool:
        """检查是否包含某个U位"""
        return self.start <= u <= self.end


@dataclass
class DeviceConstraint:
    """设备约束条件"""

    min_u_position:       Optional[int]       = None
    max_u_position:       Optional[int]       = None
    preferred_positions:  Optional[List[int]] = None
    avoid_positions:      Optional[List[int]] = None
    must_align_bottom:    bool                = False
    must_align_top:       bool                = False
    require_adjacent_to:  Optional[int]       = None
    require_spacing_from: Optional[List[int]] = None
    device_type_priority: Optional[DeviceType]= None


class CabinetUCalculator:
    """机柜U位计算器"""


    @staticmethod
    def parse_u_position(u_position) -> Optional[int]:
        """解析U位位置值（支持字符串 "U3"、数字 3 等形式）。"""
        if u_position is None:
            return None
        if isinstance(u_position, (int, float)):
            return int(u_position)
        if isinstance(u_position, str):
            try:
                return int(u_position.strip().upper().replace("U", ""))
            except ValueError:
                return None
        return None

    @staticmethod
    def is_valid_u_position(u_position: int, total_u: int) -> bool:
        """验证U位是否在机柜有效范围内（1 ~ total_u）。"""
        return isinstance(u_position, int) and 1 <= u_position <= total_u

    @staticmethod
    def calculate_used_u_positions(
        devices: List[Dict], total_u: int, filter_parent_only: bool = True
    ) -> Set[int]:
        """计算已占用的U位集合。"""
        used: Set[int] = set()
        for device in devices:
            if filter_parent_only and device.get("parent_device_id"):
                continue
            start_u  = CabinetUCalculator.parse_u_position(device.get("u_position"))
            height_u = int(device.get("height_u", device.get("u_height", 1)))
            if start_u is None or not CabinetUCalculator.is_valid_u_position(start_u, total_u):
                continue
            for u in range(start_u, start_u + height_u):
                if u <= total_u:
                    used.add(u)
        return used

    @staticmethod
    def calculate_u_usage(
        devices: List[Dict], total_u: int, filter_parent_only: bool = True
    ) -> Dict:
        """计算U位使用情况（used / free / usage_rate）。"""
        used_positions = CabinetUCalculator.calculate_used_u_positions(
            devices, total_u, filter_parent_only
        )
        used_u     = len(used_positions)
        free_u     = total_u - used_u
        usage_rate = round(used_u / total_u * 100, 2) if total_u > 0 else 0
        return {"total_u": total_u, "used_u": used_u, "free_u": free_u, "usage_rate": usage_rate}


    @staticmethod
    def check_u_position_conflict(
        devices: List[Dict],
        cabinet_id: int,
        u_position: int,
        height_u: int,
        total_u: int,
        exclude_device_id: Optional[int] = None,
        filter_parent_only: bool = True,
    ) -> Dict:
        """检查指定U位区间是否与已有设备冲突。"""
        if not CabinetUCalculator.is_valid_u_position(u_position, total_u):
            return {
                "has_conflict":    True,
                "conflict_devices": [],
                "conflict_ranges": [],
                "message":         f"U位 {u_position} 超出机柜范围（1-{total_u}U）",
            }

        device_start = u_position
        device_end   = u_position + height_u - 1
        conflict_devices: List[Dict] = []
        conflict_ranges:  List[str]  = []

        for device in devices:
            device_id = device.get("id")
            if exclude_device_id and device_id == exclude_device_id:
                continue
            if filter_parent_only and device.get("parent_device_id"):
                continue

            start_u = CabinetUCalculator.parse_u_position(device.get("u_position"))
            if start_u is None:
                continue

            d_height = int(device.get("height_u", device.get("u_height", 1)))
            end_u    = start_u + d_height - 1

            if device_start <= end_u and start_u <= device_end:
                conflict_devices.append({
                    "id":          device_id,
                    "device_name": device.get("device_name", "Unknown"),
                    "u_position":  start_u,
                    "height_u":    d_height,
                    "range":       f"{start_u}-{end_u}U",
                })
                overlap_start = max(device_start, start_u)
                overlap_end   = min(device_end,   end_u)
                conflict_ranges.append(f"{overlap_start}-{overlap_end}U")

        return {
            "has_conflict":    len(conflict_devices) > 0,
            "conflict_devices": conflict_devices,
            "conflict_ranges": conflict_ranges,
            "message":         f"发现 {len(conflict_devices)} 个冲突" if conflict_devices else "无冲突",
        }


    @staticmethod
    def get_occupied_ranges(
        devices: List[Dict], total_u: int, filter_parent_only: bool = True
    ) -> List[UPositionRange]:
        """获取已占用U位区间列表（已排序）。"""
        ranges: List[UPositionRange] = []
        for device in devices:
            if filter_parent_only and device.get("parent_device_id"):
                continue
            start_u = CabinetUCalculator.parse_u_position(device.get("u_position"))
            if start_u is None:
                continue
            h = int(device.get("height_u", device.get("u_height", 1)))
            if CabinetUCalculator.is_valid_u_position(start_u, total_u):
                ranges.append(UPositionRange(start_u, min(start_u + h - 1, total_u)))
        return sorted(ranges, key=lambda r: r.start)

    @staticmethod
    def _merge_ranges(ranges: List[UPositionRange]) -> List[UPositionRange]:
        """合并重叠或相邻的U位区间。"""
        if not ranges:
            return []
        sorted_r = sorted(ranges, key=lambda r: r.start)
        merged   = [sorted_r[0]]
        for cur in sorted_r[1:]:
            last = merged[-1]
            if cur.start <= last.end + 1:
                merged[-1] = UPositionRange(last.start, max(last.end, cur.end))
            else:
                merged.append(cur)
        return merged

    @staticmethod
    def get_free_ranges(
        devices: List[Dict],
        total_u: int,
        filter_parent_only: bool = True,
        include_spacing: bool = False,
        device_spacing: int = 2,
        min_height_for_spacing: int = 2,
    ) -> List[UPositionRange]:
        """获取空闲U位区间列表。"""
        occupied = CabinetUCalculator.get_occupied_ranges(devices, total_u, filter_parent_only)

        if include_spacing:
            expanded: List[UPositionRange] = []
            for device in devices:
                if filter_parent_only and device.get("parent_device_id"):
                    continue
                start_u = CabinetUCalculator.parse_u_position(device.get("u_position"))
                if start_u is None:
                    continue
                if not CabinetUCalculator.is_valid_u_position(start_u, total_u):
                    continue
                h = int(device.get("height_u", device.get("u_height", 1)))
                end_u = min(start_u + h - 1, total_u)
                if h >= min_height_for_spacing and device_spacing > 0:
                    end_u = min(end_u + device_spacing, total_u)
                expanded.append(UPositionRange(start_u, end_u))
            occupied = expanded

        merged     = CabinetUCalculator._merge_ranges(occupied)
        free: List[UPositionRange] = []
        current_u  = 1
        for r in merged:
            if current_u < r.start:
                free.append(UPositionRange(current_u, r.start - 1))
            current_u = r.end + 1
        if current_u <= total_u:
            free.append(UPositionRange(current_u, total_u))
        return free


    @staticmethod
    def get_available_u_positions(
        devices: List[Dict],
        total_u: int,
        height_u: int = 1,
        device_spacing: int = 2,
        filter_parent_only: bool = True,
        min_height_for_spacing: int = 2,
    ) -> Dict:
        """获取可放置指定高度设备的起始U位列表及使用映射。"""
        used_positions = CabinetUCalculator.calculate_used_u_positions(
            devices, total_u, filter_parent_only
        )

        usage_map = [
            {"u_position": u, "is_used": u in used_positions, "is_spacing": False}
            for u in range(1, total_u + 1)
        ]

        for device in devices:
            if filter_parent_only and device.get("parent_device_id"):
                continue
            start_u = CabinetUCalculator.parse_u_position(device.get("u_position"))
            if start_u is None:
                continue
            d_height = int(device.get("height_u", device.get("u_height", 1)))
            end_u    = start_u + d_height - 1
            if d_height >= min_height_for_spacing and device_spacing > 0:
                for u in range(end_u + 1, min(end_u + device_spacing + 1, total_u + 1)):
                    usage_map[u - 1]["is_used"]    = True
                    usage_map[u - 1]["is_spacing"] = True

        available = [
            s
            for s in range(1, total_u - int(height_u) + 2)
            if all(
                u <= total_u and not usage_map[u - 1]["is_used"]
                for u in range(s, s + int(height_u))
            )
        ]

        return {
            "available_positions": available,
            "total_available":     len(available),
            "usage_map":           usage_map,
        }


    @staticmethod
    def calculate_total_u_with_spacing(
        devices: List[Dict],
        total_u: int,
        filter_parent_only: bool = True,
        device_spacing: int = 2,
        min_height_for_spacing: int = 2,
    ) -> Dict:
        """计算包含设备间距的总 U 位占用量。

        基于设备实际物理位置计算间距：只在两个需要间距的设备
        物理相邻（末端与下一个起始之间空隙 < device_spacing）时
        才计入间距，避免对已隔开的设备重复计算。
        """
        valid_devices: List[Dict] = []
        for device in devices:
            if filter_parent_only and device.get("parent_device_id"):
                continue
            start_u = CabinetUCalculator.parse_u_position(device.get("u_position"))
            if start_u is None:
                continue
            h = int(device.get("height_u", device.get("u_height", 1)))
            valid_devices.append({"start_u": start_u, "height_u": h})

        valid_devices.sort(key=lambda d: d["start_u"])

        total_height = 0
        total_spacing = 0
        spacing_device_count = 0
        prev_end_u = None
        prev_needs_spacing = False

        for dev in valid_devices:
            start_u = dev["start_u"]
            h = dev["height_u"]
            end_u = start_u + h - 1
            needs_spacing = h >= min_height_for_spacing

            total_height += h
            if needs_spacing:
                spacing_device_count += 1

            if prev_end_u is not None and prev_needs_spacing and needs_spacing:
                gap = start_u - prev_end_u - 1
                if gap < device_spacing:
                    total_spacing += device_spacing - gap

            prev_end_u = end_u
            prev_needs_spacing = needs_spacing

        total_with_spacing = total_height + total_spacing
        free_u             = total_u - total_with_spacing
        usage_rate         = round(total_with_spacing / total_u * 100, 2) if total_u > 0 else 0
        device_count       = len(valid_devices)
        spacing_count      = spacing_device_count  # 保留用于兼容

        return {
            "total_u":             total_u,
            "total_height":        total_height,
            "total_spacing":       total_spacing,
            "total_with_spacing":  total_with_spacing,
            "free_u":              free_u,
            "usage_rate":          usage_rate,
            "device_count":        device_count,
            "spacing_device_count":spacing_device_count,
            "spacing_count":       spacing_count,
        }

    @staticmethod
    def check_capacity_with_spacing(
        devices: List[Dict],
        total_u: int,
        new_height: int,
        new_device_spacing: int = 2,
        filter_parent_only: bool = True,
        device_spacing: int = 2,
        min_height_for_spacing: int = 2,
    ) -> Dict:
        """检查新增设备后是否超出机柜总 U 位（含间距）。"""
        current = CabinetUCalculator.calculate_total_u_with_spacing(
            devices, total_u, filter_parent_only, device_spacing, min_height_for_spacing
        )

        new_spacing_device_count = current["spacing_device_count"]
        if new_height >= min_height_for_spacing:
            new_spacing_device_count += 1

        new_spacing_count = max(new_spacing_device_count - 1, 0)
        new_total_spacing = new_spacing_count * device_spacing
        new_total         = current["total_height"] + new_height + new_total_spacing
        exceeds           = new_total > total_u
        over_limit        = new_total - total_u if exceeds else 0

        return {
            "exceeds":                  exceeds,
            "over_limit":               over_limit,
            "current_total":            current["total_with_spacing"],
            "new_total":                new_total,
            "total_u":                  total_u,
            "new_height":               new_height,
            "new_spacing":              new_device_spacing,
            "device_count":             current["device_count"],
            "new_device_count":         current["device_count"] + 1,
            "new_spacing_device_count": new_spacing_device_count,
        }


    @staticmethod
    def auto_allocate_u_position(
        devices: List[Dict],
        total_u: int,
        height_u: int,
        strategy: UPositionStrategy = UPositionStrategy.AUTO_BOTTOM_UP,
        constraint: Optional[DeviceConstraint] = None,
        filter_parent_only: bool = True,
        device_spacing: int = 2,
        min_height_for_spacing: int = 2,
    ) -> Optional[int]:
        """自动分配U位，返回推荐起始U位，无可用位置时返回 None。"""
        if constraint is None:
            constraint = DeviceConstraint()

        include_spacing = height_u >= min_height_for_spacing
        free_ranges = CabinetUCalculator.get_free_ranges(
            devices, total_u, filter_parent_only,
            include_spacing, device_spacing, min_height_for_spacing,
        )
        suitable = [r for r in free_ranges if r.height >= height_u]
        if not suitable:
            return None

        suitable = CabinetUCalculator._apply_constraints(suitable, height_u, constraint, total_u)
        if not suitable:
            return None

        return CabinetUCalculator._select_position_by_strategy(suitable, height_u, strategy, constraint)

    @staticmethod
    def _apply_constraints(
        ranges: List[UPositionRange],
        height_u: int,
        constraint: DeviceConstraint,
        total_u: int,
    ) -> List[UPositionRange]:
        """根据约束条件过滤可用区间。"""
        filtered: List[UPositionRange] = []
        for r in ranges:
            if constraint.min_u_position and r.start < constraint.min_u_position:
                continue
            if constraint.max_u_position and r.end > constraint.max_u_position:
                continue
            if constraint.avoid_positions and any(r.contains(p) for p in constraint.avoid_positions):
                continue
            if constraint.must_align_bottom and (r.start - 1) % height_u != 0:
                continue
            if constraint.must_align_top:
                has_aligned_pos = any(
                    (total_u - k * height_u - height_u + 1) >= r.start
                    and (total_u - k * height_u) <= r.end
                    for k in range(0, (total_u // height_u) + 1)
                )
                if not has_aligned_pos:
                    continue
            filtered.append(r)

        if constraint.preferred_positions:
            preferred: List[UPositionRange] = []
            for pos in constraint.preferred_positions:
                for r in filtered:
                    if r.contains(pos) and pos + height_u - 1 <= r.end:
                        preferred.append(r)
                        break
            if preferred:
                return preferred

        return filtered

    @staticmethod
    def _select_position_by_strategy(
        ranges: List[UPositionRange],
        height_u: int,
        strategy: UPositionStrategy,
        constraint: DeviceConstraint,
    ) -> int:
        """根据策略从候选区间中选择起始 U 位。

        修复：AUTO_TOP_DOWN 原来返回 ranges[-1].start，
        这是最后一个空闲区间的起始位置（即区间底部），
        对于"从顶向下"分配，应该返回区间末端倒推：
            end - height_u + 1
        """
        if not ranges:
            raise ValueError("没有可用的U位区间")

        if strategy == UPositionStrategy.AUTO_BOTTOM_UP:
            return ranges[0].start

        elif strategy == UPositionStrategy.AUTO_TOP_DOWN:
            last = ranges[-1]
            return last.end - height_u + 1

        elif strategy == UPositionStrategy.AUTO_BEST_FIT:
            best = min(ranges, key=lambda r: r.height)
            return best.start

        elif strategy == UPositionStrategy.AUTO_FIRST_FIT:
            return ranges[0].start

        return ranges[0].start


    @staticmethod
    def batch_allocate_devices(
        devices_to_allocate: List[Dict],
        existing_devices: List[Dict],
        total_u: int,
        default_strategy: UPositionStrategy = UPositionStrategy.AUTO_BOTTOM_UP,
        allow_partial: bool = False,
        filter_parent_only: bool = True,
        device_spacing: int = 2,
        min_height_for_spacing: int = 2,
    ) -> Dict:
        """批量为设备分配U位（按优先级排序，支持全量回滚）。"""
        allocated: List[Dict] = []
        failed:    List[Dict] = []
        working = list(existing_devices)

        for device in sorted(devices_to_allocate, key=lambda d: d.get("priority", 999)):
            h        = device.get("height_u", device.get("u_height", 1))
            strategy = device.get("strategy", default_strategy)
            u        = CabinetUCalculator.auto_allocate_u_position(
                devices=working, total_u=total_u, height_u=h,
                strategy=strategy, constraint=device.get("constraint"),
                filter_parent_only=filter_parent_only,
                device_spacing=device_spacing,
                min_height_for_spacing=min_height_for_spacing,
            )
            if u is not None:
                dev = {**device, "u_position": u}
                allocated.append(dev)
                working.append(dev)
            else:
                failed.append({"device": device, "reason": "无法分配U位"})
                if not allow_partial:
                    return {
                        "success":   False,
                        "allocated": [],
                        "failed": [{"device": d, "reason": "部分分配失败，已回滚"} for d in devices_to_allocate],
                        "message": "分配失败，已全量回滚",
                    }

        msg = f"成功分配 {len(allocated)} 个设备"
        if failed:
            msg += f"，失败 {len(failed)} 个"
        return {"success": not failed, "allocated": allocated, "failed": failed, "message": msg}


    @staticmethod
    def optimize_cabinet_layout(
        devices: List[Dict],
        total_u: int,
        device_spacing: int = 2,
        min_height_for_spacing: int = 2,
        filter_parent_only: bool = True,
    ) -> Dict:
        """优化机柜布局：对所有可移动设备重新紧凑排列以最大化空间利用率。

        策略说明：
        - 没有 u_position 的设备视为"待分配"，直接参与重排
        - 有 u_position 的设备视为已定位，保留原位不动
        优化方向：按设备高度降序（大设备优先），用 BEST_FIT 策略填充空隙
        """
        fixed:    List[Dict] = []
        movable:  List[Dict] = []
        for device in devices:
            if filter_parent_only and device.get("parent_device_id"):
                continue
            if CabinetUCalculator.parse_u_position(device.get("u_position")) is not None:
                fixed.append(device)
            else:
                movable.append(device)

        movable_sorted = sorted(
            movable,
            key=lambda d: d.get("height_u", d.get("u_height", 1)),
            reverse=True,
        )

        working    = list(fixed)
        optimized: List[Dict] = []

        for device in movable_sorted:
            h = device.get("height_u", device.get("u_height", 1))
            u = CabinetUCalculator.auto_allocate_u_position(
                devices=working, total_u=total_u, height_u=h,
                strategy=UPositionStrategy.AUTO_BEST_FIT,
                filter_parent_only=filter_parent_only,
                device_spacing=device_spacing,
                min_height_for_spacing=min_height_for_spacing,
            )
            if u is not None:
                dev = {**device, "u_position": u}
                optimized.append(dev)
                working.append(dev)
            else:
                optimized.append(device)

        all_devices = fixed + optimized
        usage = CabinetUCalculator.calculate_total_u_with_spacing(
            all_devices, total_u, filter_parent_only, device_spacing, min_height_for_spacing
        )

        return {
            "success":           True,
            "optimized_devices": all_devices,
            "usage":             usage,
            "message":           f"优化完成，空间利用率：{usage['usage_rate']}%",
        }


    @staticmethod
    def validate_cabinet_capacity(
        devices: List[Dict],
        total_u: int,
        device_spacing: int = 2,
        min_height_for_spacing: int = 2,
        max_usage_rate: float = 90.0,
        filter_parent_only: bool = True,
    ) -> Dict:
        """验证机柜容量与规划合理性，返回 warnings 和 recommendations。"""
        usage    = CabinetUCalculator.calculate_total_u_with_spacing(
            devices, total_u, filter_parent_only, device_spacing, min_height_for_spacing
        )
        warnings:       List[str] = []
        recommendations:List[str] = []

        if usage["usage_rate"] > max_usage_rate:
            warnings.append(f'空间使用率 {usage["usage_rate"]}% 超过阈值 {max_usage_rate}%')
            recommendations.append("建议优化机柜布局或清理不必要的设备")

        if usage["free_u"] < 4:
            warnings.append(f'剩余空间仅 {usage["free_u"]}U，可能影响未来扩展')
            recommendations.append("建议预留至少 4U 以备将来扩展")

        if usage["total_with_spacing"] > 0:
            spacing_ratio = usage["total_spacing"] / usage["total_with_spacing"] * 100
            if spacing_ratio > 30:
                warnings.append(f"设备间距占用比例较高：{spacing_ratio:.1f}%")
                recommendations.append("建议检查设备间距配置是否合理")

        valid   = not warnings
        message = "验证通过" if valid else f"存在 {len(warnings)} 个警告"

        return {
            "valid":           valid,
            "usage":           usage,
            "warnings":        warnings,
            "recommendations": recommendations,
            "message":         message,
        }


    @staticmethod
    def filter_valid_devices(
        devices: List[Dict], total_u: int, filter_parent_only: bool = True
    ) -> Tuple[List[Dict], List[Dict]]:
        """过滤有效设备和无效设备，返回 (valid_list, invalid_list)。"""
        valid:   List[Dict] = []
        invalid: List[Dict] = []
        for device in devices:
            if filter_parent_only and device.get("parent_device_id"):
                invalid.append({**device, "invalid_reason": "子设备"})
                continue
            start_u = CabinetUCalculator.parse_u_position(device.get("u_position"))
            if start_u is None:
                invalid.append({**device, "invalid_reason": "U位为空"})
            elif not CabinetUCalculator.is_valid_u_position(start_u, total_u):
                invalid.append({**device, "invalid_reason": f"U位超出范围（{start_u} > {total_u}）"})
            else:
                valid.append(device)
        return valid, invalid


class DeviceFieldMapper:
    """设备字段映射工具，统一处理不同命名约定的字段。"""

    FIELD_MAPPINGS: Dict[str, List[str]] = {
        "u_position":      ["u_position", "rack_position"],
        "height_u":        ["height_u", "u_height"],
        "device_name":     ["device_name", "name"],
        "device_type":     ["device_type", "type"],
        "device_model":    ["device_model", "model"],
        "cabinet_id":      ["cabinet_id"],
        "parent_device_id":["parent_device_id"],
    }

    @staticmethod
    def get_field_value(device: Dict, field_name: str, default=None):
        """获取字段值，支持多个别名。"""
        if field_name in device:
            return device[field_name]
        for alias in DeviceFieldMapper.FIELD_MAPPINGS.get(field_name, []):
            if alias in device:
                return device[alias]
        return default

    @staticmethod
    def normalize_device_fields(device: Dict) -> Dict:
        """将设备字典的字段名统一为标准命名。"""
        normalized: Dict = {}
        for field_name, aliases in DeviceFieldMapper.FIELD_MAPPINGS.items():
            for alias in aliases:
                if alias in device:
                    normalized[field_name] = device[alias]
                    break
        for k, v in device.items():
            if k not in normalized:
                normalized[k] = v
        return normalized

    @staticmethod
    def normalize_device_list(devices: List[Dict]) -> List[Dict]:
        """标准化设备列表中的全部字段名。"""
        return [DeviceFieldMapper.normalize_device_fields(d) for d in devices]
