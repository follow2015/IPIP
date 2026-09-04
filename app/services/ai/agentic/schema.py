# -*- coding: utf-8 -*-
"""Agentic 技能 schema：frontmatter 元数据校验。"""
from typing import List, Optional

from pydantic import BaseModel, Field


class AgenticSkillSpec(BaseModel):
    name: str
    title: Optional[str] = None
    description: str = ""
    category: str = "agentic"
    allowed_capabilities: List[str] = Field(default_factory=list)
    allowed_skills: List[str] = Field(default_factory=list)
    max_iterations: int = 8
    triggers: List[str] = Field(default_factory=list)
