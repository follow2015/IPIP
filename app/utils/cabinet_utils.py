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
    AUTO_BEST_FIT   = "auto_best_fit"    # 最小空隙优先（减少碎片，布局优化在用）


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
    def _iter_effective(devices: List[Dict], filter_parent_only: bool = True):
        """迭代「有效设备」：排除机箱子节点与软删（回收站）设备。

        全模块**唯一**的设备口径——占用统计、冲突检测、分配都必须经由此处。
        此前各方法各自 `if parent_device_id: continue`，且都漏了软删过滤，
        于是出现「机柜概览显示有空位、自动分配却说空间不足」这类口径分裂。

        Args:
            devices: 原始设备字典列表。
            filter_parent_only: True 时排除机箱子节点（子设备不独立占 U 位）。

        Yields:
            有效设备字典。
        """
        for device in devices:
            if filter_parent_only and device.get("parent_device_id"):
                continue
            if device.get("deleted_at") is not None:
                continue
            yield device

    @staticmethod
    def calculate_used_u_positions(
        devices: List[Dict], total_u: int, filter_parent_only: bool = True
    ) -> Set[int]:
        """计算已占用的U位集合。"""
        used: Set[int] = set()
        for device in CabinetUCalculator._iter_effective(devices, filter_parent_only):
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

        for device in CabinetUCalculator._iter_effective(devices, filter_parent_only):
            device_id = device.get("id")
            if exclude_device_id and device_id == exclude_device_id:
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
        for device in CabinetUCalculator._iter_effective(devices, filter_parent_only):
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
            for device in CabinetUCalculator._iter_effective(devices, filter_parent_only):
                start_u = CabinetUCalculator.parse_u_position(device.get("u_position"))
                if start_u is None:
                    continue
                if not CabinetUCalculator.is_valid_u_position(start_u, total_u):
                    continue
                h = int(device.get("height_u", device.get("u_height", 1)))
                end_u = min(start_u + h - 1, total_u)
                lo, hi = start_u, end_u
                if h >= min_height_for_spacing and device_spacing > 0:
                    lo = max(1, start_u - device_spacing)
                    hi = min(end_u + device_spacing, total_u)
                expanded.append(UPositionRange(lo, hi))
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
    def get_candidate_positions(
        devices: List[Dict],
        total_u: int,
        height_u: int,
        device_spacing: int = 2,
        filter_parent_only: bool = True,
        min_height_for_spacing: int = 2,
    ) -> List[int]:
        """枚举全部合法起始 U 位（已通过重叠与**双向**间距校验）。

        这是「自动分配」与「可用位置列表」的共同基础：先枚举合法位置，再按策略
        挑选。原实现是「先算空闲区间、再由区间端点推导位置」，间距只在区间层面
        生效，于是 AUTO_TOP_DOWN 会把设备贴到相邻设备身上（间距静默失效）。

        间距语义：新设备与任一已有设备之间，只要**其中一方**高度达到
        min_height_for_spacing，两者间就必须留出 >= device_spacing 的空隙。

        Args:
            devices: 机柜内已有设备字典列表。
            total_u: 机柜总 U 数。
            height_u: 待放置设备高度（U）。
            device_spacing: 要求的设备间距（U），0 表示不要求间距。
            filter_parent_only: True 时忽略机箱子节点。
            min_height_for_spacing: 触发间距要求的最小设备高度。

        Returns:
            升序的合法起始 U 位列表；无可用位置返回空列表。
        """
        h = int(height_u)
        if h < 1 or total_u < 1 or h > total_u:
            return []

        occupied: List[Tuple[int, int, int]] = []   # (start, end, height)
        for device in CabinetUCalculator._iter_effective(devices, filter_parent_only):
            start_u = CabinetUCalculator.parse_u_position(device.get("u_position"))
            if start_u is None or not CabinetUCalculator.is_valid_u_position(start_u, total_u):
                continue
            d_h = int(device.get("height_u", device.get("u_height", 1)))
            occupied.append((start_u, min(start_u + d_h - 1, total_u), d_h))

        new_needs_spacing = h >= min_height_for_spacing
        candidates: List[int] = []
        for s in range(1, total_u - h + 2):
            end = s + h - 1
            for (ds, de, dh) in occupied:
                if s <= de and ds <= end:                      # 区间重叠
                    break
                if device_spacing > 0 and (new_needs_spacing or dh >= min_height_for_spacing):
                    gap = (s - de - 1) if s > de else (ds - end - 1)
                    if gap < device_spacing:                   # 间距不足
                        break
            else:
                candidates.append(s)
        return candidates

    @staticmethod
    def get_available_u_positions(
        devices: List[Dict],
        total_u: int,
        height_u: int = 1,
        device_spacing: int = 2,
        filter_parent_only: bool = True,
        min_height_for_spacing: int = 2,
    ) -> Dict:
        """获取可放置指定高度设备的起始U位列表及使用映射。

        available_positions 直接取自 `get_candidate_positions`，与自动分配同源，
        保证「界面看到可选的」与「点自动分配得到的」永远一致。

        usage_map 中的 is_spacing 仅用于界面标注保护区，最终可否放置一律以
        available_positions 为准（保护区判定无法表达"新设备自身高度"这一变量）。
        """
        used_positions = CabinetUCalculator.calculate_used_u_positions(
            devices, total_u, filter_parent_only
        )

        usage_map = [
            {"u_position": u, "is_used": u in used_positions, "is_spacing": False}
            for u in range(1, total_u + 1)
        ]

        for device in CabinetUCalculator._iter_effective(devices, filter_parent_only):
            start_u = CabinetUCalculator.parse_u_position(device.get("u_position"))
            if start_u is None:
                continue
            d_height = int(device.get("height_u", device.get("u_height", 1)))
            end_u    = start_u + d_height - 1
            if d_height >= min_height_for_spacing and device_spacing > 0:
                lo = max(1, start_u - device_spacing)
                hi = min(end_u + device_spacing, total_u)
                for u in range(lo, hi + 1):
                    if not usage_map[u - 1]["is_used"]:
                        usage_map[u - 1]["is_used"]    = True
                        usage_map[u - 1]["is_spacing"] = True

        available = CabinetUCalculator.get_candidate_positions(
            devices, total_u, height_u, device_spacing,
            filter_parent_only, min_height_for_spacing,
        )

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
        for device in CabinetUCalculator._iter_effective(devices, filter_parent_only):
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
        """自动分配U位，返回推荐起始U位，无可用位置时返回 None。

        先由 get_candidate_positions 枚举出所有「不与已有设备重叠 且 满足双向
        间距」的位置，再按策略挑选——因此任何策略都不可能返回违规位置。
        """
        if constraint is None:
            constraint = DeviceConstraint()

        candidates = CabinetUCalculator.get_candidate_positions(
            devices, total_u, height_u, device_spacing,
            filter_parent_only, min_height_for_spacing,
        )
        if not candidates:
            return None

        candidates = CabinetUCalculator._apply_constraints(
            candidates, height_u, constraint, total_u
        )
        if not candidates:
            return None

        return CabinetUCalculator._select_position_by_strategy(
            candidates, height_u, strategy, devices, filter_parent_only, total_u
        )

    @staticmethod
    def _apply_constraints(
        positions: List[int],
        height_u: int,
        constraint: DeviceConstraint,
        total_u: int,
    ) -> List[int]:
        """根据约束条件过滤候选起始位。"""
        filtered: List[int] = []
        for s in positions:
            end = s + height_u - 1
            if constraint.min_u_position and s < constraint.min_u_position:
                continue
            if constraint.max_u_position and end > constraint.max_u_position:
                continue
            if constraint.avoid_positions and any(s <= p <= end for p in constraint.avoid_positions):
                continue
            if constraint.must_align_bottom and (s - 1) % height_u != 0:
                continue
            if constraint.must_align_top and (total_u - end) % height_u != 0:
                continue
            filtered.append(s)

        if constraint.preferred_positions:
            preferred = [
                s for s in filtered
                if any(s <= p <= s + height_u - 1 for p in constraint.preferred_positions)
            ]
            if preferred:
                return preferred

        return filtered

    @staticmethod
    def _select_position_by_strategy(
        positions: List[int],
        height_u: int,
        strategy: UPositionStrategy,
        devices: List[Dict],
        filter_parent_only: bool = True,
        total_u: int = 0,
    ) -> int:
        """根据策略从合法候选位中挑选起始 U 位。

        入参是**已通过重叠与间距校验的起始位列表**，策略只负责"挑哪一个"，
        不再自行推导位置。历史 bug 正是策略层用区间端点推导位置，导致
        AUTO_TOP_DOWN 把设备贴到相邻设备身上、间距静默失效。
        """
        if not positions:
            raise ValueError("没有可用的U位区间")

        if strategy == UPositionStrategy.AUTO_TOP_DOWN:
            return max(positions)

        if strategy == UPositionStrategy.AUTO_BEST_FIT:
            spans: List[Tuple[int, int]] = []
            for device in CabinetUCalculator._iter_effective(devices, filter_parent_only):
                start_u = CabinetUCalculator.parse_u_position(device.get("u_position"))
                if start_u is None:
                    continue
                d_h = int(device.get("height_u", device.get("u_height", 1)))
                spans.append((start_u, start_u + d_h - 1))

            def _slack(s: int) -> int:
                end = s + height_u - 1
                left  = min((s - de - 1 for (_ds, de) in spans if de < s), default=s - 1)
                right = min((ds - end - 1 for (ds, _de) in spans if ds > end),
                            default=total_u - end)
                return left + right

            return min(positions, key=lambda s: (_slack(s), s))

        return min(positions)


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
        for device in CabinetUCalculator._iter_effective(devices, filter_parent_only):
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
            if device.get("deleted_at") is not None:
                invalid.append({**device, "invalid_reason": "回收站设备"})
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
