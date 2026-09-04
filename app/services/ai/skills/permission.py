# -*- coding: utf-8 -*-
"""技能级权限聚合校验。

技能执行前，聚合其引用到的所有 capability 的权限要求，统一判断当前用户是否满足。
不在路由层单独判断每个 capability 的权限。
"""
from typing import Set

from app.services.ai.capabilities.registry import get_required_permission
from app.services.ai.skills.schema import SkillSpec


def collect_required_permissions(skill) -> Set[str]:
    """收集技能声明的所有权限码。

    兼容两类技能规格（鸭子类型，避免循环 import）：
    - Tier1 SkillSpec：按 steps 迭代，capability 步骤贡献权限，llm/route 步骤不贡献；
    - AgenticSkillSpec：无 steps，权限面即 allowed_capabilities 白名单
      （与 runner 逐 capability 校验的语义一致）。
    """
    perms: Set[str] = set()
    steps = getattr(skill, "steps", None)
    if steps is not None:
        for step in steps:
            if step.type == "capability":
                p = get_required_permission(step.call)
                if p:
                    perms.add(p)
    else:
        for name in getattr(skill, "allowed_capabilities", []) or []:
            p = get_required_permission(name)
            if p:
                perms.add(p)
    return perms


class SkillPermissionDenied(Exception):
    """技能执行所需权限未满足。"""

    def __init__(self, missing: Set[str]):
        self.missing = missing
        super().__init__(f"missing permissions: {missing}")


def check_skill_permission(skill, user_permissions: Set[str]) -> None:
    """校验用户权限是否覆盖技能所需权限，缺失则抛 SkillPermissionDenied。"""
    required = collect_required_permissions(skill)
    missing = required - user_permissions
    if missing:
        raise SkillPermissionDenied(missing)
