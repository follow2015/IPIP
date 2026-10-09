# -*- coding: utf-8 -*-
"""工单插件 · 装配与开关（同构于 ``collector/runtime.py`` 的 ``build_channels``）。

**显式装配**：候选列表写死在这里。刻意不用 ``pkgutil`` 扫包自动注册 ——
"哪些插件当前生效"必须一眼可数、可审计；自动发现会让某个插件悄悄生效，
也让单测结果依赖目录内容（新增一个文件就改变测试集合是最难排查的那种耦合）。

开关是**双闸**（总开关 + 白名单），照采集侧 ``SCAN_CHANNEL_ENABLED`` +
``allowed_channels`` 的形态：关掉总开关即回到"纯内核 web 工单"，零发版回退。
"""

from __future__ import annotations

from typing import Iterable

from app.services.ticket.plugin_base import TicketPlugin
from app.services.ticket.plugins.noop import NoopPlugin

CANDIDATE_PLUGINS: tuple[type[TicketPlugin], ...] = (NoopPlugin,)


def build_ticket_plugins(
    enabled: bool = False,
    allowed: Iterable[str] | None = None,
) -> list[TicketPlugin]:
    """按开关与白名单装配插件实例。

    三重过滤：总开关 -> 白名单 -> ``is_available()``。最后一重是实例级判断
    （凭据 / 熔断由插件自己回答），前两重是运维意图。

    返回顺序与 ``CANDIDATE_PLUGINS`` 一致（**装配顺序即优先级**，后续内核若要做
    "第一个能处理的插件胜出"，依据就是这个顺序）。
    """
    if not enabled:
        return []
    allow = {str(code) for code in (allowed or ())}
    if not allow:
        return []
    plugins = [cls() for cls in CANDIDATE_PLUGINS if cls.code in allow]
    return [p for p in plugins if p.is_available()]


__all__ = ["CANDIDATE_PLUGINS", "build_ticket_plugins"]
