# -*- coding: utf-8 -*-
"""LDAP 组 → RBAC 角色映射（T3.5，纯函数层）。

为什么单独成模块、且只放纯函数：
  客户 AD/OpenLDAP 的 schema 差异最大（memberOf 可能是完整 DN、可能只有 CN、
  也可能走 groupOfNames 反查），「怎么解析」与「怎么落库」必须分开 ——
  前者可被穷举测试，后者才碰数据库。本模块不 import ldap3、不 import db、
  不读 Flask app，任何一行都可单独断言。

配置格式（``LDAP_GROUP_ROLE_MAP``）：
  - 对象/JSON：``{"IPIP-Ops": "operator", "CN=Admins,OU=G,DC=c,DC=l": "admin"}``
  - 分隔串：``IPIP-Ops=>operator;CN=Admins,OU=G,DC=c,DC=l=>admin``

  分隔串里 **条目之间** 用 ``;`` / ``|`` / 换行；**组与角色之间** 用 ``=>``
  （推荐），也接受 ``:`` 与 ``=``。DN 里全是 ``=``，所以后两者**仅在该条目里
  恰好只出现一次时**才可用于拆分 —— 否则说明多半是把条目分隔符写错了
  （例如用逗号或空格连接多条），此时必须报错。详见 :func:`_split_entry`。

匹配口径（只做**精确键**匹配，绝不做子串匹配）：
  一个组 DN ``CN=IPIP-Ops,OU=Groups,DC=corp,DC=local`` 会被展开成键集合
  ``{完整dn, ipip-ops, groups}`` —— 即逐个 RDN 取下 **cn/ou** 的值。
  刻意不收 ``dc=`` 的值：那会让 ``corp`` 这类域组件匹配到域下所有对象，
  等于把整棵树都授了权。
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping

_TOKEN_RE = re.compile(r"^[^\s,;=\"|:]+$")
_SEPARATOR = "=>"
_ENTRY_SPLIT_RE = re.compile(r"[;|\n]")
_SHORT_KEY_ATTRS = frozenset({"cn", "ou"})


class GroupRoleMapError(ValueError):
    """``LDAP_GROUP_ROLE_MAP`` 配置无法解析 —— 属配置错误，应在启动/自检时暴露。"""


def _split_entry(entry: str) -> tuple[str, str]:
    """把单条 ``组<分隔符>角色`` 拆成 ``(组, 角色)``；拆不出唯一结果就报错。

    分隔符按优先级：``=>``（规范写法，DN 里不可能出现）→ ``:`` → ``=``。
    后两者**要求该条目里恰好只出现一次**，因为它们本身是 DN 的组成部分。

    为什么必须限制出现次数、而不能「按最后一个分隔符切开就行」：
      多条映射写错条目分隔符时（例如用逗号或空格并列），整串会被当成**一条**
      映射切开，键和值都是垃圾。垃圾键永远匹配不上任何组，症状是「所有人都被
      降级到默认角色」—— 不报错、日志干净、配置看着还挺对，是最难查的一类故障。
      限制次数后这种串直接解析失败，启动期就暴露。
    """
    if _SEPARATOR in entry:
        key, _, value = entry.partition(_SEPARATOR)
        return key, value
    for sep in (":", "="):
        if entry.count(sep) == 1:
            key, _, value = entry.partition(sep)
            return key, value
    raise GroupRoleMapError(
        "LDAP_GROUP_ROLE_MAP 条目无法解析（应为 组=>角色，多条之间用 ; 或 | 分隔）: "
        f"{entry!r}"
    )


def parse_group_role_map(raw: Any) -> dict[str, str]:
    """把配置归一成 ``{组标识(小写): 角色名}``。

    接受 dict、JSON 字符串、``组=>角色`` 分隔串（条目间用 ``;`` / ``|`` / 换行）；
    空/None 返回空映射。条目缺失任一侧、角色名含空白或逗号等形态异常时抛
    :class:`GroupRoleMapError` —— 宁可启动即失败，也不静默丢一条映射
    （丢配置 = 静默少授权或多授权）。
    """
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        items = list(raw.items())
    else:
        text = str(raw).strip()
        if not text:
            return {}
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise GroupRoleMapError(f"LDAP_GROUP_ROLE_MAP 不是合法 JSON: {exc}") from exc
            if not isinstance(parsed, Mapping):
                raise GroupRoleMapError("LDAP_GROUP_ROLE_MAP 的 JSON 根节点必须是对象")
            items = list(parsed.items())
        else:
            items = []
            for chunk in _ENTRY_SPLIT_RE.split(text):
                entry = chunk.strip()
                if not entry:
                    continue
                items.append(_split_entry(entry))

    mapping: dict[str, str] = {}
    for key, value in items:
        k = str(key).strip()
        v = str(value).strip()
        if not k or not v:
            raise GroupRoleMapError(f"LDAP_GROUP_ROLE_MAP 条目为空: {key!r} => {value!r}")
        if not _TOKEN_RE.match(v):
            raise GroupRoleMapError(
                "角色名含非法字符（应为单个标识符，不含空白/逗号/分号/等号/竖线/冒号）: "
                f"{v!r}"
            )
        lowered = k.lower()
        if lowered in mapping and mapping[lowered] != v:
            raise GroupRoleMapError(
                f"LDAP_GROUP_ROLE_MAP 中组 {k!r} 被映射到多个角色"
                f"（{mapping[lowered]!r} 与 {v!r}）—— 映射必须唯一"
            )
        mapping[lowered] = v
    return mapping


def expand_group_keys(group_dn: str) -> set[str]:
    """把一个组 DN 展开成可匹配的键集合（完整 DN + 各级 cn/ou 的值）。"""
    if not group_dn:
        return set()
    text = str(group_dn).strip().lower()
    if not text:
        return set()
    keys = {text}
    for rdn in text.split(","):
        if "=" not in rdn:
            continue
        attr, _, value = rdn.partition("=")
        attr, value = attr.strip(), value.strip()
        if attr in _SHORT_KEY_ATTRS and value:
            keys.add(value)
    return keys


def match_groups_to_roles(
    groups: Iterable[str], group_role_map: Mapping[str, str]
) -> list[str]:
    """按配置顺序返回命中的角色名（去重、保序）。未命中返回空列表。

    键在此处再做一次 ``strip().lower()`` 归一：映射表通常已由
    :func:`parse_group_role_map` 归一，但调用方直接传入手写 dict 时（测试、
    程序化构造）不应因为大小写而漏匹配 —— 漏匹配的后果是「该授权的人登不上」，
    属于最难排查的一类故障。
    """
    if not group_role_map:
        return []
    matched_keys: set[str] = set()
    for group in groups or ():
        matched_keys |= expand_group_keys(group)

    roles: list[str] = []
    for key, role in group_role_map.items():
        if str(key).strip().lower() in matched_keys and role not in roles:
            roles.append(role)
    return roles


def resolve_roles(
    groups: Iterable[str],
    group_role_map: Mapping[str, str],
    default_role: str = "",
) -> list[str]:
    """映射角色；没有任何组命中时回落到 ``default_role``（未配置则返回空列表）。

    返回空列表是**有意义的**：调用方据此判定「该账号未被授权任何角色」并拒绝登录
    （fail-close），而不是默默给一个无权限会话。
    """
    roles = match_groups_to_roles(groups, group_role_map)
    if roles:
        return roles
    fallback = (default_role or "").strip()
    return [fallback] if fallback else []
