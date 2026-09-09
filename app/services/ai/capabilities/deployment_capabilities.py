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


def _resolve_room_id(args: Dict[str, Any]) -> Any:
    """room_id / room_name 混合解析；都缺省返回 None（全部机房择优）。"""
    room_id = args.get("room_id")
    room_name = args.get("room_name") or args.get("room")
    if room_id not in (None, ""):
        return room_id
    if room_name:
        from app.models.room import Room

        room = Room.query.filter(Room.name.ilike(str(room_name).strip())).first()
        if room is None:
            raise ValueError(f"机房不存在: {room_name}")
        return room.id
    return None


@register_capability("deployment.plan")
def deployment_plan(args: Dict[str, Any]) -> dict:
    """生成上架推荐方案（机柜+U位 / IP / 端口 / 限速 / 出口判定）。

    Args:
        count: 上架台数（≥1）；缺省 = 容量模式，回答"还能上多少台"
        bandwidth_mbps: 单台带宽需求 Mbps（必填 >0，人工输入）
        port_speed: 服务器端口速率（必填，如 "1000m"/"1g"/"10g"）
        u_height: 单台 U 高（默认 2）
        power_per_unit: 单台功率 W（默认 750，仅参考不阻断）
        room_id / room_name: 机房（可选，缺省全机房择优）
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
        return build_plan(
            count=count,
            bandwidth_mbps=_coerce_positive_int(args.get("bandwidth_mbps"), "bandwidth_mbps"),
            port_speed_raw=args.get("port_speed") or args.get("port_speed_mbps"),
            u_height=_coerce_positive_int(args.get("u_height"), "u_height", default=2),
            power_per_unit=_coerce_positive_int(
                args.get("power_per_unit"), "power_per_unit", default=750
            ),
            room_id=room_id,
            visible_switch_ids=visible,
        )
    except DeploymentPlanError as exc:
        raise ValueError(str(exc))
