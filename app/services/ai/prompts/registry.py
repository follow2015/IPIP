# -*- coding: utf-8 -*-
"""Prompt 模板注册表。

技能 YAML 的 llm/route 步骤只能引用这里注册过的模板名，不允许内联 prompt 原文。
内容审查责任留在代码 review 环节，不依赖技能 YAML 评审者。
"""
from typing import Dict, List, Optional


class PromptTemplate:
    """一个 prompt 模板：system + user_tpl + 可选 allowed_outputs。

    allowed_outputs 用于 route 步骤：限定 LLM 只能返回这些值之一。
    """

    def __init__(self, name: str, system: str, user_tpl: str,
                 allowed_outputs: Optional[List[str]] = None):
        self.name = name
        self.system = system
        self.user_tpl = user_tpl
        self.allowed_outputs = allowed_outputs

    def render_user(self, ctx: dict) -> str:
        """用 ctx 字典填充 user_tpl 占位符。"""
        return self.user_tpl.format(**ctx)


_REGISTRY: Dict[str, PromptTemplate] = {}


def register_prompt(name: str, system: str, user_tpl: str,
                    allowed_outputs: Optional[List[str]] = None) -> None:
    """注册一个 prompt 模板。同名覆盖（开发期热重载友好）。"""
    _REGISTRY[name] = PromptTemplate(name, system, user_tpl, allowed_outputs)


def get_prompt(name: str) -> Optional[PromptTemplate]:
    """取模板；未注册返回 None。"""
    return _REGISTRY.get(name)
