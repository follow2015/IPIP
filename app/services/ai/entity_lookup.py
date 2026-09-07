# -*- coding: utf-8 -*-
"""
AI 实体解析（客户 / 设备）

能力参数允许 LLM 直接传"客户A""设备X"这类名称，而非仅 ID。本模块提供
三级匹配（ID 精确 → 字段精确 → 模糊），并总是返回候选列表供 LLM 追问，
避免解析失败就把整轮对话卡死。

设备可解析字段：device_name / hostname / management_ip（也支持数字 ID）。
客户可解析字段：customer_name（唯一约束，匹配安全）。

所有匹配均显式排除软删除记录（deleted_at IS NULL）。
"""
from typing import Any, Dict, List, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

_MAX_CANDIDATES = 10
_MAX_CUSTOMER_DEVICES = 50


def _clean_query(query: Any) -> str:
    """清洗入参：数字转字符串并去除空白。"""
    if isinstance(query, (int, float)):
        return str(int(query))
    return str(query or "").strip()


_LIKE_ESCAPE_CHAR = "\\"


def _escape_like(value: str) -> str:
    """转义 LIKE/ilike 通配符（% _ \\），配合 escape 参数使用。"""
    return (
        value
        .replace(_LIKE_ESCAPE_CHAR, _LIKE_ESCAPE_CHAR * 2)
        .replace("%", _LIKE_ESCAPE_CHAR + "%")
        .replace("_", _LIKE_ESCAPE_CHAR + "_")
    )


def _customer_brief(c) -> Dict[str, Any]:
    """客户精简序列化。"""
    from app.core.enums import CustomerStatus
    status = CustomerStatus(c.customer_status) if c.customer_status is not None else None
    return {
        "id": c.id,
        "name": c.customer_name,
        "status": status.value if status else None,
        "contact_person": c.contact_person,
        "contact_phone": c.contact_phone,
        "email": c.email,
    }


def resolve_customer(query: Any) -> Dict[str, Any]:
    """按 ID / 名称精确 / 名称模糊 三级解析客户。

    Returns:
        {"status": "ok"|"ambiguous"|"missing",
         "customer": {...}|None, "candidates": [{id,name}...], "message": str}
    """
    from app.models.customer import Customer

    q = _clean_query(query)
    if not q:
        return {"status": "missing", "customer": None, "candidates": [],
                "message": "客户参数为空"}

    base = Customer.query.filter(Customer.deleted_at.is_(None))

    if q.isdigit():
        c = base.filter(Customer.id == int(q)).first()
        if c:
            return {"status": "ok", "customer": _customer_brief(c), "candidates": [],
                    "message": ""}

    c = base.filter(Customer.customer_name == q).first()
    if c:
        return {"status": "ok", "customer": _customer_brief(c), "candidates": [],
                "message": ""}

    like = f"%{_escape_like(q)}%"
    fuzzy = (base.filter(Customer.customer_name.ilike(like, escape=_LIKE_ESCAPE_CHAR))
             .order_by(Customer.id).limit(_MAX_CANDIDATES).all())
    candidates = [{"id": c.id, "name": c.customer_name} for c in fuzzy]
    if len(candidates) == 1:
        return {"status": "ok", "customer": _customer_brief(fuzzy[0]),
                "candidates": [], "message": ""}
    if candidates:
        return {"status": "ambiguous", "customer": None, "candidates": candidates,
                "message": f"客户「{q}」不唯一/不精确，请从候选中选择"}

    return {"status": "missing", "customer": None, "candidates": [],
            "message": f"未找到客户「{q}」"}


def list_customer_devices(customer_id: int,
                          limit: int = _MAX_CUSTOMER_DEVICES) -> List[Dict[str, Any]]:
    """客户的设备清单摘要（按 id 升序，超限截断由调用方提示）。"""
    from app.models.device import Device

    rows = (
        Device.query
        .filter(Device.customer_id == customer_id)
        .filter(Device.deleted_at.is_(None))
        .order_by(Device.id)
        .limit(limit + 1)
        .all()
    )
    return [_device_brief(d) for d in rows[:limit]]


def _device_brief(d) -> Dict[str, Any]:
    """设备精简序列化（capability 与候选共用）。"""
    from app.core.enums import DeviceStatus
    _STATUS_MAP = {
        DeviceStatus.ONLINE: "online",
        DeviceStatus.OFFLINE: "offline",
        DeviceStatus.AVAILABLE: "available",
        DeviceStatus.MAINTENANCE: "maintenance",
        DeviceStatus.RESERVED: "reserved",
    }
    return {
        "id": d.id,
        "name": d.device_name,
        "hostname": d.hostname,
        "device_type": d.device_type,
        "device_subtype": d.device_subtype,
        "status": _STATUS_MAP.get(d.status, "unknown"),
        "ip": d.management_ip,
        "model": d.device_model,
    }


def resolve_device(query: Any, device_types: Optional[List[str]] = None) -> Dict[str, Any]:
    """按 ID / 名称 / 主机名 / 管理IP 三级解析设备。

    Args:
        query: 设备名、主机名、管理 IP 或数字 ID。
        device_types: 限定设备类型（如 ["network"]），类型不匹配返回 missing 提示。

    Returns:
        {"status": "ok"|"ambiguous"|"missing",
         "device": {...}|None, "candidates": [{id,name,...}...], "message": str}
    """
    from sqlalchemy import or_
    from app.models.device import Device

    q = _clean_query(query)
    if not q:
        return {"status": "missing", "device": None, "candidates": [],
                "message": "设备参数为空"}

    base = Device.query.filter(Device.deleted_at.is_(None))
    if device_types:
        base = base.filter(Device.device_type.in_(device_types))

    if q.isdigit():
        d = base.filter(Device.id == int(q)).first()
        if d:
            return {"status": "ok", "device": _device_brief(d), "candidates": [],
                    "message": ""}

    exact = (
        base.filter(or_(
            Device.device_name == q,
            Device.hostname == q,
            Device.management_ip == q,
        ))
        .order_by(Device.id)
        .limit(_MAX_CANDIDATES)
        .all()
    )
    if len(exact) == 1:
        return {"status": "ok", "device": _device_brief(exact[0]), "candidates": [],
                "message": ""}
    if len(exact) > 1:
        return {"status": "ambiguous", "device": None,
                "candidates": [_device_brief(d) for d in exact],
                "message": f"「{q}」匹配多台设备（不同主机/端口命中），请从候选确认"}

    like = f"%{_escape_like(q)}%"
    fuzzy = (
        base.filter(or_(
            Device.device_name.ilike(like, escape=_LIKE_ESCAPE_CHAR),
            Device.hostname.ilike(like, escape=_LIKE_ESCAPE_CHAR),
        ))
        .order_by(Device.id)
        .limit(_MAX_CANDIDATES)
        .all()
    )
    if len(fuzzy) == 1:
        return {"status": "ok", "device": _device_brief(fuzzy[0]), "candidates": [],
                "message": ""}
    if fuzzy:
        return {"status": "ambiguous", "device": None,
                "candidates": [_device_brief(d) for d in fuzzy],
                "message": f"「{q}」匹配到多个相近设备，请从候选确认"}
    return {"status": "missing", "device": None, "candidates": [],
            "message": f"未找到设备「{q}」（按名称/主机名/管理IP 均无命中）"}
