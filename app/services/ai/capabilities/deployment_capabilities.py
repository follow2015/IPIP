# -*- coding: utf-8 -*-
"""上架方案能力：deployment.plan（只读，Phase 1 纯推荐零副作用）。

把 docs/上架规划.md 拍板口径暴露给 AI 技能：运维直接问
「机房 A 能上几台 2U 750W 的电口服务器？」即可得到
机柜+U位+IP+端口+限速+出口的完整推荐。

数据域纪律（对齐 topology_capabilities）：
- 只读能力不声明 requires_permission；
- device_scope.resolve_visible_scope() 故障 → fail-closed 拒绝；
- 受限可见域下，端口推荐池按可见交换机集裁剪，机柜/U位/IP 为机房级
  资产（不含设备级敏感信息）保持全量，在返回 note 中说明口径。
"""
from typing import Any, Dict

from app.services.ai.capabilities.registry import register_capability
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _deny(hint: str) -> Dict[str, Any]:
    return {"supported": False, "hint": hint}


def _coerce_positive_int(value: Any, field: str, default: Any = None) -> Any:
    if value is None or str(value).strip() == "":
        if default is not None:
            return default
        raise ValueError(f"{field} 必填")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} 须为正整数，当前: {value!r}")


_IP_SCOPE_ALIASES = {
    "public": "public", "公网": "public", "公網": "public", "外网": "public", "外網": "public",
    "private": "private", "内网": "private", "內網": "private", "私网": "private", "私網": "private",
}


def _coerce_ip_scope(value: Any) -> Any:
    """ip_scope 入参归一（中文别名友好）；非法值明确报错而不是静默忽略。"""
    if value is None or str(value).strip() == "":
        return None
    key = str(value).strip().lower()
    if key in _IP_SCOPE_ALIASES:
        return _IP_SCOPE_ALIASES[key]
    raise ValueError(f"ip_scope 只能是 public/private（公网/内网），当前: {value!r}")


_POOL_SCOPE_ALIASES = {
    "auto": "auto", "自动": "auto", "跨机房": "auto", "二层域": "auto",
    "l2": "auto", "virtual_room": "auto",
    "room": "room", "本机房": "room", "物理机房": "room", "仅本机房": "room",
    "只在本机房": "room", "限定本机房": "room",
}


def _coerce_pool_scope(value: Any) -> Any:
    """ip_pool_scope 入参归一；非法值明确报错。"""
    if value is None or str(value).strip() == "":
        return "auto"
    key = str(value).strip().lower()
    if key in _POOL_SCOPE_ALIASES:
        return _POOL_SCOPE_ALIASES[key]
    raise ValueError(f"ip_pool_scope 只能是 auto/room（跨机房/仅本机房），当前: {value!r}")


def _resolve_room_id(args: Dict[str, Any]) -> Any:
    """room_id / room_name 混合解析；都缺省返回 None（全部机房择优）。

    名称解析启发式（用户口述"机房A"与库名"room-A"/"常青机房"常无公共
    子串）：先对原词做 ilike 精确 → 包含匹配；再剥离"机房"字样用剩余
    token 重试两级匹配（"机房A"→"A"）。唯一命中直接用；多个候选列出
    供复问；零命中报错并附可选机房清单。
    """
    room_id = args.get("room_id")
    room_name = args.get("room_name") or args.get("room")
    if room_id not in (None, ""):
        return room_id
    if room_name:
        from app.models.room import Room

        name = str(room_name).strip()
        tokens = [name]
        stripped = name.replace("机房", "").strip()
        if stripped and stripped != name:
            tokens.append(stripped)

        for token in tokens:
            room = Room.query.filter(Room.name.ilike(token)).first()
            if room is not None:
                return room.id
        for token in tokens:
            matches = Room.query.filter(Room.name.ilike(f"%{token}%")).all()
            if len(matches) == 1:
                return matches[0].id
            if len(matches) > 1:
                cand = "、".join(r.name for r in matches[:10])
                raise ValueError(
                    f"机房名称「{name}」匹配到多个机房：{cand}，请指明完整名称"
                )
        all_rooms = [r.name for r in Room.query.order_by(Room.id).all()]
        room_list = "、".join(all_rooms[:20]) + ("…" if len(all_rooms) > 20 else "")
        raise ValueError(f"机房不存在: {name}。可选机房：{room_list or '（系统中暂无机房）'}")
    return None


@register_capability("deployment.plan")
def deployment_plan(args: Dict[str, Any]) -> dict:
    """生成上架推荐方案（机柜+U位 / IP / 端口 / 限速 / 出口判定）。

    Args:
        count: 上架台数（≥1）；缺省 = 容量模式，回答"还能上多少台"
        bandwidth_mbps: 单台带宽需求 Mbps（可选；缺省不给限速建议）
        port_speed: 服务器端口速率（必填，如 "1000m"/"1g"/"10g"）
        u_height: 单台 U 高（默认 2）
        power_per_unit: 单台功率 W（默认 750，仅参考不阻断）
        room_id / room_name: 机房（可选，缺省全机房择优）
        ip_scope: "public" 仅推公网 IP / "private" 仅推内网 / None 不限（公网优先）
        ip_pool_scope: "auto" 先本机房后二层域跨机房（默认）/" room" 只用本机房地址
    """
    from app.services.ai.capabilities.device_scope import resolve_visible_scope
    from app.services.deployment_plan_service import DeploymentPlanError, build_plan

    ok, visible, reason = resolve_visible_scope()
    if not ok:
        return _deny(reason)  # 数据域服务故障 fail-closed

    try:
        room_id = _resolve_room_id(args)
        raw_count = args.get("count")
        count = None if raw_count in (None, "") else _coerce_positive_int(raw_count, "count")
        raw_bw = args.get("bandwidth_mbps")
        bandwidth = None if raw_bw in (None, "") else _coerce_positive_int(raw_bw, "bandwidth_mbps")
        scope = args.get("ip_scope") or args.get("ip_type")
        return build_plan(
            count=count,
            bandwidth_mbps=bandwidth,
            port_speed_raw=args.get("port_speed") or args.get("port_speed_mbps"),
            u_height=_coerce_positive_int(args.get("u_height"), "u_height", default=2),
            power_per_unit=_coerce_positive_int(
                args.get("power_per_unit"), "power_per_unit", default=750
            ),
            room_id=room_id,
            visible_switch_ids=visible,
            ip_scope=_coerce_ip_scope(scope),
            ip_examples=_coerce_positive_int(
                args.get("ip_examples"), "ip_examples", default=0
            ),
            ip_pool_scope=_coerce_pool_scope(
                args.get("ip_pool_scope") or args.get("pool_scope")
            ),
        )
    except DeploymentPlanError as exc:
        raise ValueError(str(exc))
