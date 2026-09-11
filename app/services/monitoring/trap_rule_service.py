# -*- coding: utf-8 -*-
"""
SNMP Trap 规则匹配（P1-1）

Trap OID → 告警规则。规则来源（两层，后者覆盖前者）：
1. **内置默认规则**：SNMPv2-MIB 标准trap（coldStart/warmStart/linkDown/linkUp/
   authenticationFailure/egpNeighborLoss）。v1 generic trap 经 RFC 2576 翻译
   后也落在 ``1.3.6.1.6.3.1.1.5.N``，天然统一。
2. **站点自定义规则**：``TRAP_CUSTOM_RULES``（JSON 数组，见 .env.example），
   用于厂商私有 OID（电源/风扇/温度/BGP 等，各厂商 OID 不同，无法内置穷举）。

规则解析失败（JSON 非法/字段缺失/OID 形态不对）抛 :class:`TrapRuleError`
—— 在 trapd 服务启动期 fail-fast，宁可不起服务也不带病运行静默丢告警。
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

_TRAP_PREFIX = "1.3.6.1.6.3.1.1.5"

DEFAULT_TRAP_RULES: list[dict[str, Any]] = [
    {
        "name": "link_down",
        "match_oid": f"{_TRAP_PREFIX}.3",
        "severity": "critical",
        "title": "端口 LinkDown",
        "content": "设备上报链路中断（IF-MIB::linkDown）",
        "index_varbind": "1.3.6.1.2.1.2.2.1.1",
    },
    {
        "name": "link_up",
        "match_oid": f"{_TRAP_PREFIX}.4",
        "severity": "info",
        "title": "端口 LinkUp",
        "content": "设备上报链路恢复（IF-MIB::linkUp）",
        "index_varbind": "1.3.6.1.2.1.2.2.1.1",
    },
    {
        "name": "authentication_failure",
        "match_oid": f"{_TRAP_PREFIX}.6",
        "severity": "warning",
        "title": "SNMP 认证失败",
        "content": "设备收到携带错误 community 的请求，疑似扫描/误配置",
        "index_varbind": None,
    },
    {
        "name": "cold_start",
        "match_oid": f"{_TRAP_PREFIX}.1",
        "severity": "info",
        "title": "设备冷启动",
        "content": "设备代理冷启动（可能伴随断电重启）",
        "index_varbind": None,
    },
    {
        "name": "warm_start",
        "match_oid": f"{_TRAP_PREFIX}.2",
        "severity": "info",
        "title": "设备热启动",
        "content": "设备代理热启动",
        "index_varbind": None,
    },
    {
        "name": "egp_neighbor_loss",
        "match_oid": f"{_TRAP_PREFIX}.5",
        "severity": "warning",
        "title": "EGP 邻居丢失",
        "content": "设备上报 EGP 邻居丢失",
        "index_varbind": None,
    },
]

_SEVERITIES = {"info", "warning", "critical"}
_OID_RE = re.compile(r"^\.?\d+(\.\d+)*$")
_RULE_FIELDS = {"name", "match_oid", "severity"}


class TrapRuleError(ValueError):
    """``TRAP_CUSTOM_RULES`` 无法解析 —— 启动期 fail-fast。"""


def _normalize_oid(oid: str) -> str:
    """归一化 OID：去前导点。实例后缀（.0 等）由匹配策略处理。"""
    return oid.strip().lstrip(".")


def _validate_rule(rule: Any, source: str) -> dict[str, Any]:
    """校验单条规则结构，失败抛 TrapRuleError（fail-fast，不静默丢弃）。"""
    if not isinstance(rule, dict):
        raise TrapRuleError(f"{source}: 规则必须是对象，得到 {type(rule).__name__}")
    missing = _RULE_FIELDS - set(rule)
    if missing:
        raise TrapRuleError(f"{source}: 缺少必填字段 {sorted(missing)}: {rule!r}")
    name = str(rule["name"]).strip()
    if not name or len(name) > 40 or not re.match(r"^[a-z0-9_\-]+$", name):
        raise TrapRuleError(
            f"{source}: name 须为 ≤40 字符的 [a-z0-9_-] 标识符，得到 {rule['name']!r}"
        )
    oid = str(rule["match_oid"]).strip()
    if not _OID_RE.match(oid):
        raise TrapRuleError(f"{source}: match_oid 不是合法数字 OID: {oid!r}")
    severity = str(rule["severity"]).strip().lower()
    if severity not in _SEVERITIES:
        raise TrapRuleError(
            f"{source}: severity 必须是 info/warning/critical，得到 {rule['severity']!r}"
        )
    index_varbind = rule.get("index_varbind")
    if index_varbind is not None and not str(index_varbind).strip():
        index_varbind = None
    return {
        "name": name,
        "match_oid": _normalize_oid(oid),
        "severity": severity,
        "title": str(rule.get("title") or name),
        "content": str(rule.get("content") or ""),
        "index_varbind": (str(index_varbind).strip() if index_varbind else None),
    }


def parse_custom_rules(raw: Optional[str]) -> list[dict[str, Any]]:
    """解析 ``TRAP_CUSTOM_RULES``（JSON 数组字符串）；空/未配置返回 []。"""
    if raw is None or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise TrapRuleError(f"TRAP_CUSTOM_RULES 不是合法 JSON: {exc}") from exc
    if not isinstance(data, list):
        raise TrapRuleError("TRAP_CUSTOM_RULES 必须是 JSON 数组")
    return [_validate_rule(r, f"TRAP_CUSTOM_RULES[{i}]") for i, r in enumerate(data)]


class TrapRuleMatcher:
    """Trap OID → 规则匹配器（线程安全：只读结构，构造期完成校验）。

    匹配策略：
    1. 精确匹配（含实例后缀的完整 OID，如 ``...5.3.0`` 不常见，先剥后缀再比）；
    2. **最长前缀匹配** —— 厂商私有 trap 形如
       ``1.3.6.1.4.1.9.9.<x>.<y>.<z>``，规则写企业前缀即可命中整族。
    """

    def __init__(self, default_rules=None, custom_rules=None):
        self._rules: list[dict[str, Any]] = []
        for rule in (default_rules if default_rules is not None else DEFAULT_TRAP_RULES):
            self._rules.append(_validate_rule(rule, "DEFAULT_TRAP_RULES"))
        self._rules.extend(custom_rules or [])
        self._exact: dict[str, dict[str, Any]] = {}
        self._prefixes: list[tuple[str, dict[str, Any]]] = []
        for rule in self._rules:
            oid = rule["match_oid"]
            self._exact.setdefault(oid, rule)
            self._prefixes.append((oid, rule))
        self._prefixes.sort(key=lambda item: len(item[0]), reverse=True)

    @property
    def rules(self) -> list[dict[str, Any]]:
        return list(self._rules)

    def match(self, trap_oid: str) -> Optional[dict[str, Any]]:
        """匹配 trap OID；未命中返回 None（调用方落原始日志）。"""
        oid = _normalize_oid(str(trap_oid or ""))
        if not oid:
            return None
        rule = self._exact.get(oid)
        if rule is not None:
            return rule
        for prefix, rule in self._prefixes:
            if oid.startswith(prefix + ".") or oid == prefix:
                return rule
        return None

    def extract_index(self, rule: dict[str, Any], varbinds: list[tuple[str, Any]]) -> Optional[str]:
        """从 varbinds 里按规则的 index_varbind 抽 index（供去重键与展示）。

        ``index_varbind`` 支持两种写法：
        - **OID 前缀**（推荐，纯数字形态可靠）：如 linkDown 取
          ``1.3.6.1.2.1.2.2.1.1``（IF-MIB::ifIndex 列 OID），命中后取
          **前缀之后的剩余段**作为实例 index（``...1.1.5`` → ``5``）。
          项目不内置厂商 MIB，trap varbind 以数字 OID 到达，符号匹配不可靠。
        - **符号名**（兜底）：大小写不敏感地匹配 varbind 的可读名/值文本。
        找不到返回 None。
        """
        want = rule.get("index_varbind")
        if not want:
            return None
        want_s = str(want).strip().lstrip(".")
        if _OID_RE.match(want_s):
            prefix = want_s
            for oid, value in varbinds or []:
                oid_s = _normalize_oid(str(oid))
                if oid_s == prefix:
                    return "0"
                if oid_s.startswith(prefix + "."):
                    return oid_s[len(prefix) + 1:] or "0"
            return None
        want_l = want_s.lower()
        for oid, value in varbinds or []:
            readable = getattr(value, "prettyPrint", None)
            text = readable() if callable(readable) else str(value)
            name_text = str(oid)
            if want_l in name_text.lower() or want_l in text.lower():
                return text
        return None
