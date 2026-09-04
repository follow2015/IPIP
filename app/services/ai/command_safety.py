# -*- coding: utf-8 -*-
"""命令安全校验层：诊断命令白名单 + 修复命令白名单 + 四层校验。

设计文档第七节：remedial 命令是 LLM 自由生成的任意字符串时，一旦执行层直接复用
下发通道，等同于任意命令执行——这与"执行锁死"原则直接矛盾。四层校验缺一不可：
1. 模板化：remedial 命令必须是 command_key + params，不接受任意字符串。
2. 修复白名单（独立于诊断白名单）。
3. 强制确认：type == "remedial" 一律 requires_confirmation = true，后端强制。
4. 执行前置：下发前自动备份 running-config；高风险命令强制要求 rollback_command_key。

回滚链路本身也要有闸门：
- rollback_command_key 指向的命令同样必须在白名单中登记为独立条目。
- 未登记 rollback 的 brand 组合一律拒绝下发，不降级为"无回滚可执行"。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)



_COMMAND_FAMILIES = ("h3c", "huawei", "cisco")

_ENTERPRISE_NO_TO_FAMILY: Dict[str, str] = {
    "25506": "h3c",     # H3C Comware
    "2011": "huawei",   # Huawei VRP / TaiShan
    "9": "cisco",       # Cisco
}

_BRAND_NAME_FAMILY_KEYWORDS = (
    ("h3c", "h3c"),
    ("huawei", "huawei"),
    ("cisco", "cisco"),
)


def resolve_command_family(brand: Any) -> Optional[str]:
    """把 device.brand 解析为命令族名（h3c/huawei/cisco）。

    兼容三种输入形态：
    1. 命令族名本身（"h3c" / "H3C Comware"）—— 老数据与测试替身常用；
    2. SNMP enterprise 号（"25506"）—— 生产库实际存值；
    3. 品牌全称（"Huawei VRP"）—— 自建厂商或 DB 查询结果。

    解析顺序按开销递增：族名 → enterprise 号静态表 → 名称关键词 → DB 兜底。
    DB 查询仅在静态表未命中时发生，用于支持用户自行登记的厂商。

    Args:
        brand: device.brand 原值，可能是数字字符串、品牌名或 None。

    Returns:
        命令族名；无法确定时返回 None（调用方应按「未知厂商」处理，不猜测）。
    """
    if brand is None:
        return None
    raw = str(brand).strip()
    if not raw:
        return None
    lowered = raw.lower()

    for family in _COMMAND_FAMILIES:
        if lowered == family:
            return family

    family = _ENTERPRISE_NO_TO_FAMILY.get(lowered)
    if family:
        return family

    for keyword, fam in _BRAND_NAME_FAMILY_KEYWORDS:
        if keyword in lowered:
            return fam

    return _resolve_family_from_db(lowered)


def _resolve_family_from_db(lowered_brand: str) -> Optional[str]:
    """查 monitor_vendor_brands 把 enterprise 号换成品牌全称再匹配命令族。

    仅在静态表未命中时调用，用于支持用户自行登记的厂商。数据库不可用或
    无匹配时返回 None（不影响诊断主流程，由调用方降级为「未知厂商」）。
    """
    try:
        from app.persistence.monitor_vendor_brand_repository import (
            MonitorVendorBrandRepository,
        )
        from extensions import db

        row = (
            MonitorVendorBrandRepository(db.session)
            .find_by_enterprise_no(lowered_brand)
        )
    except Exception as e:  # noqa: BLE001 - DB 不可用时降级为未命中
        logger.warning("resolve command family from db failed brand=%s: %s",
                       lowered_brand, e)
        return None
    if row is None:
        return None
    brand_name = (getattr(row, "brand_name", "") or "").lower()
    for keyword, fam in _BRAND_NAME_FAMILY_KEYWORDS:
        if keyword in brand_name:
            return fam
    return None



_DIAGNOSTIC_COMMAND_WHITELIST: Dict[str, Dict[str, str]] = {
    "h3c": {
        "session_statistics": "display session statistics",
        "session_relation": "display session relation",
        "cpu_usage": "display cpu-usage",
        "memory": "display memory",
        "interface_brief": "display interface brief",
        "logbuffer": "display logbuffer",
        "arp_all": "display arp all",
        "mac_address": "display mac-address",
    },
    "huawei": {
        "cpu_usage": "display cpu-usage",
        "memory": "display memory-usage",
        "interface_brief": "display interface brief",
        "session_statistics": "display session statistics",
        "logbuffer": "display logbuffer",
        "arp_all": "display arp all",
        "mac_address": "display mac-address",
    },
    "cisco": {
        "cpu_usage": "show processes cpu",
        "memory": "show memory statistics",
        "interface_brief": "show ip interface brief",
        "logbuffer": "show logging",
        "arp_all": "show ip arp",
        "mac_address": "show mac address-table",
    },
}

_BACKUP_COMMAND_WHITELIST: Dict[str, str] = {
    "h3c": "display current-configuration",
    "huawei": "display current-configuration",
    "cisco": "show running-config",
}


def get_backup_command(brand: Any) -> Optional[str]:
    """取该厂商备份 running-config 的只读命令。

    Args:
        brand: device.brand 原值（enterprise 号或厂商名）。

    Returns:
        备份命令字符串；厂商未登记时返回 None（调用方应中止下发，
        不做无备份的变更）。
    """
    family = resolve_command_family(brand)
    if family is None:
        return None
    return _BACKUP_COMMAND_WHITELIST.get(family)


def get_diagnostic_command(brand: Any, command_key: str) -> Optional[str]:
    """按厂商 + command_key 查诊断命令模板。

    Args:
        brand: device.brand 原值（enterprise 号或厂商名，见 resolve_command_family）。
        command_key: 预定义命令键（如 session_statistics）。

    Returns:
        命令字符串；未登记返回 None。
    """
    family = resolve_command_family(brand)
    if family is None:
        return None
    return _DIAGNOSTIC_COMMAND_WHITELIST.get(family, {}).get(command_key)


def is_diagnostic_command_allowed(brand: Any, command_key: str) -> bool:
    """诊断命令是否在白名单内（供 ssh.diagnostic_show 调用前校验）。"""
    return get_diagnostic_command(brand, command_key) is not None



_REMEDIAL_COMMAND_WHITELIST: Dict[str, Dict[str, Dict[str, Any]]] = {
    "syn_cookie_enable": {
        "h3c": {
            "template": "attack-defense policy {policy_id}\n syn-cookie enable",
            "risk": "high",
            "rollback": "syn_cookie_disable",
            "params_schema": {"policy_id": {"type": "int", "min": 1, "max": 65535}},
            "platform_note": (
                "H3C Comware：本命令仅修改攻击防范策略，需另行执行 "
                "attack-defense apply policy {policy_id} 应用后才生效。"
            ),
        },
        "huawei": {
            "template": "anti-attack enable",
            "risk": "high",
            "rollback": "syn_cookie_disable",
            "params_schema": {},
            "platform_note": (
                "华为 VRP（S 系列交换机 / AR 路由器）：anti-attack enable 会同时"
                "使能畸形报文、分片报文等全部攻击防范功能（非仅 SYN flood），"
                "可能有额外性能开销。USG 防火墙请用 firewall defend "
                "syn-flood enable（尚未登记）。"
            ),
        },
        "cisco": {
            "template": "ip tcp intercept list {acl_id}",
            "risk": "high",
            "rollback": "syn_cookie_disable",
            "params_schema": {"acl_id": {"type": "int", "min": 1, "max": 2699}},
            "platform_note": (
                "Cisco IOS TCP intercept：依赖编号为 {acl_id} 的 ACL 已存在"
                "（如 access-list {acl_id} permit tcp any host <目标IP>）。"
                "ACL 不存在时本命令会被接受但不生效。推荐使用扩展 ACL"
                "（100-199 / 2000-2699）。ASA、NX-OS 语法不同，尚未登记。"
            ),
        },
    },
    "syn_cookie_disable": {
        "h3c": {
            "template": "attack-defense policy {policy_id}\n undo syn-cookie enable",
            "risk": "low",
            "rollback": None,  # 回滚命令本身无需回滚
            "params_schema": {"policy_id": {"type": "int", "min": 1, "max": 65535}},
        },
        "huawei": {
            "template": "undo anti-attack enable",
            "risk": "low",
            "rollback": None,
            "params_schema": {},
        },
        "cisco": {
            "template": "no ip tcp intercept list {acl_id}",
            "risk": "low",
            "rollback": None,
            "params_schema": {"acl_id": {"type": "int", "min": 1, "max": 2699}},
        },
    },
}


_PARAM_PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class CommandSafetyError(Exception):
    """命令安全校验失败。"""


def _validate_params(params: Dict[str, Any], schema: Dict[str, Dict[str, Any]]) -> None:
    """按 schema 校验模板参数类型与范围，防止模板参数注入。

    Args:
        params: LLM 提供的参数（如 {"policy_id": 1}）。
        schema: 白名单中登记的参数 schema（如 {"policy_id": {"type": "int", "min": 1, "max": 65535}}）。

    Raises:
        CommandSafetyError: 参数缺失/类型错误/越界。
    """
    for name, spec in schema.items():
        if name not in params:
            raise CommandSafetyError(f"缺少必填参数：{name}")
        value = params[name]
        expected_type = spec.get("type", "str")
        if expected_type == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                raise CommandSafetyError(f"参数 {name} 必须为整数，实际 {type(value).__name__}")
            if "min" in spec and value < spec["min"]:
                raise CommandSafetyError(f"参数 {name}={value} 低于下限 {spec['min']}")
            if "max" in spec and value > spec["max"]:
                raise CommandSafetyError(f"参数 {name}={value} 超过上限 {spec['max']}")
        elif expected_type == "str":
            if not isinstance(value, str):
                raise CommandSafetyError(f"参数 {name} 必须为字符串，实际 {type(value).__name__}")
            if re.search(r"[\n\r;`|]", value):
                raise CommandSafetyError(f"参数 {name} 含危险字符")


def render_remedial_command(command_key: str, brand: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """渲染修复命令（四层校验主入口）。

    设计文档第七节四层校验：
    1. 模板化：command_key 必须在白名单中，不接受任意字符串。
    2. 修复白名单：按 brand 查模板，未登记的 brand 组合拒绝。
    3. 参数校验：params 过类型与范围校验，防模板参数注入。
    4. 回滚登记：高风险命令必须有 rollback_command_key，且 rollback 本身也在白名单中。

    Args:
        command_key: 修复命令键（如 syn_cookie_enable）。
        brand: 设备厂商。
        params: 模板参数（如 {"policy_id": 1}）。

    Returns:
        {"command": <渲染后命令字符串>, "risk": <high/medium/low>,
         "rollback_command_key": <str|None>, "requires_confirmation": True,
         "platform_note": <平台前置/后置条件说明|None>}

    Raises:
        CommandSafetyError: 任一层校验失败。
    """
    entry = _REMEDIAL_COMMAND_WHITELIST.get(command_key)
    if entry is None:
        raise CommandSafetyError(f"修复命令 {command_key} 不在白名单中，拒绝下发")

    family = resolve_command_family(brand)
    brand_entry = entry.get(family) if family else None
    if brand_entry is None:
        raise CommandSafetyError(
            f"修复命令 {command_key} 未在厂商 {brand} 下登记，拒绝下发"
        )

    schema = brand_entry.get("params_schema", {})
    _validate_params(params, schema)

    template = brand_entry["template"]
    placeholders = set(_PARAM_PLACEHOLDER_PATTERN.findall(template))
    missing = placeholders - set(params.keys())
    if missing:
        raise CommandSafetyError(f"模板占位符 {missing} 未提供参数")
    try:
        command = template.format(**{k: params[k] for k in placeholders})
    except (ValueError, KeyError, IndexError) as e:
        raise CommandSafetyError(f"修复命令 {command_key} 模板非法：{e}") from e

    risk = brand_entry.get("risk", "high")
    rollback_key = brand_entry.get("rollback")

    if risk == "high" and not rollback_key:
        raise CommandSafetyError(
            f"高风险命令 {command_key} 未登记 rollback_command_key，拒绝下发"
        )
    if rollback_key:
        rollback_entry = _REMEDIAL_COMMAND_WHITELIST.get(rollback_key)
        if rollback_entry is None:
            raise CommandSafetyError(
                f"回滚命令 {rollback_key} 不在白名单中，拒绝下发（回滚路径不能绕过白名单）"
            )
        rollback_brand_entry = rollback_entry.get(family) if family else None
        if rollback_brand_entry is None:
            raise CommandSafetyError(
                f"回滚命令 {rollback_key} 未在厂商 {brand} 下登记，拒绝下发"
            )
        rollback_schema = rollback_brand_entry.get("params_schema", {})
        if set(rollback_schema) != set(schema):
            raise CommandSafetyError(
                f"回滚命令 {rollback_key} 的参数（{sorted(rollback_schema)}）"
                f"与主命令 {command_key} 的参数（{sorted(schema)}）不一致，拒绝下发"
            )

    note = brand_entry.get("platform_note")
    if note:
        try:
            note = note.format(**{k: params[k] for k in placeholders})
        except (KeyError, ValueError, IndexError):
            note = None

    return {
        "command": command,
        "risk": risk,
        "rollback_command_key": rollback_key,
        "requires_confirmation": True,  # 后端强制，不采信 LLM 输出
        "platform_note": note,
    }


def enforce_confirmation(proposed_commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """后端强制 remedial 命令 requires_confirmation=True，过滤无效命令。

    设计文档第五节：type == "remedial" 一律 requires_confirmation = true，后端强制，
    不采信 LLM 输出（LLM 可能误判为 false 导致高危命令未经确认下发）。
    同时过滤空字符串/无 command_key 的命令。

    Args:
        proposed_commands: LLM 输出的 proposed_commands 列表。

    Returns:
        清洗后的命令列表（remedial 类强制 requires_confirmation=True）。
    """
    cleaned = []
    for cmd in proposed_commands:
        if not isinstance(cmd, dict):
            continue
        command_key = cmd.get("command_key")
        if not command_key or not isinstance(command_key, str):
            continue  # 过滤无 command_key 的命令
        cmd_type = cmd.get("type", "diagnostic")
        if cmd_type == "remedial":
            cmd = dict(cmd)  # 不修改原对象
            cmd["requires_confirmation"] = True
        cleaned.append(cmd)
    return cleaned
