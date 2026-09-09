# -*- coding: utf-8 -*-
"""根因分析类 capability：root_cause.analyze（只读）。

设计文档第四节：定位故障域而非单设备。把「同机柜/同机房/同上游设备是否同时异常」
与「当前值 vs 基线偏离倍数」作为结构化事实喂给 LLM，而不是让 LLM 自己判断
"这个值算不算高"。

数据域裁剪与拓扑类能力同口径：走 resolve_visible_scope（fail-closed），且邻居
设备列表按可见集过滤——故障域会暴露"哪些邻居设备也异常"，未过滤即等于泄露
数据域外设备的存在性与健康状态。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.ai.capabilities.registry import register_capability
from app.utils.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_METRIC = "cpu_usage"


def _coerce_device_id(raw: Any) -> Optional[int]:
    """把参数里的 device_id 收敛成 int；无法收敛返回 None。"""
    if isinstance(raw, bool):  # bool 是 int 子类，必须单独排除
        return None
    if isinstance(raw, int):
        return raw
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


@register_capability("root_cause.analyze")
def analyze(args: Dict[str, Any]) -> Dict[str, Any]:
    """故障域定位：判断单设备异常是本地问题还是机柜/机房/上游级故障。

    Args:
        args: {
            "device_id": int,              必填，异常设备 ID
            "metric": str,                 可选，异常指标 key，默认 cpu_usage
            "inspection": dict,            可选，device.live_inspection 的返回，
                                           提供时额外产出结构化事实列表
        }

    Returns:
        {
            "device_id", "metric", "fault_domain", "scope",
            "related_anomalies": [{device_id, device_name, relation, metric,
                                   current, deviation_pct, reason}],
            "facts": [...],                仅传 inspection 时产出
            "suppressed_by_scope": int     因数据域被剔除的邻居数（0 表示无裁剪）
        }
        或 {"supported": False, "hint": ...}
    """
    from app.services.ai.capabilities.device_scope import resolve_visible_scope
    from app.services.ai.root_cause_analyzer import RootCauseAnalyzer

    device_id = _coerce_device_id(args.get("device_id"))
    if device_id is None:
        return {"supported": False, "hint": "device_id 必填且为整数"}

    metric = args.get("metric") or _DEFAULT_METRIC
    if not isinstance(metric, str) or not metric.strip():
        return {"supported": False, "hint": "metric 必须是非空字符串"}
    metric = metric.strip()

    ok, visible, reason = resolve_visible_scope()
    if not ok:
        return {"supported": False, "hint": reason}
    if visible is not None and device_id not in visible:
        return {"supported": False, "hint": f"无权访问设备 {device_id}（数据域隔离）"}

    try:
        result = RootCauseAnalyzer().analyze_fault_domain(device_id, metric)
    except Exception as e:  # noqa: BLE001 - 分析失败降级为 supported:false，不外抛
        logger.warning("root_cause.analyze failed device=%s metric=%s: %s",
                       device_id, metric, e)
        return {"supported": False, "hint": f"故障域分析失败：{type(e).__name__}"}

    if result.get("fault_domain") == "unknown":
        return {"supported": False, "hint": f"设备 {device_id} 不存在"}

    related: List[Dict[str, Any]] = result.get("related_anomalies") or []
    if visible is not None:
        kept = [r for r in related if r.get("device_id") in visible]
        suppressed = len(related) - len(kept)
        related = kept
    else:
        suppressed = 0

    domain = result.get("fault_domain")
    scope = result.get("scope") or ""
    if not related and domain != "single":
        domain = "single"
        scope = "仅单设备异常，疑似设备本地问题（其余异常设备不在您的可见范围内）"

    out: Dict[str, Any] = {
        "device_id": device_id,
        "metric": metric,
        "fault_domain": domain,
        "scope": scope,
        "related_anomalies": related,
        "suppressed_by_scope": suppressed,
    }

    inspection = args.get("inspection")
    if isinstance(inspection, dict) and inspection:
        try:
            out["facts"] = RootCauseAnalyzer().build_structured_facts(
                device_id, inspection
            )
        except Exception as e:  # noqa: BLE001 - 事实抽取失败不影响故障域结论
            logger.warning("root_cause.build_facts failed device=%s: %s", device_id, e)
            out["facts"] = []

    return out
