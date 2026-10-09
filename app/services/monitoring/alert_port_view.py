# -*- coding: utf-8 -*-
"""告警「端口」读取期还原 —— 让**存量** Trap 告警也能看出是哪个端口。


Trap 报文只报"哪个 ifIndex 的接口状态变了"，端口名必须从**同批 varbind** 还原。
2026-10-08 起新入箱的告警已在 payload 里写 ``port_name`` / ``port_alias`` /
``oper_status`` / ``shutdown``；但**改造前入箱的存量行**没有这些键 —— 它们只在
``payload.varbinds`` 里带着 IF-MIB 原始列（测试机实测 450/450 条携带 ifDescr）。
读取期派生可让存量行**立刻**可读：无需迁移、无需回填、**不改写历史语义**
（与 ``monitor_alert_outbox_repository.delivery_summary`` 同一思路）。


三条，任一条都足以否决：

1. **ifIndex 是设备本地编号，不是全局标识** —— 同一台设备的 ``ifIndex=10`` 是
   ``10GE1/0/5``，换一台设备可能完全是另一个端口 ⇒ "加一列" 说不通，必须与
   ``device_id`` 组成复合键才成立；
2. **SSH / 其它采集路径根本不产生 ifIndex** —— CLI 侧端口告警的 ``index`` 直接
   就是端口名（见 ``port_status_changed``），该列对那类设备**恒为 NULL**，
   是个永远填不满的列；
3. 最要紧的是**不需要** —— 这条告警自己的 payload 里就带着端口名。


``10`` 对运维没有可读性。真正无从还原时（非 IF-MIB 的 trap、或该条报文确实没带
IF-MIB 列）**如实返回 None**，由调用方显示 "-"：不编造、不猜 —— 猜错会把运维
引到错误的端口上。
"""
from __future__ import annotations

from typing import Any, Optional

from app.services.monitoring import if_mib

_MASK = "***"


def _text_or_none(value: Any) -> Optional[str]:
    """归一成"有意义的字符串"，否则 None。

    空白串、布尔、以及脱敏掩码一律视为"没有这个值" —— 它们的共同点是
    **不能作为端口名展示**。
    """
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text or text == _MASK:
        return None
    return text


def resolve_alert_port(payload: Optional[dict]) -> Optional[dict[str, Any]]:
    """从**已落库的告警 payload** 还原端口信息（只读派生，不改写落库内容）。

    Args:
        payload: outbox 行 ``payload_json`` 的解析结果（整条通知体）。

    Returns:
        ``{"index", "name", "alias", "oper_status", "shutdown", "source"}``，
        其中 ``name`` / ``alias`` / ``oper_status`` 可为 None（该列确实没带），
        ``source`` ∈ ``{"payload", "varbinds"}`` 标明来源 —— 便于排障时区分
        "入箱时写好的" 与 "读取时从 varbind 还原的"。

        **该告警与端口无关、或无从还原时返回 None**（而不是空 dict）：调用方
        据 None 直接显示 "-"，无需再区分"空"与"没有"。
    """
    if not isinstance(payload, dict):
        return None
    inner = payload.get("payload")
    if not isinstance(inner, dict):
        return None

    index = inner.get("index")
    index_text = str(index).strip() if index is not None else ""
    index_text = index_text or None

    name = _text_or_none(inner.get("port_name"))
    alias = _text_or_none(inner.get("port_alias"))
    oper = _text_or_none(inner.get("oper_status"))
    shutdown = inner.get("shutdown")

    if name or alias or oper or isinstance(shutdown, bool):
        return {
            "index": index_text,
            "name": name,
            "alias": alias,
            "oper_status": oper,
            "shutdown": shutdown if isinstance(shutdown, bool) else None,
            "source": "payload",
        }

    varbinds = inner.get("varbinds")
    if not index_text or not isinstance(varbinds, list) or not varbinds:
        return None
    iface = if_mib.extract_interface(varbinds, index_text)
    if not iface:
        return None

    name = _text_or_none(iface.get("name"))
    alias = _text_or_none(iface.get("alias"))
    oper = _text_or_none(iface.get("oper_status"))
    admin = _text_or_none(iface.get("admin_status"))
    if not (name or alias or oper or admin):
        return None
    return {
        "index": index_text,
        "name": name,
        "alias": alias,
        "oper_status": oper,
        "shutdown": bool(iface.get("admin_down")) if admin else None,
        "source": "varbinds",
    }


__all__ = ["resolve_alert_port"]
