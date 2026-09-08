# -*- coding: utf-8 -*-
"""实体检索能力：客户 / 设备 名称 → 结构化实体（含候选追问）。

customer.search 与 devices.locate 是拓扑类能力的**前置解析**：LLM 说"客户A的
服务器连到哪些交换机"时，先用本能力把"客户A"落成 customer_id 再进拓扑查询。
设计决策：
- 参数形态名称+ID 混合；解析结果不确定时返回候选列表（supported=False +
  hint + candidates），由 LLM 继续追问，而不是猜一个错实体。
- 设备检索结果经数据域(device_scope)裁剪：不可见设备不返回存在性。
"""
from typing import Any, Dict, Optional

from app.services.ai.capabilities.registry import register_capability
from app.services.ai.entity_lookup import (
    resolve_customer,
    resolve_device,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _visible_scope() -> "tuple[bool, Optional[set], str]":
    """取当前用户可见设备集（与 topology_capabilities 同口径）。

    Returns:
        (ok, visible, reason)：ok=False 时 reason 为拒绝原因（身份缺失或
        数据域服务故障——后者 fail-closed，见 device_scope.resolve_visible_scope）；
        visible=None 表示无限制（超管/全量），否则为受限设备 id 集合。
    """
    from app.services.ai.capabilities.device_scope import resolve_visible_scope
    return resolve_visible_scope()


def _resolve_err(res: Dict[str, Any]) -> Dict[str, Any]:
    """解析失败/歧义 → 既有 supported=False + hint + candidates 返回形状。"""
    out: Dict[str, Any] = {"supported": False, "hint": res.get("message", "实体解析失败")}
    candidates = res.get("candidates")
    if candidates:
        out["candidates"] = candidates
    return out


@register_capability("customer.search")
def customer_search(args: Dict[str, Any]) -> dict:
    """按名称/ID 搜客户，返回客户信息与其设备清单。

    用于 LLM 把"客户A"解析成实体后直接给结果；设备清单经过数据域裁剪。
    """
    query = args.get("query")
    if query is None:
        raise ValueError("query 必填")

    res = resolve_customer(query)
    if res["status"] != "ok":
        return _resolve_err(res)

    customer = res["customer"]
    ok, visible, reason = _visible_scope()
    if not ok:
        return {"supported": False, "hint": reason}

    from app.models.device import Device
    from app.services.ai.entity_lookup import _MAX_CUSTOMER_DEVICES

    dev_query = Device.query.filter(Device.customer_id == customer["id"])
    if visible is not None:
        if not visible:
            return {"supported": False, "hint": "当前数据域无可访问设备"}
        dev_query = dev_query.filter(Device.id.in_(visible))
    total = dev_query.filter(Device.deleted_at.is_(None)).count()
    device_rows = (
        dev_query.filter(Device.deleted_at.is_(None))
        .order_by(Device.id)
        .limit(_MAX_CUSTOMER_DEVICES)
        .all()
    )
    from app.services.ai.entity_lookup import _device_brief
    devices = [_device_brief(d) for d in device_rows]

    result: Dict[str, Any] = {
        "customer": customer,
        "device_count": total,
        "devices": devices,
    }
    if total > len(devices):
        result["truncated"] = True
        result["hint"] = f"设备较多，仅展示前 {len(devices)} 台"
    return result


@register_capability("devices.locate")
def devices_locate(args: Dict[str, Any]) -> dict:
    """按名称 / 主机名 / 管理 IP / ID 定位单台设备（跨数据域校验）。"""
    query = args.get("query")
    if query is None:
        raise ValueError("query 必填")

    res = resolve_device(query)
    if res["status"] != "ok":
        return _resolve_err(res)

    device = res["device"]
    ok, visible, reason = _visible_scope()
    if not ok:
        return {"supported": False, "hint": reason}
    if visible is not None and device["id"] not in visible:
        return {"supported": False, "hint": f"无权访问设备 {device['id']}（数据域隔离）"}
    return device
