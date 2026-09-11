# -*- coding: utf-8 -*-
"""拓扑遍历能力：上行链路 / 点对点路径 / 客户接入 / 影响面。

全部基于 topology_query_service 的只读图索引：
- 参数 device/customer 均为"名称或 ID"混合形态（name+ID 混合解析），
  解析歧义返回候选列表（supported=False + candidates）供 LLM 追问。
- 每次调用先取当前用户可见设备集并整体裁剪图索引：跨设备域的信息
  （客户接入、影响面）天然不会泄露不可见设备的存在性。
- 全部能力只读，不声明 requires_permission；数据域服务故障按 **fail-closed**
  拒绝（放行=受限用户静默获得全量可见性，详见 device_scope.resolve_visible_scope）。
"""
import threading
import time
from typing import Any, Dict, Optional, Set

from app.services.ai.capabilities.registry import register_capability
from app.services.ai.entity_lookup import resolve_customer, resolve_device
from app.utils.logging import get_logger

logger = get_logger(__name__)

_TOPO_INDEX_TTL_SECONDS = 60.0
_TOPO_INDEX_MAX_ENTRIES = 32
_index_cache: Dict[str, Any] = {}
_index_cache_lock = threading.Lock()


def _index_cache_key(visible: Optional[Set[int]]) -> str:
    """缓存键 = 可见域内容。同可见域 → 同索引，可安全共享。

    注意键不含 user_id：索引已按可见域裁剪，可见集相同即内容相同，
    跨用户共享不会泄露域外设备（泄露面由 visible 决定，不由缓存决定）。

    必须区分两种"空"：visible=None 表示超管/全量（不裁剪），
    visible=set() 表示受限且当前无任何可见设备——两者语义相反，
    共用键会让空集用户命中全量索引。把这条防线放在缓存键本身，
    新增 capability 即使漏了入口校验也不会静默获得全量可见性。
    """
    if visible is None:
        return "all"
    if not visible:
        return "empty"
    return "v:%d:%d" % (len(visible), hash(frozenset(visible)))


def _load_index_cached(visible: Optional[Set[int]]):
    """带 TTL 的拓扑索引读取（未命中或过期才真正建图）。

    索引对象会被多线程共享，其内部 `_parent_cache`/`_forest_parent` 是幂等
    的惰性记忆化（重复计算只浪费一点 CPU，结果一致），故共享安全。
    """
    key = _index_cache_key(visible)
    now = time.monotonic()
    with _index_cache_lock:
        hit = _index_cache.get(key)
        if hit is not None and now - hit[0] < _TOPO_INDEX_TTL_SECONDS:
            return hit[1]

    from app.services.topology_query_service import load_topology_index
    idx = load_topology_index(visible_ids=visible)

    with _index_cache_lock:
        if len(_index_cache) >= _TOPO_INDEX_MAX_ENTRIES:
            _index_cache.clear()
        _index_cache[key] = (now, idx)
    return idx


def clear_topology_index_cache() -> None:
    """清空拓扑索引缓存（拓扑变更后手动失效 / 测试用）。"""
    with _index_cache_lock:
        _index_cache.clear()


def _visible_scope() -> "tuple[bool, Optional[set], str]":
    """取当前用户可见设备集（与 entity_capabilities 同口径）。

    Returns:
        (ok, visible, reason)：ok=False 时 reason 为拒绝原因（身份缺失或
        数据域服务故障——后者 fail-closed，见 device_scope.resolve_visible_scope）；
        visible=None 表示无限制（超管/全量），否则为受限设备 id 集合。
    """
    from app.services.ai.capabilities.device_scope import resolve_visible_scope
    return resolve_visible_scope()


def _deny(hint: str) -> Dict[str, Any]:
    """拒绝/无法执行时的统一返回形状（对齐 devices.get_by_id 惯例）。"""
    return {"supported": False, "hint": hint}


def _resolve_entity(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """实体解析结果 → device/customer dict；非 ok 时返回拒绝 dict（调用方判断）。"""
    if result["status"] == "ok":
        return result.get("device") or result.get("customer")
    out: Dict[str, Any] = {"supported": False, "hint": result.get("message", "实体解析失败")}
    candidates = result.get("candidates")
    if candidates:
        out["candidates"] = candidates
    return out


def _device_arg(args: Dict[str, Any], key: str) -> Any:
    """取必填 device 参数（名称或 ID），缺失抛 ValueError 对齐既有能力。"""
    value = args.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"{key} 必填")
    return value


def _root_access(device_id: int, visible: Optional[set]) -> Optional[Dict[str, Any]]:
    """数据域校验：受限域下根设备不可见则拒绝（不返回存在性）。"""
    if visible is not None and device_id not in visible:
        return _deny(f"无权访问设备 {device_id}（数据域隔离）")
    return None


@register_capability("topology.uplink_path")
def topology_uplink_path(args: Dict[str, Any]) -> dict:
    """返回设备（服务器或交换机）到最上级核心的完整上行链路。

    输出逐跳设备名与端口；服务器多网卡/多接入时拆多条路径。
    """
    raw = _device_arg(args, "device")
    res = _resolve_entity(resolve_device(raw))
    if not isinstance(res, dict) or res.get("supported") is False:
        return res
    device: Dict[str, Any] = res

    ok, visible, reason = _visible_scope()
    if not ok:
        return _deny(reason)
    denied = _root_access(device["id"], visible)
    if denied:
        return denied

    idx = _load_index_cached(visible)
    path = idx.uplink_path(device["id"])
    return {"device": device, **path}


@register_capability("topology.path_between")
def topology_path_between(args: Dict[str, Any]) -> dict:
    """返回两台设备之间的一条最短连通路径（N2N/D2N 均参与）。

    起点终点可为服务器或网络设备；无路径时 reachable=False 并给出原因。
    """
    raw_a = _device_arg(args, "device_a")
    raw_b = _device_arg(args, "device_b")
    res_a = _resolve_entity(resolve_device(raw_a))
    if not isinstance(res_a, dict) or res_a.get("supported") is False:
        return res_a
    res_b = _resolve_entity(resolve_device(raw_b))
    if not isinstance(res_b, dict) or res_b.get("supported") is False:
        return res_b
    dev_a: Dict[str, Any] = res_a
    dev_b: Dict[str, Any] = res_b

    ok, visible, reason = _visible_scope()
    if not ok:
        return _deny(reason)
    for d in (dev_a, dev_b):
        denied = _root_access(d["id"], visible)
        if denied:
            return denied

    idx = _load_index_cached(visible)
    path = idx.path_between(dev_a["id"], dev_b["id"])
    return {"device_a": dev_a, "device_b": dev_b, **path}


@register_capability("topology.customer_connectivity")
def topology_customer_connectivity(args: Dict[str, Any]) -> dict:
    """客户接入拓扑：客户所有服务器 → 接入交换机（含端口）→ 上联核心链路。"""
    raw = args.get("customer")
    if raw is None or str(raw).strip() == "":
        raise ValueError("customer 必填")
    res = _resolve_entity(resolve_customer(raw))
    if not isinstance(res, dict) or res.get("supported") is False:
        return res
    customer: Dict[str, Any] = res

    ok, visible, reason = _visible_scope()
    if not ok:
        return _deny(reason)
    if visible is not None and not visible:
        return _deny("当前数据域无可访问设备")

    idx = _load_index_cached(visible)
    conn = idx.customer_connectivity(customer["id"])
    return {"customer": customer, **conn}


@register_capability("topology.impact_analysis")
def topology_impact_analysis(args: Dict[str, Any]) -> dict:
    """影响面分析：网络设备宕机将影响的交换机/服务器及其所属客户。

    以该设备为根沿上行父指针反向计算下行子树（root 自身外的受影响面）。
    根设备必须是网络设备；服务器作为结果出现而非根。
    """
    raw = _device_arg(args, "device")
    res = _resolve_entity(resolve_device(raw))
    if not isinstance(res, dict) or res.get("supported") is False:
        return res
    device: Dict[str, Any] = res
    if device.get("device_type") != "network":
        return _deny(
            f"设备「{device.get('name')}」是 {device.get('device_type')}，"
            "影响面分析仅面向网络设备（交换机/路由器/防火墙）"
        )

    ok, visible, reason = _visible_scope()
    if not ok:
        return _deny(reason)
    denied = _root_access(device["id"], visible)
    if denied:
        return denied

    idx = _load_index_cached(visible)
    impact = idx.downstream(device["id"])
    if not impact.get("supported_root"):
        return _deny(impact.get("reason", "该设备不支持作为影响面根"))
    return {"device": device, **impact}
