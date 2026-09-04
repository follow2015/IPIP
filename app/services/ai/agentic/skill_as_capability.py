# -*- coding: utf-8 -*-
"""把 Tier 1 YAML 技能包装成 agentic runner 可调用的工具，用于混合型技能。"""
from typing import Callable, Optional

from app.services.ai.skills.loader import load_skill, default_skill_dirs
from app.services.ai.skills.engine import WorkflowEngine
from app.services.ai.capabilities.registry import get_capability as _default_get_capability



def call_tier1_skill_as_tool(skill_name: str,
                             user_id: Optional[int] = None,
                             user_permissions: Optional[set] = None) -> Callable[[dict], object]:
    """返回一个包装函数，调用时执行对应 Tier 1 技能。

    B2 修复：传入 user_permissions，engine.run 内部会校验技能所需权限。
    A9 修复：透传 user_id——技能内的设备类 capability 要靠它做数据域校验，
    缺失会被判"无法识别当前用户"而拒绝执行。
    """

    def _tool(args: dict):
        skill = load_skill(skill_name, default_skill_dirs())
        engine = WorkflowEngine(get_capability=_default_get_capability)
        return engine.run(skill, args or {}, user_id=user_id,
                          user_permissions=user_permissions)

    return _tool
