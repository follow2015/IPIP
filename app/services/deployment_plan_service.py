# -*- coding: utf-8 -*-
"""上架方案查询服务（只读，Phase 1 纯推荐零副作用）。

输入机房/台数/U高/单台功率/单台带宽/服务器端口速率，输出一套推荐方案：
推荐机柜 + 起始 U 位（复用 CabinetUCalculator 含间距校验）→ 同机房网段挑
空闲 IP（排除网关/网络号/广播）→ 交换机空闲端口（速率能力匹配，接入优先）→
每端口限速建议 → 上行出口信息。

拍板口径（docs/上架规划.md 2026-09-09，同日二次修订）：
- 端口不建机柜↔交换机映射，全机房扫描；无匹配空闲端口 → 阻断；
  只有核心交换机有匹配端口 → 提示不阻断；优先接入交换机。
- **速率匹配**（替代介质匹配）：服务器端口速率（如 1000M）≥ 需求即匹配；
  speed 列解析（1G→1000）+ 接口前缀兜底（AUTO 的 10GE 口按 10000 计）；
  count 缺省 = 容量模式（"还能上多少台"）。
- 电力仅参考：超出机柜 total_power 合计 / 未录入 → 仅 warnings 不阻断。
- 容量不足不静默截断：输出「还能放 X 台 / 差 Y 台」+ 瓶颈维度。
- 同批次就近分配：同机柜优先，其次 cabinet_number 相邻的机柜窗口。
- IP 只建议不锁定；带宽需求人工输入（必填）。

本服务不写库、不下发配置——写动作属 Phase 2（验证推荐准确性后再做）。
"""
import re
from typing import Any, Dict, List, Optional

from extensions import db

from app.utils.logging import get_logger

logger = get_logger(__name__)

_DEVICE_SPACING = 2
_MIN_HEIGHT_FOR_SPACING = 2

_INTERFACE_CLASS_MBPS = (
    ("400ge", 400_000), ("200ge", 200_000), ("100ge", 100_000),
    ("40ge", 40_000), ("25ge", 25_000), ("10ge", 10_000),
    ("xgigabit", 10_000), ("xge", 10_000),
    ("gigabitethernet", 1_000), ("10gigabitethernet", 10_000),
    ("fastethernet", 100), ("ge", 1_000), ("meth", 1_000),
)

_VIRTUAL_PORT_TYPES = {"vlan", "eth-trunk", "loopback", "null", "tunnel",
                       "nve", "stack", "css", "port-channel"}

class DeploymentPlanError(Exception):
    """输入不合法（阻断级，直接回给调用方）。"""


def normalize_port_speed(raw: Any) -> int:
    """端口速率入参（"1000m"/"1g"/"10000m"/"10g"/1000）→ Mbps；非法抛错。"""
    from app.services.port_matching_engine import PortMatchingEngine

    if raw is None or str(raw).strip() == "":
        raise DeploymentPlanError("端口速率必填（如 1000m / 1g / 10g）")
    mbps = PortMatchingEngine._parse_speed_to_mbps(str(raw))
    if not mbps or mbps <= 0:
        raise DeploymentPlanError(
            f"端口速率无法识别: {raw!r}（支持 100M/1G/1000M/10G/25G/40G/100G/400G）"
        )
    return mbps


def _port_capability_mbps(port_type: Optional[str], port_name: Optional[str],
                          speed: Optional[str]) -> Optional[int]:
    """交换机端口速率能力（Mbps）：speed 列解析优先，接口前缀兜底。

    speed='AUTO'（空闲口未协商）无数字 → 解析 None → 按接口类别上限推断
    （10GE 口按 10000 计）；两者都取不到 → None（速率无法确认）。
    """
    from app.services.port_matching_engine import PortMatchingEngine

    parsed = PortMatchingEngine._parse_speed_to_mbps(speed) if speed else None
    if parsed:
        return parsed

    raw_prefix = _interface_class_prefix(port_type, port_name)
    if raw_prefix:
        prefix = raw_prefix.lower()
        best: Optional[tuple] = None
        for cls, mbps in _INTERFACE_CLASS_MBPS:
            if prefix.startswith(cls) and (best is None or len(cls) > len(best[0])):
                best = (cls, mbps)
        if best:
            return best[1]
    return None


def _interface_class_prefix(port_type: Optional[str], port_name: Optional[str]) -> Optional[str]:
    """提取接口类别前缀（保留原始大小写，供展示）：优先 port_type，其次 port_name 前缀。

    "10GE1/0/1" → "10GE"；"GigabitEthernet0/0/1" → "GigabitEthernet"；
    port_type="40GE" → "40GE"。提取不出返回 None。
    """
    if port_type:
        pt = str(port_type).strip()
        if pt and any(ch.isalpha() for ch in pt):
            return pt
    if port_name:
        m = re.match(r"^([0-9]*[A-Za-z][A-Za-z-]*)", str(port_name).strip())
        if m:
            return m.group(1)
    return None


def _is_virtual_port(port_type: Optional[str], port_name: Optional[str]) -> bool:
    """虚拟/管理接口（VLANIF/Eth-Trunk/LoopBack/NULL 等）不参与物理端口推荐。"""
    from app.models.network_port import NetworkPort

    if NetworkPort.is_logical_port(port_name):
        return True
    if port_type:
        return str(port_type).strip().lower() in _VIRTUAL_PORT_TYPES
    return False


def _cabinet_fits(cabinet, u_height: int, existing: List[Dict[str, Any]]) -> int:
    """机柜还能放几台 u_height 高的设备（逐台模拟，含间距）。"""
    from app.utils.cabinet_utils import CabinetUCalculator

    sim = list(existing)
    fits = 0
    while True:
        start = CabinetUCalculator.auto_allocate_u_position(
            devices=sim, total_u=cabinet.total_u, height_u=u_height,
            device_spacing=_DEVICE_SPACING,
            min_height_for_spacing=_MIN_HEIGHT_FOR_SPACING,
            filter_parent_only=False,
        )
        if start is None:
            return fits
        fits += 1
        sim.append({"u_position": start, "height_u": u_height})


def _cabinet_existing_devices(cabinet) -> List[Dict[str, Any]]:
    return [
        {"u_position": d.u_position, "height_u": d.height_u or 1}
        for d in cabinet._parent_devices
    ]


def _room_u_capacity(room_id: int, u_height: int) -> tuple:
    """机房 U 位容量：[(cabinet, fits, existing_devices), ...]，按编号排序。"""
    from app.core.enums import CabinetStatus
    from app.models.cabinet import Cabinet

    cabinets = (
        Cabinet.query.filter(
            Cabinet.room_id == room_id,
            Cabinet.status.in_([int(CabinetStatus.AVAILABLE), int(CabinetStatus.IN_USE)]),
        )
        .order_by(Cabinet.cabinet_number)
        .all()
    )
    out = []
    for cab in cabinets:
        existing = _cabinet_existing_devices(cab)
        out.append((cab, _cabinet_fits(cab, u_height, existing), existing))
    return out


def _room_power_headroom(cabinets: List, power_per_unit: int) -> tuple:
    """电力参考容量：总和 + 未录入机柜数。未录入不阻断，只计数。"""
    headroom = 0
    unrecorded = 0
    for cab, _, _ in cabinets:
        if not cab.total_power or cab.total_power <= 0:
            unrecorded += 1
            continue
        headroom += max(0, (cab.total_power - (cab.used_power or 0)) // power_per_unit)
    return headroom, unrecorded


def _collect_room_ports(room_id: int, speed_mbps: int, visible_switch_ids=None) -> Dict[str, Any]:
    """全机房扫描交换机空闲端口（速率能力 ≥ 需求即匹配）。

    Returns:
        {"access": [(port, switch)], "core": [...],
         "virtual": int, "below": {label: cnt}, "unknown_speed": {label: cnt},
         "switches": {...}}
    """
    from app.models.device import Device
    from app.models.network_port import NetworkPort

    rows = (
        NetworkPort.query
        .join(Device, NetworkPort.device_id == Device.id)
        .filter(
            Device.device_type == "network",
            Device.device_subtype == "switch",
            Device.deleted_at.is_(None),
            NetworkPort.usage_status == "free",
            NetworkPort.lag_group_id.is_(None),
            Device.cabinet_id.isnot(None),
        )
        .all()
    )

    from app.models.cabinet import Cabinet
    cabinet_room = {
        c.id: c.room_id
        for c in Cabinet.query.filter_by(room_id=room_id).all()
    }

    access: list = []
    core: list = []
    virtual = 0
    below: Dict[str, int] = {}
    unknown_speed: Dict[str, int] = {}
    switch_meta: Dict[int, Dict[str, Any]] = {}

    for port in rows:
        device = port.device
        if device is None or device.cabinet_id not in cabinet_room:
            continue
        if visible_switch_ids is not None and device.id not in visible_switch_ids:
            continue  # 数据域隔离：不可见交换机的端口不进推荐池
        if _is_virtual_port(port.port_type, port.port_name):
            virtual += 1
            continue
        cap = _port_capability_mbps(port.port_type, port.port_name, port.speed)
        if cap is None:
            label = _interface_class_prefix(port.port_type, port.port_name) \
                or str(port.speed or "(速率未录入)")
            unknown_speed[label] = unknown_speed.get(label, 0) + 1
            continue
        if cap < speed_mbps:
            label = f"{_interface_class_prefix(port.port_type, port.port_name) or port.speed or '?'}({port.speed or cap})"
            below[label] = below.get(label, 0) + 1
            continue
        meta = switch_meta.get(device.id)
        if meta is None:
            ext = device.switch_ext
            meta = {
                "device": device,
                "is_core": bool(ext and ext.switch_role == 0),
            }
            switch_meta[device.id] = meta
        (core if meta["is_core"] else access).append((port, device))

    return {"access": access, "core": core, "virtual": virtual,
            "below": below, "unknown_speed": unknown_speed,
            "switches": switch_meta}


def _format_port_breakdown(ports: Dict[str, Any]) -> str:
    """把未匹配端口池格式化成可行动的阻断说明片段。"""
    parts = []
    if ports["below"]:
        detail = "、".join(f"{k}×{v}" for k, v in sorted(
            ports["below"].items(), key=lambda x: -x[1]))
        parts.append(f"{sum(ports['below'].values())} 个空闲端口速率低于需求（{detail}）")
    if ports["unknown_speed"]:
        detail = "、".join(f"{k}×{v}" for k, v in sorted(
            ports["unknown_speed"].items(), key=lambda x: -x[1]))
        parts.append(
            f"{sum(ports['unknown_speed'].values())} 个空闲端口速率无法确认"
            f"（{detail}），需人工核对"
        )
    if ports["virtual"]:
        parts.append(f"另有 {ports['virtual']} 个虚拟接口已排除（VLANIF/Eth-Trunk/LoopBack 等）")
    return "；".join(parts)


def _room_free_ips(room_id: int, needed: int) -> Dict[str, Any]:
    """按网段挑空闲 IP：状态 UNUSED 优先、INACTIVE 兜底，排除网关/网络号/广播。

    Returns:
        {"ips": [...], "total_free": int, "subnet_count": int, "short": int}
    """
    from app.core.enums import IPStatus
    from app.models.ip_model import IPManager, ip_to_int
    from app.models.switch_route import IPNetwork

    subnets = IPNetwork.query.filter_by(room_id=room_id).all()
    if not subnets:
        return {"ips": [], "total_free": 0, "subnet_count": 0, "short": needed}

    wanted_status = (int(IPStatus.UNUSED), int(IPStatus.INACTIVE))
    rows = (
        IPManager.query
        .filter(IPManager.room_id == room_id, IPManager.status.in_(wanted_status))
        .all()
    )

    picked: List[str] = []
    total_free = 0
    for subnet in subnets:
        if subnet.network_int is None or not subnet.prefix:
            continue
        prefix = int(subnet.prefix)
        if prefix < 8 or prefix > 32:
            continue
        size = 1 << (32 - prefix)
        lo = subnet.network_int + 1          # 排除网络号
        hi = subnet.network_int + size - 2   # 排除广播地址
        if lo > hi:
            continue
        gateway_int = ip_to_int(subnet.gateway) if subnet.gateway else None
        in_range = [
            r for r in rows
            if r.ip_int is not None and lo <= r.ip_int <= hi
            and (gateway_int is None or r.ip_int != gateway_int)
        ]
        in_range.sort(key=lambda r: (r.status != int(IPStatus.UNUSED), r.ip_int))
        total_free += len(in_range)
        for r in in_range:
            if len(picked) < needed:
                picked.append(r.ip_address)

    return {
        "ips": picked,
        "total_free": total_free,
        "subnet_count": len(subnets),
        "short": max(0, needed - len(picked)),
    }


def _uplink_info(switch_ids: List[int]) -> List[Dict[str, Any]]:
    """批内交换机的上行出口信息（容量未登记 → 上层据此 warning）。"""
    from app.models.device import Device
    from app.models.network_port import NetworkPort

    out = []
    for sid in switch_ids:
        device = db.session.get(Device, sid)
        ext = device.switch_ext if device else None
        uplink_ports = []
        if ext and ext.uplink_port_ids:
            uplink_ports = [
                p.port_name
                for p in NetworkPort.query.filter(NetworkPort.id.in_(list(ext.uplink_port_ids))).all()
            ]
        out.append({
            "switch_id": sid,
            "switch_name": device.device_name if device else str(sid),
            "uplink_device_id": ext.uplink_device_id if ext else None,
            "uplink_ports": uplink_ports,
            "capacity_registered": False,  # connections.bandwidth 自由文本，无法解析
        })
    return out


def _pick_cabinet_window(cabinets: List[tuple], need: int) -> List[tuple]:
    """就近分配：在 cabinet_number 有序序列上找总 fits ≥ need 的最短连续窗口。

    窗口最短优先（机柜集中），平局取起始编号靠前。need 已被上游 min 截断。
    """
    if need <= 0:
        return []
    n = len(cabinets)
    best: Optional[tuple] = None  # (窗口长度, 起始下标)
    for i in range(n):
        acc = 0
        for j in range(i, n):
            acc += cabinets[j][1]
            if acc >= need:
                if best is None or (j - i + 1) < best[0]:
                    best = (j - i + 1, i)
                break
    if best is None:
        return []
    _, start = best
    return cabinets[start: start + best[0]]


def build_plan(
    *,
    count: Optional[int],
    bandwidth_mbps: Optional[int],
    port_speed_raw: Any,
    u_height: int = 2,
    power_per_unit: int = 750,
    room_id: Optional[int] = None,
    visible_switch_ids=None,
) -> Dict[str, Any]:
    """生成上架推荐方案（只读）。

    Args:
        count: 本次上架台数（≥1）；None = 容量模式（"还能上多少台"），
               返回 placeable 而不出明细分配
        bandwidth_mbps: 单台带宽需求（可选；None = 不给限速建议，
               出口判定跳过，仅提示）
        port_speed_raw: 服务器端口速率（必填，如 "1000m"/"1g"/"10g"）
        u_height: 单台 U 高（默认 2）
        power_per_unit: 单台额定功率 W（默认 750，仅参考）
        room_id: 机房 ID（可选；缺省则在全部机房中择优）
        visible_switch_ids: 数据域可见交换机集合（None=不限制）
    """
    speed_mbps = normalize_port_speed(port_speed_raw)
    if bandwidth_mbps is not None and (not int(bandwidth_mbps) or int(bandwidth_mbps) <= 0):
        raise DeploymentPlanError("单台带宽需求 bandwidth_mbps 须为正整数（不填=不给限速建议）")
    if count is not None and (not int(count) or int(count) < 1):
        raise DeploymentPlanError("台数 count 须 ≥ 1（缺省=查询机房还能上多少台）")
    bandwidth_mbps = int(bandwidth_mbps)
    capacity_mode = count is None
    count = int(count) if count is not None else 0
    u_height = max(1, int(u_height or 2))
    power_per_unit = max(1, int(power_per_unit or 750))

    from app.models.room import Room

    if room_id is not None:
        rooms = Room.query.filter_by(id=room_id).all()
        if not rooms:
            raise DeploymentPlanError(f"机房不存在: {room_id}")
    else:
        rooms = Room.query.order_by(Room.id).all()
        if not rooms:
            raise DeploymentPlanError("系统中无机房数据")

    warnings: List[Dict[str, str]] = []
    room_evals = []
    for room in rooms:
        cabinets = _room_u_capacity(room.id, u_height)
        u_total = sum(f for _, f, _ in cabinets)
        if u_total <= 0:
            continue
        ports = _collect_room_ports(room.id, speed_mbps, visible_switch_ids)
        port_total = len(ports["access"]) + len(ports["core"])
        power_head, power_unrecorded = _room_power_headroom(cabinets, power_per_unit)
        dims = {"U 位": u_total, "匹配空闲端口": port_total}
        placeable = min(dims.values())
        bottleneck = min(dims, key=dims.get)
        room_evals.append({
            "room": room, "cabinets": cabinets, "ports": ports,
            "placeable": placeable, "u_total": u_total,
            "port_total": port_total, "power_headroom": power_head,
            "power_unrecorded": power_unrecorded, "bottleneck": bottleneck,
            "dims": dims,
        })

    if not room_evals:
        return {
            "supported": True, "blocked": True,
            "block_reason": "所有机房均无可用 U 位空位",
            "warnings": warnings, "requested": count,
            "placeable": 0, "diff": count, "assignments": [],
        }

    room_evals.sort(key=lambda e: (-e["placeable"], e["room"].id))
    chosen = room_evals[0]
    room = chosen["room"]

    for ev in room_evals[1:]:
        warnings.append({
            "code": "room_not_chosen",
            "message": f"机房 {ev['room'].name} 可放 {ev['placeable']} 台，未选用",
        })

    placeable = chosen["placeable"]
    diff = max(0, count - placeable) if not capacity_mode else 0
    to_place = min(count, placeable)

    if capacity_mode:
        if placeable <= 0:
            breakdown = _format_port_breakdown(chosen["ports"])
            reason = (f"机房「{room.name}」当前无法再上架 {u_height}U/"
                      f"{speed_mbps}M 端口的服务器（U 位余量 {chosen['u_total']}、"
                      f"匹配空闲端口 {chosen['port_total']}）")
            if breakdown:
                reason += f"。{breakdown}"
            return {
                "supported": True, "blocked": True,
                "block_reason": reason, "capacity_query": True,
                "warnings": warnings, "requested": None,
                "placeable": 0, "diff": 0, "assignments": [],
            }
        return {
            "supported": True, "blocked": False,
            "capacity_query": True, "requested": None,
            "placeable": placeable, "diff": 0, "assignments": [],
            "room": {"id": room.id, "name": room.name},
            "summary": {
                "u_height": u_height,
                "power_per_unit": power_per_unit,
                "bandwidth_mbps": bandwidth_mbps,
                "port_speed_mbps": speed_mbps,
                "u_total": chosen["u_total"],
                "matched_port_total": chosen["port_total"],
                "bottleneck": chosen["bottleneck"],
                "power_headroom": chosen["power_headroom"],
            },
            "warnings": warnings,
            "note": "容量模式：placeable 即该机房还能上的台数；明细分配请指定台数查询",
        }

    if chosen["port_total"] == 0:
        breakdown = _format_port_breakdown(chosen["ports"])
        reason = (f"机房「{room.name}」没有速率 ≥ {speed_mbps}Mbps 的空闲物理端口，无法接入")
        if breakdown:
            reason += f"。{breakdown}"
        return {
            "supported": True, "blocked": True,
            "block_reason": reason,
            "warnings": warnings, "requested": count,
            "placeable": placeable, "diff": diff, "assignments": [],
        }
    if to_place <= 0:
        return {
            "supported": True, "blocked": True,
            "block_reason": f"机房 {room.name} 无可上架空位（U 位容量 0）",
            "warnings": warnings, "requested": count,
            "placeable": 0, "diff": count, "assignments": [],
        }

    if diff > 0:
        warnings.append({
            "code": "capacity_short",
            "message": (
                f"机房 {room.name} 只能放 {placeable} 台，差 {diff} 台"
                f"（瓶颈：{chosen['bottleneck']}）"
            ),
        })
    if chosen["power_unrecorded"]:
        warnings.append({
            "code": "power_unrecorded",
            "message": (
                f"机房 {room.name} 有 {chosen['power_unrecorded']} 个机柜未录入"
                f" total_power，电力校验跳过（仅提示不阻断）"
            ),
        })

    port_pool = list(chosen["ports"]["access"]) + list(chosen["ports"]["core"])
    core_used = min(max(0, to_place - len(chosen["ports"]["access"])), len(chosen["ports"]["core"]))
    if core_used > 0:
        warnings.append({
            "code": "core_switch_fallback",
            "message": (
                f"接入交换机空闲端口不足，有 {core_used} 台需接入核心交换机"
                f"（违反分层规范时请先扩容接入层）"
            ),
        })

    window = _pick_cabinet_window(chosen["cabinets"], to_place)
    assignments: List[Dict[str, Any]] = []
    port_cursor = 0
    power_warned_cabinets = set()
    simulated = {cab.id: list(existing) for cab, _, existing in window}

    for seq in range(1, to_place + 1):
        target = None
        for cab, _, _ in window:
            from app.utils.cabinet_utils import CabinetUCalculator
            start_u = CabinetUCalculator.auto_allocate_u_position(
                devices=simulated[cab.id], total_u=cab.total_u,
                height_u=u_height, device_spacing=_DEVICE_SPACING,
                min_height_for_spacing=_MIN_HEIGHT_FOR_SPACING,
                filter_parent_only=False,
            )
            if start_u is not None:
                target = (cab, start_u)
                break
        if target is None:  # 理论不可达（placeable 已按 min 截断），防御
            diff += to_place - seq + 1
            warnings.append({
                "code": "capacity_short",
                "message": f"机柜窗口内仅排下 {seq - 1} 台",
            })
            break

        cab, start_u = target
        simulated[cab.id].append({"u_position": start_u, "height_u": u_height})

        if cab.total_power and cab.total_power > 0:
            planned_in_cab = 1 + sum(
                1 for a in assignments if a["cabinet_id"] == cab.id
            )
            used = (cab.used_power or 0) + power_per_unit * planned_in_cab
            if used > cab.total_power and cab.id not in power_warned_cabinets:
                power_warned_cabinets.add(cab.id)
                warnings.append({
                    "code": "power_exceeded",
                    "message": (
                        f"机柜 {cab.cabinet_number} 按方案满载后功率 {used}W，"
                        f"超出额定 {cab.total_power}W（仅提示，请复核电力分配）"
                    ),
                })

        port, switch = port_pool[port_cursor]
        port_cursor += 1
        is_core = chosen["ports"]["switches"][switch.id]["is_core"]

        assignments.append({
            "seq": seq,
            "cabinet_id": cab.id,
            "cabinet_number": cab.cabinet_number,
            "start_u": start_u,
            "switch": {
                "device_id": switch.id,
                "device_name": switch.device_name,
                "role": "core" if is_core else "access",
                "port_id": port.id,
                "port_name": port.port_name,
                "port_type": port.port_type,
                "speed": port.speed,
            },
            "speed_limit_mbps": bandwidth_mbps,
        })

    ip_plan = _room_free_ips(room.id, to_place)
    if ip_plan["short"] > 0:
        warnings.append({
            "code": "ip_short",
            "message": (
                f"机房 {room.name} 空闲 IP 仅 {ip_plan['total_free']} 个"
                f"（{ip_plan['subnet_count']} 个网段），差 {ip_plan['short']} 个"
            ),
        })
    for i, a in enumerate(assignments):
        a["suggested_ip"] = ip_plan["ips"][i] if i < len(ip_plan["ips"]) else None

    used_switch_ids = list({a["switch"]["device_id"] for a in assignments})
    uplinks = _uplink_info(used_switch_ids)
    warnings.append({
        "code": "uplink_capacity_unknown",
        "message": "上行链路容量未登记（connections.bandwidth 为自由文本），出口余量无法计算，请人工核对",
    })

    return {
        "supported": True,
        "blocked": False,
        "block_reason": None,
        "requested": count,
        "placeable": placeable,
        "diff": diff,
        "room": {"id": room.id, "name": room.name},
        "summary": {
            "u_height": u_height,
            "power_per_unit": power_per_unit,
            "bandwidth_mbps": bandwidth_mbps,
            "port_speed_mbps": speed_mbps,
            "bottleneck": chosen["bottleneck"],
            "power_headroom": chosen["power_headroom"],
            "free_ip_total": ip_plan["total_free"],
            "cabinets_used": sorted({a["cabinet_number"] for a in assignments}),
        },
        "assignments": assignments,
        "uplinks": uplinks,
        "warnings": warnings,
        "note": "Phase 1 纯推荐，零副作用：实际分配请走 IP 管理流程与上架流程",
    }
