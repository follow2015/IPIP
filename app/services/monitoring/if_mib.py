# -*- coding: utf-8 -*-
"""IF-MIB 接口表语义（标准 MIB，故内置，不进配置）。

**为什么这个模块存在**：SNMP Trap 报文里的端口信息全部来自 IF-MIB 接口表的
**同一实例**（``ifIndex``）—— trap 只告诉你"哪个索引的接口状态变了"，"索引 10
是哪个端口"必须靠同批 varbind 里的列数据还原。实测（2026-10-08 真实库 450 条
linkDown/linkUp）**每一台设备的每一条 trap 都携带 ifDescr**，但原实现只抽了
``ifIndex`` 做去重键、把端口名丢掉了 ⇒ 告警只显示「实例: 10」，运维看不出是
哪个端口，只能登设备去数。

**为什么可以内置而不做成配置**：IF-MIB（RFC 2863 / 1213）是**标准** MIB，OID
与取值语义全厂商一致；相比之下 ``TRAP_CUSTOM_RULES`` 存在是因为厂商私有 trap
OID 无法穷举。把标准 MIB 也塞进配置，等于让每个站点手抄一遍同样的 OID，抄错
了还会静默丢端口名。

**为什么优先 ifName 再 ifDescr**：与采集侧 ``snmp_port_collector`` 的既有优先级
保持一致（见其模块 docstring）—— 两者对"这个端口叫什么"必须给出同一个答案，
否则同一端口在告警里和端口列表里会显示两个名字。

**ifAlias 不进标题**：它是运维随手备注（"上联至核心交换机"），长度不可控、
可能为空或只有空格。标题要用**物理端口名**（运维照着去插拔的那个名字），
ifAlias 放正文作为补充。

**为什么没有"查库兜底"**：曾计划在 varbind 缺 ifDescr 时按 ``ifIndex`` 去库里
反查端口名，**实测不可行**（2026-10-08）——全库**没有任何列存 ifIndex**：
``network_ports`` 只有 ``slot``/``card``/``port_number``（由 ``port_name`` 解析
而来），``snmp_port_collector`` 虽然按 ifIndex 遍历整张接口表，但只在内存里当
连接键用完即弃（见其 ``port_rows`` 的键集合）。硬按 ``port_number`` 猜会把
``ifIndex=10`` 猜成 ``10GE1/0/10``（实际是 ``10GE1/0/5``），**把运维引到错误的
端口上**，比不显示更糟。要做可靠兜底必须先给端口表加 ifIndex 列并在采集侧
持久化，属独立改动；在那之前一律退回显示 ifIndex。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

IF_INDEX_PREFIX = "1.3.6.1.2.1.2.2.1.1"

IF_NAME_PREFIX = "1.3.6.1.2.1.31.1.1.1.1"
IF_DESCR_PREFIX = "1.3.6.1.2.1.2.2.1.2"
IF_ALIAS_PREFIX = "1.3.6.1.2.1.31.1.1.1.18"
IF_ADMIN_STATUS_PREFIX = "1.3.6.1.2.1.2.2.1.7"
IF_OPER_STATUS_PREFIX = "1.3.6.1.2.1.2.2.1.8"

ADMIN_DOWN_VALUE = "2"

IF_STATUS_NAMES: dict[str, str] = {
    "1": "up",
    "2": "down",
    "3": "testing",
    "4": "unknown",
    "5": "dormant",
    "6": "notPresent",
    "7": "lowerLayerDown",
}


def is_if_index_rule(index_varbind: Optional[str]) -> bool:
    """规则的 ``index_varbind`` 是否即 IF-MIB ``ifIndex``。

    这是**唯一**判据：ifIndex 按定义就是 IF-MIB 的接口实例号，所以"规则的索引
    取自 ifIndex 列" ⟺ "该索引可用于查 IF-MIB 的其它列"。无需让站点在
    ``TRAP_CUSTOM_RULES`` 里手抄一遍 IF-MIB OID，也就不会抄错。
    """
    if not index_varbind:
        return False
    return str(index_varbind).strip().lstrip(".") == IF_INDEX_PREFIX


def _text(value: Any) -> str:
    """把 varbind 值统一成文本（兼容 pysnmp 值对象与裸 str/bytes）。"""
    pretty = getattr(value, "prettyPrint", None)
    if callable(pretty):
        try:
            return str(pretty())
        except Exception:
            logger.debug(
                "prettyPrint() 取值失败，退回 str()：value_type=%s",
                type(value).__name__, exc_info=True,
            )
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    return str(value)


def _instance_text(varbinds, prefix: str, instance: str) -> Optional[str]:
    """取 ``prefix.instance`` 这一条 varbind 的文本值；无此条返回 None。

    [WARN] 必须按**完整实例**比对（``oid == prefix + "." + instance``），不能
    用 ``str`` 前缀：``...2.1`` 是 ``...2.10`` 的字符串前缀，端口 1 会把端口 10
    的值顶掉。OID 是点分弧段树，判据必须落到弧段边界上。
    """
    want = f"{prefix}.{instance}"
    for oid, value in varbinds or ():
        if str(oid).strip().lstrip(".") == want:
            return _text(value)
    return None


def status_name(raw: Optional[str]) -> Optional[str]:
    """IF-MIB 状态码 → 语义名（``"2"`` → ``"down"``）；未知值原样返回。"""
    if raw is None:
        return None
    key = str(raw).strip()
    if not key:
        return None
    return IF_STATUS_NAMES.get(key, key)


def extract_interface(varbinds, index: Optional[str]) -> dict[str, Any]:
    """从一批 trap varbinds 里还原 ``ifIndex`` 对应的接口信息。

    Args:
        varbinds: ``[(oid, value), ...]``。**必须是脱敏前的原始列表** —— 脱敏
            会把敏感 OID 的值换成 ``***``，虽然 IF-MIB 各列都不在敏感表内，
            但把顺序约束写进契约比赌"当前这版敏感表不含它"更稳。
        index: 接口实例号（``ifIndex`` 的字符串形式），来自
            ``TrapRuleMatcher.extract_index``；None 直接返回空结果。

    Returns:
        dict，键含义：
        - ``name``: 端口名（ifName → ifDescr），都没有则 None
        - ``alias``: ifAlias 备注（可能 None）
        - ``admin_status`` / ``oper_status``: 语义名（如 ``"down"``）或 None
        - ``admin_down``: 是否**人为关闭**（admin=2）—— 用于把"运维 shutdown"
          与"真断链"分开，前者不该刷 critical
        任何一列缺失都只是该键为 None，**不编造**：拿不到端口名时宁可让调用方
        退回显示 ``ifIndex``，也不能猜一个名字（猜错会把运维引到错误的端口上）。
    """
    if not index:
        return {}
    if_name = _instance_text(varbinds, IF_NAME_PREFIX, index)
    if_descr = _instance_text(varbinds, IF_DESCR_PREFIX, index)
    alias = _instance_text(varbinds, IF_ALIAS_PREFIX, index)
    admin_raw = _instance_text(varbinds, IF_ADMIN_STATUS_PREFIX, index)
    oper_raw = _instance_text(varbinds, IF_OPER_STATUS_PREFIX, index)
    return {
        "name": (if_name or if_descr or None),
        "alias": (alias.strip() if alias and alias.strip() else None),
        "admin_status": status_name(admin_raw),
        "oper_status": status_name(oper_raw),
        "admin_down": (
            str(admin_raw).strip() == ADMIN_DOWN_VALUE if admin_raw is not None else False
        ),
    }


__all__ = [
    "ADMIN_DOWN_VALUE",
    "IF_ALIAS_PREFIX",
    "IF_ADMIN_STATUS_PREFIX",
    "IF_DESCR_PREFIX",
    "IF_INDEX_PREFIX",
    "IF_NAME_PREFIX",
    "IF_OPER_STATUS_PREFIX",
    "IF_STATUS_NAMES",
    "extract_interface",
    "is_if_index_rule",
    "status_name",
]
