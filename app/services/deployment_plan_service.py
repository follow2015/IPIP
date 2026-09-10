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

_DEFAULT_IP_SAMPLES = 10

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
            f"端口速率无法识别：{raw}（支持 100M/1G/1000M/10G/25G/40G/100G/400G）"
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
    """电力参考容量：(可再放台数, 未录入额定功率机柜数, [(机柜号,额定,已用)...])。

    第三项 = 已用功率超过额定值的异常机柜（登记数据自相矛盾），必须暴露给
    用户——这类数据的电力参考值已不可信，不能静默按 0 抹平。
    """
    headroom = 0
    unrecorded = 0
    anomalies = []
    for cab, _, _ in cabinets:
        if not cab.total_power or cab.total_power <= 0:
            unrecorded += 1
            continue
        used = cab.used_power or 0
        if used > cab.total_power:
            anomalies.append((cab.cabinet_number, cab.total_power, used))
            continue
        headroom += max(0, (cab.total_power - used) // power_per_unit)
    return headroom, unrecorded, anomalies


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


def _switch_distribution(ports: Dict[str, Any]) -> List[Dict[str, Any]]:
    """可用端口按交换机聚合（"哪些交换机、多少口、接入还是核心、在哪个机柜"）。

    只报总数会让用户无法判断布线可行性（端口可能集中在某台远机柜交换机上），
    因此 Top 维度必须落到交换机。
    """
    from app.models.cabinet import Cabinet

    counter: Dict[int, Dict[str, Any]] = {}
    for port, sw in list(ports["access"]) + list(ports["core"]):
        item = counter.get(sw.id)
        if item is None:
            meta = ports["switches"].get(sw.id, {})
            item = {
                "switch_id": sw.id,
                "device_name": sw.device_name,
                "role": "core" if meta.get("is_core") else "access",
                "cabinet_id": sw.cabinet_id,
                "cabinet_number": None,
                "free_ports": 0,
            }
            counter[sw.id] = item
        item["free_ports"] += 1

    cab_ids = {i["cabinet_id"] for i in counter.values() if i["cabinet_id"]}
    numbers = {}
    if cab_ids:
        numbers = {
            c.id: c.cabinet_number
            for c in Cabinet.query.filter(Cabinet.id.in_(list(cab_ids))).all()
        }
    for item in counter.values():
        item["cabinet_number"] = numbers.get(item["cabinet_id"])

    return sorted(counter.values(), key=lambda x: (-x["free_ports"], str(x["device_name"])))


def _is_public_ipv4(ip_address: Optional[str]) -> bool:
    """是否为公网 IPv4（RFC1918/CGNAT/环回/链路本地/多播/保留段均算内网）。

    库内无"公网/内网"字段，只能按地址属性判定；判定不了的安全回落为 False。
    """
    import ipaddress

    try:
        addr = ipaddress.ip_address(str(ip_address or "").strip())
    except ValueError:
        return False
    if addr.version != 4:
        return False
    return not (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_multicast or addr.is_reserved or addr.is_unspecified
    )


def _l2_room_ids(room_id: int) -> Dict[str, Any]:
    """本机房所在的二层可达域（虚拟房网格径）。

    同一虚拟机房（virtual_room_members）的成员交换机在网络上是互联的，
    因此登记在该虚拟机房覆盖机房名下的网段对本机房同样可用。

    该口径与网络扫描保持一致：``vr:{id}`` 扫描的 IP 作业范围就是
    ``VirtualRoomService.get_covered_room_ids()``（见 network_scanner_service
    Phase 6b）；公网地址本身也是跨机房可达的（同文件 6b 段注释）。

    Returns:
        {"room_ids": set, "room_names": [...], "virtual_room_names": [...],
         "scope": "virtual_room" | "room"}
    """
    from app.models.cabinet import Cabinet
    from app.models.device import Device
    from app.models.room import Room
    from app.models.virtual_room import VirtualRoomMember
    from app.persistence.virtual_room_repository import VirtualRoomRepository

    fallback = {
        "room_ids": {room_id}, "room_names": [], "virtual_room_names": [],
        "scope": "room",
    }
    cab_ids = [
        r[0] for r in db.session.query(Cabinet.id).filter(
            Cabinet.room_id == room_id
        ).all()
    ]
    if not cab_ids:
        return fallback
    switch_ids = [
        r[0] for r in db.session.query(Device.id).filter(
            Device.cabinet_id.in_(cab_ids)
        ).all()
    ]
    if not switch_ids:
        return fallback

    vr_ids = [
        r[0] for r in db.session.query(VirtualRoomMember.virtual_room_id)
        .filter(VirtualRoomMember.device_id.in_(switch_ids))
        .distinct().all()
    ]
    if not vr_ids:
        return fallback  # 本机房交换机未加入任何虚拟机房 → 保守按本机房计

    repo = VirtualRoomRepository(db.session)
    room_ids = {room_id}
    vr_names = []
    for vr_id in sorted(vr_ids):
        room_ids |= set(repo.get_covered_room_ids(vr_id))
        vr = repo.find_by_id(vr_id)
        if vr is not None:
            vr_names.append(vr.name)

    names = [
        r[1] for r in db.session.query(Room.id, Room.name)
        .filter(Room.id.in_(sorted(room_ids)))
        .order_by(Room.id).all()
    ]
    return {
        "room_ids": room_ids,
        "room_names": names,
        "virtual_room_names": vr_names,
        "scope": "virtual_room" if len(room_ids) > 1 else "room",
    }


def _collect_ip_candidates(room_ids, primary_room_id=None):
    """收集一组机房内的空闲 IP 候选（跨去重），供多口径统计复用。

    Returns:
        (candidates, stats)；candidates 每项含 ip/network/room/is_primary/
        is_public/unused/ip_int，其中 is_primary 表示网段登记在目标物理机房名下。
    """
    import bisect

    from app.core.enums import IPStatus
    from app.models.ip_model import IPManager, ip_to_int
    from app.models.room import Room
    from app.models.switch_route import IPNetwork

    room_ids = sorted(set(int(r) for r in room_ids if r is not None))
    if not room_ids:
        return [], {"usable": 0, "registered": 0,
                    "usable_local": 0, "registered_local": 0}

    subnets = IPNetwork.query.filter(IPNetwork.room_id.in_(room_ids)).all()
    if not subnets:
        return [], {"usable": 0, "registered": 0,
                    "usable_local": 0, "registered_local": 0}

    wanted_status = (int(IPStatus.UNUSED), int(IPStatus.INACTIVE))
    rows = (
        IPManager.query
        .filter(
            IPManager.room_id.in_(room_ids),
            IPManager.status.in_(wanted_status),
            IPManager.ip_int.isnot(None),
        )
        .all()
    )
    room_names = {
        r.id: r.name for r in Room.query.filter(Room.id.in_(room_ids)).all()
    }
    rows.sort(key=lambda r: r.ip_int)
    ints = [r.ip_int for r in rows]

    seen: Dict[int, Dict[str, Any]] = {}
    usable = usable_local = registered_local = 0
    for subnet in subnets:
        is_primary = subnet.room_id == primary_room_id
        if is_primary:
            registered_local += 1
        if subnet.network_int is None or not subnet.prefix:
            continue
        prefix = int(subnet.prefix)
        if prefix < 8 or prefix > 32:   # 排除 0.0.0.0/0 一类兜底脏数据
            continue
        size = 1 << (32 - prefix)
        lo = subnet.network_int + 1          # 排除网络号
        hi = subnet.network_int + size - 2   # 排除广播地址
        if lo > hi:                          # /31、/32 无可分配主机地址
            continue
        usable += 1
        if is_primary:
            usable_local += 1
        gateway_int = ip_to_int(subnet.gateway) if subnet.gateway else None
        left = bisect.bisect_left(ints, lo)
        right = bisect.bisect_right(ints, hi)
        for r in rows[left:right]:
            if gateway_int is not None and r.ip_int == gateway_int:
                continue
            cand = {
                "ip": r.ip_address,
                "network": subnet.network,
                "room": room_names.get(subnet.room_id),
                "is_primary": is_primary,
                "is_public": _is_public_ipv4(r.ip_address),
                "unused": r.status == int(IPStatus.UNUSED),
                "ip_int": r.ip_int,
            }
            old = seen.get(r.ip_int)
            if old is None or (is_primary and not old["is_primary"]):
                seen[r.ip_int] = cand

    return list(seen.values()), {
        "usable": usable, "registered": len(subnets),
        "usable_local": usable_local, "registered_local": registered_local,
    }


def _ip_view(candidates, ip_scope, needed: int, examples: int,
             usable_subnets: int, registered_subnets: int,
             required: Optional[int] = None) -> Dict[str, Any]:
    """把一个候选池折算成某个口径的统计视图（计数 + 推荐序 + 样例）。

    needed 决定候选切片大小（容量模式下按最大可能台数取），
    required 是实际要落地的台数，决定 short 缺口。
    """
    if ip_scope == "public":
        pool = [c for c in candidates if c["is_public"]]
    elif ip_scope == "private":
        pool = [c for c in candidates if not c["is_public"]]
    else:
        pool = list(candidates)

    pool.sort(key=lambda c: (not c["is_public"], not c["is_primary"],
                             not c["unused"], c["ip_int"]))

    return {
        "ips": [c["ip"] for c in pool[:max(needed, 0)]],
        "total_free": len(candidates),
        "public_free": sum(1 for c in candidates if c["is_public"]),
        "private_free": sum(1 for c in candidates if not c["is_public"]),
        "subnet_count": usable_subnets,
        "registered_subnet_count": registered_subnets,
        "short": max(0, (needed if required is None else required)
                     - min(len(pool), max(needed, 0))),
        "samples": [
            {"ip": c["ip"], "network": c["network"], "room": c["room"],
             "scope": "public" if c["is_public"] else "private"}
            for c in pool[:max(examples, 0)]
        ],
    }


def _ip_reference(primary_room_id: int, l2: Dict[str, Any],
                  ip_scope: Optional[str], needed: int, examples: int,
                  pool_scope: str = "auto",
                  required: Optional[int] = None) -> Dict[str, Any]:
    """双口径 IP 资源：物理机房（本地出口）与虚拟机房二层域（跨域可调）并行。

    生产两种形态并存，不是非此即彼：
      · room —— 网段按物理机房登记，出口与带宽在本机房，最稳妥；
      · l2   —— 同一虚拟机房内二层互通，网段可跨物理机房调度，但需要确认出口可达。

    pool_scope:
      "auto"（默认）—— 两套都算，挑 IP 时先本地后跨域；
      "room" —— 严格只用本物理机房名下的地址。

    Returns: 顶层为选中口径的统计（向后兼容 ips/total_free/...），
    另含 local / l2 两份明细与口径标识。
    """
    cands, stats = _collect_ip_candidates(l2["room_ids"], primary_room_id)
    local_cands = [c for c in cands if c["is_primary"]]

    view_local = _ip_view(local_cands, ip_scope, needed, examples,
                          stats["usable_local"], stats["registered_local"],
                          required)
    view_l2 = _ip_view(cands, ip_scope, needed, examples,
                       stats["usable"], stats["registered"], required)

    pick = view_local if pool_scope == "room" else view_l2
    return {
        **pick,
        "scope": l2["scope"],
        "pool_scope": pool_scope,
        "scope_rooms": l2["room_names"],
        "virtual_rooms": l2["virtual_room_names"],
        "local": view_local,
        "l2": view_l2,
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


def _ip_reference_lines(ip_ref: Optional[Dict[str, Any]], placeable: int,
                        room_name: str = "") -> List[str]:
    """IP 段：物理机房（本地出口）与虚拟机房二层域两套口径并列展示。

    实际网络里两者并存——段既可能按物理机房落地（带宽/出口就在这里），
    也可能登记在虚拟机房内其他机房名下（二层互通但要看出口方向是否可达），
    所以不分彼此，用谁的结论由使用者按现场出口情况决定。
    """
    lines = ["", "IP 地址资源"]
    if not ip_ref:
        return lines

    local = ip_ref.get("local") or {}
    l2 = ip_ref.get("l2") or {}
    strict = ip_ref.get("pool_scope") == "room"
    vr_txt = "、".join(ip_ref.get("virtual_rooms") or [])
    room_txt = "、".join(ip_ref.get("scope_rooms") or [])
    has_l2 = ip_ref.get("scope") == "virtual_room"

    def _line(label: str, view: Dict[str, Any]) -> str:
        return (
            f"· {label}：登记 {view.get('registered_subnet_count', 0)} 个网段，"
            f"其中 {view.get('subnet_count', 0)} 个含可分配主机地址；"
            f"空闲可用 {view.get('total_free', 0)} 个："
            f"公网 {view.get('public_free', 0)} 个、"
            f"内网 {view.get('private_free', 0)} 个"
        )

    if local.get("registered_subnet_count") == 0:
        lines.append(f"· ⚠ {room_name}名下未登记任何网段，无法推荐 IP，请先维护网段规划")
    else:
        lines.append(_line(f"本物理机房（{room_name}）", local))
    if has_l2:
        lines.append(_line(f"虚拟机房「{vr_txt}」二层域（{room_txt}）", l2))
        lines.append(
            "· 分配口径：" + ("限定只用本物理机房地址" if strict else
                          "先本物理机房，不足时在同一虚拟机房内跨机房调度")
        )
    else:
        lines.append("· 本机房交换机未加入虚拟机房，无跨机房二层域可参照")
    lines.append("· 计数已去重，并剔除网关、网络号、广播地址与 /31、/32 主机路由")

    base = local.get("public_free", 0) if strict else l2.get("public_free", 0)
    if local.get("registered_subnet_count", 0) and base < placeable:
        gap = placeable - base
        if has_l2 and not strict and l2.get("public_free", 0) >= placeable:
            extra = int(l2["public_free"]) - int(local.get("public_free", 0))
            lines.append(
                f"· ⚠ 每台 1 个公网 IP 时，本物理机房公网地址差 "
                f"{placeable - int(local.get('public_free', 0))} 个；"
                f"二层域内另有 {extra} 个公网空闲可在确认出口可达后跨机房调配"
            )
        else:
            lines.append(
                f"· ⚠ 若每台配 1 个公网 IP，公网地址还差 {gap} 个，"
                f"需先申请新的公网地址段"
            )

    samples = ip_ref.get("samples") or []
    if samples:
        lines.append(f"· 优先可分配地址（前 {len(samples)} 个 · 网段 / 地址）")
        for s in samples:
            tag = "" if s["scope"] == "public" else "（内网）"
            where = f"（{s['room']}）" if s.get("room") else ""
            lines.append(f"  - {s['network']}{where}：{s['ip']}{tag}")
    lines.append("· 以上为可分配建议，未做任何预留与占用")
    return lines


def _capacity_report(room, ev: Dict[str, Any], u_height: int,
                     power_per_unit: int, speed_mbps: int) -> str:
    """容量模式中文报告（给 AI/前端直接展示，避免吐机器字段）。"""
    per_unit_u = u_height + _DEVICE_SPACING
    free_u = sum(
        max(0, (cab.total_u or 0) - sum(d["height_u"] for d in existing))
        for cab, _, existing in ev["cabinets"]
    )
    lines = [
        f"【上架容量查询】{room.name}",
        f"结论：还能上架 {ev['placeable']} 台"
        f"（{u_height}U / {power_per_unit}W / {speed_mbps}Mbps 端口）",
        "",
        "依据",
        f"· U 位：可用 {free_u}U，按每台占 {u_height}U + {_DEVICE_SPACING}U "
        f"散热间距（即 {per_unit_u}U/台）计算 → {ev['placeable']} 台",
        f"· 端口：速率 ≥ {speed_mbps}Mbps 的空闲物理端口 {ev['port_total']} 个",
    ]

    sw_dist = ev.get("switch_distribution") or []
    if sw_dist:
        lines.append("· 端口落在以下交换机（接入/核心 · 所在机柜：可用口）")
        for item in sw_dist:
            where = f"{item['cabinet_number']} 机柜" if item["cabinet_number"] else "机柜未登记"
            role = "核心" if item["role"] == "core" else "接入"
            lines.append(
                f"  - {item['device_name']}（{role} · {where}）：{item['free_ports']} 个"
            )
        if any(i["role"] == "core" for i in sw_dist):
            lines.append("  - ⚠ 上列含核心交换机端口，正式上架请优先用接入交换机端口")

    lines.append(f"· 瓶颈：{ev['bottleneck']}（端口 {ev['port_total']} vs U 位 {ev['placeable']}）")

    dist = [(cab.cabinet_number, fits) for cab, fits, _ in ev["cabinets"] if fits > 0]
    if dist:
        total_fits = sum(f for _, f in dist)
        lines.append("")
        lines.append("可上机柜分布（机柜：台数）")
        lines.append("· " + " | ".join(f"{num}：{fits}" for num, fits in dist))
        if total_fits > ev["placeable"]:
            lines.append(
                f"  - 机柜合计可放 {total_fits} 台，但受{ev['bottleneck']}限制"
                f"最终只能上 {ev['placeable']} 台"
            )

    lines.append("")
    lines.append("电力余量参考")
    lines.append("· 说明：电力按机柜台账估算，存在加装/临时下电未登记的情况，"
                 "不纳入上面的容量结论，以现场实测为准")
    if ev["power_anomalies"]:
        detail = "；".join(
            f"{num} 机柜已用 {used}W 超过额定 {total}W"
            for num, total, used in ev["power_anomalies"]
        )
        lines.append(
            f"· ⚠ 台账异常：{detail}——该部分余量不计入，"
            f"请先核对并修正机柜额定/已用功率"
        )
    lines.append(f"· 按已录额定功率推算还能支撑 {ev['power_headroom']} 台")
    if ev["power_unrecorded"]:
        lines.append(
            f"· 另有 {ev['power_unrecorded']} 个机柜未录入额定功率，未计入电力余量"
        )
    if ev["power_headroom"] < ev["placeable"]:
        lines.append(
            f"· ⚠ 按电力推算（{ev['power_headroom']} 台）少于空间容量"
            f"（{ev['placeable']} 台），上架前请先确认新增电路的供电能力"
        )

    lines += _ip_reference_lines(ev.get("ip_reference"), ev["placeable"], room.name)

    lines.append("")
    lines.append("备注")
    lines.append("· 结果依据库内登记数据推算，现场请复核承重/散热/走线")
    lines.append("· 需要具体到每台机柜、U 位、端口与 IP 的清单，请指定台数后再查")
    return "\n".join(lines)


def _assignment_report(room, assignments: List[Dict[str, Any]],
                       warnings: List[Dict[str, str]], u_height: int,
                       speed_mbps: int) -> str:
    """分配模式中文报告。"""
    cabinets_used = {a["cabinet_number"] for a in assignments}
    core_used = [a for a in assignments if a["switch"]["role"] == "core"]
    lines = [
        f"【上架方案】{room.name} · {len(assignments)} 台 {u_height}U / "
        f"{speed_mbps}Mbps 端口",
        f"涉及机柜：{'、'.join(sorted(cabinets_used))}",
        "",
        "逐台方案（序号 | 机柜-U位 | 交换机/端口 | 建议IP | 限速）",
    ]
    for a in assignments:
        sw = a["switch"]
        limit = a.get("speed_limit_mbps")
        lines.append(
            f"· {a['seq']} | {a['cabinet_number']}-U{a['start_u']} "
            f"| {sw['device_name']} {sw['port_name']}"
            f"（{'核心' if sw['role'] == 'core' else '接入'}）"
            f" | {a.get('suggested_ip') or '无空闲 IP'}"
            f" | {str(limit) + 'Mbps' if limit else '未提供需求'}"
        )
    if core_used:
        names = sorted({a["switch"]["device_name"] for a in core_used})
        lines.append(
            f"· ⚠ 其中 {len(core_used)} 台落到核心交换机（{'、'.join(names)}），"
            f"建议优先接接入交换机"
        )
    if warnings:
        lines.append("")
        lines.append("提示")
        for w in warnings:
            lines.append(f"· {w['message']}")
    lines.append("")
    lines.append("本清单为推荐方案，未预留机位、端口与 IP；实施请走 IP 管理与上架审批流程")
    return "\n".join(lines)


def build_plan(
    *,
    count: Optional[int],
    bandwidth_mbps: Optional[int],
    port_speed_raw: Any,
    u_height: int = 2,
    power_per_unit: int = 750,
    room_id: Optional[int] = None,
    visible_switch_ids=None,
    ip_scope: Optional[str] = None,
    ip_examples: int = 0,
    ip_pool_scope: str = "auto",
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
        ip_scope: "public" 只要公网 / "private" 只要内网 / None 不限（推荐序仍公网优先）
        ip_examples: 额外返回多少个"可分配 IP 样例"（容量模式默认给 _DEFAULT_IP_SAMPLES 个）
        ip_pool_scope: 地址池口径，"auto"（默认，先本物理机房后二层域内跨机房）/
               "room"（严格只用本物理机房名下的地址）
    """
    if ip_scope not in (None, "public", "private"):
        raise DeploymentPlanError("IP 类型 ip_scope 只能是 public / private")
    pool_scope = (ip_pool_scope or "auto").strip().lower()
    if pool_scope in ("l2", "virtual_room", "vroom"):
        pool_scope = "auto"
    if pool_scope not in ("auto", "room"):
        raise DeploymentPlanError("地址池口径 ip_pool_scope 只能是 auto / room")
    examples = int(ip_examples or 0)
    speed_mbps = normalize_port_speed(port_speed_raw)
    if bandwidth_mbps is not None and (not int(bandwidth_mbps) or int(bandwidth_mbps) <= 0):
        raise DeploymentPlanError("单台带宽需求 bandwidth_mbps 须为正整数（不填=不给限速建议）")
    if count is not None and (not int(count) or int(count) < 1):
        raise DeploymentPlanError("台数 count 须 ≥ 1（缺省=查询机房还能上多少台）")
    bandwidth_mbps = int(bandwidth_mbps) if bandwidth_mbps is not None else None
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
        power_head, power_unrecorded, power_anomalies = _room_power_headroom(
            cabinets, power_per_unit
        )
        dims = {"U 位": u_total, "匹配空闲端口": port_total}
        placeable = min(dims.values())
        bottleneck = min(dims, key=dims.get)
        room_evals.append({
            "room": room, "cabinets": cabinets, "ports": ports,
            "placeable": placeable, "u_total": u_total,
            "port_total": port_total, "power_headroom": power_head,
            "power_unrecorded": power_unrecorded, "bottleneck": bottleneck,
            "power_anomalies": power_anomalies,
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
            "message": (f"另有候选机房 {ev['room'].name}，可容纳 {ev['placeable']} 台"
                        f"（本次未选用）"),
        })

    examples = max(examples, _DEFAULT_IP_SAMPLES) if capacity_mode else examples
    chosen["switch_distribution"] = _switch_distribution(chosen["ports"])
    l2 = _l2_room_ids(room.id)
    chosen["ip_reference"] = _ip_reference(
        room.id, l2, ip_scope, max(chosen["placeable"], count),
        examples, pool_scope=pool_scope,
        required=chosen["placeable"] if capacity_mode else count,
    )

    placeable = chosen["placeable"]
    diff = max(0, count - placeable) if not capacity_mode else 0
    to_place = min(count, placeable)

    if chosen["power_anomalies"]:
        detail = "；".join(
            f"{n}（额定 {t}W < 已用 {u}W）" for n, t, u in chosen["power_anomalies"]
        )
        warnings.append({
            "code": "power_data_inconsistent",
            "message": (f"机柜电力台账待核对：{detail}，这部分余量未计入本次评估，"
                        f"请先核对额定功率与已用功率录入"),
        })

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
            "report": _capacity_report(room, chosen, u_height,
                                       power_per_unit, speed_mbps),
            "summary": {
                "u_height": u_height,
                "power_per_unit": power_per_unit,
                "bandwidth_mbps": bandwidth_mbps,
                "port_speed_mbps": speed_mbps,
                "u_total": chosen["u_total"],
                "matched_port_total": chosen["port_total"],
                "bottleneck": chosen["bottleneck"],
                "power_headroom": chosen["power_headroom"],
                "switch_count": len(chosen["switch_distribution"]),
                "free_ip_total": chosen["ip_reference"]["total_free"],
                "public_ip_total": chosen["ip_reference"]["public_free"],
                "subnet_count": chosen["ip_reference"]["subnet_count"],
                "ip_scope": chosen["ip_reference"]["scope"],
                "ip_scope_rooms": chosen["ip_reference"]["scope_rooms"],
                "ip_pool_scope": chosen["ip_reference"]["pool_scope"],
                "local_free_ip_total": (chosen["ip_reference"].get("local") or {})
                .get("total_free", 0),
                "local_public_ip_total": (chosen["ip_reference"].get("local") or {})
                .get("public_free", 0),
            },
            "power_reference": {
                "placeable_by_power": chosen["power_headroom"],
                "unrecorded_cabinets": chosen["power_unrecorded"],
                "anomalies": [
                    {"cabinet": n, "total_power": t, "used_power": u}
                    for n, t, u in chosen["power_anomalies"]
                ],
            },
            "cabinet_distribution": [
                {"cabinet_number": cab.cabinet_number, "placeable": fits}
                for cab, fits, _ in chosen["cabinets"] if fits > 0
            ],
            "switch_distribution": chosen["switch_distribution"],
            "ip_reference": chosen["ip_reference"],
            "warnings": warnings,
            "note": "本次仅评估机房容量，未生成分配明细；指定台数可得逐台机柜/U位/端口/IP 清单",
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
                f"机房 {room.name} 有 {chosen['power_unrecorded']} 个机柜未录入额定功率，"
                f"其电力余量未计入本次评估"
            ),
        })

    port_pool = list(chosen["ports"]["access"]) + list(chosen["ports"]["core"])
    core_used = min(max(0, to_place - len(chosen["ports"]["access"])), len(chosen["ports"]["core"]))
    if core_used > 0:
        warnings.append({
            "code": "core_switch_fallback",
            "message": (
                f"接入交换机空闲端口不足，有 {core_used} 台需上联核心交换机；"
                f"建议先扩容接入交换机端口再上架"
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
                        f"机柜 {cab.cabinet_number} 按本方案满载后达 {used}W，"
                        f"超出额定 {cab.total_power}W，请复核该机柜供电或调整本批分布"
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

    ip_plan = chosen["ip_reference"]  # 已在选机房后统一扫描，避免重复全表查询
    ip_short = max(0, to_place - len(ip_plan["ips"]))
    if ip_short > 0:
        warnings.append({
            "code": "ip_short",
            "message": (
                f"机房 {room.name} 网络可达范围内空闲 IP 仅 "
                f"{ip_plan['total_free']} 个"
                f"（分布于 {ip_plan['subnet_count']} 个网段），还差 {ip_short} 个"
            ),
        })
    for i, a in enumerate(assignments):
        a["suggested_ip"] = ip_plan["ips"][i] if i < len(ip_plan["ips"]) else None

    used_switch_ids = list({a["switch"]["device_id"] for a in assignments})
    uplinks = _uplink_info(used_switch_ids)
    if bandwidth_mbps is None:
        warnings.append({
            "code": "bandwidth_not_provided",
            "message": "未提供单机带宽需求，未生成端口限速建议，也未核算出口带宽余量",
        })
    warnings.append({
        "code": "uplink_capacity_unknown",
        "message": "上行链路带宽未录入或无法识别，出口带宽余量无法核算，请先在连接台账补录上行链路带宽",
    })

    return {
        "supported": True,
        "blocked": False,
        "block_reason": None,
        "requested": count,
        "placeable": placeable,
        "diff": diff,
        "room": {"id": room.id, "name": room.name},
        "report": _assignment_report(room, assignments, warnings,
                                     u_height, speed_mbps),
        "summary": {
            "u_height": u_height,
            "power_per_unit": power_per_unit,
            "bandwidth_mbps": bandwidth_mbps,
            "port_speed_mbps": speed_mbps,
            "bottleneck": chosen["bottleneck"],
            "power_headroom": chosen["power_headroom"],
            "free_ip_total": ip_plan["total_free"],
            "public_ip_total": ip_plan["public_free"],
            "ip_scope": ip_plan["scope"],
            "ip_scope_rooms": ip_plan["scope_rooms"],
            "ip_pool_scope": ip_plan["pool_scope"],
            "local_free_ip_total": (ip_plan.get("local") or {}).get("total_free", 0),
            "local_public_ip_total": (ip_plan.get("local") or {}).get("public_free", 0),
            "cabinets_used": sorted({a["cabinet_number"] for a in assignments}),
        },
        "assignments": assignments,
        "ip_reference": chosen["ip_reference"],
        "uplinks": uplinks,
        "warnings": warnings,
        "note": "本方案为推荐结果，未预留机位、端口与 IP；正式分配请走 IP 管理与上架审批流程",
    }
