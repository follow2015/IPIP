# -*- coding: utf-8 -*-
"""加载 SKILL.md：frontmatter 做元数据校验，markdown body 原样作为 system instructions。"""
from pathlib import Path
from typing import List

import frontmatter

from app.services.ai.agentic.schema import AgenticSkillSpec
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _iter_skill_md(dirs: List[str]):
    for d in dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        for f in sorted(p.glob("*/SKILL.md")):
            yield f


def load_agentic_catalog(dirs: List[str]) -> List[dict]:
    """启动仅载元数据（跟 Tier 1 的 load_catalog 对称），不读全文 instructions。"""
    catalog = []
    for f in _iter_skill_md(dirs):
        try:
            post = frontmatter.load(f)
            catalog.append({
                "name": post["name"],
                "title": post.get("title", post["name"]),
                "description": post.get("description", ""),
                "category": post.get("category", "agentic"),
                "triggers": post.get("triggers", []),
                "_path": str(f),
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("skip unparsable agentic skill %s: %s", f, e)
    return catalog


def load_agentic_skill(name: str, dirs: List[str]) -> tuple:
    """惰性：选中才读全文。返回 (AgenticSkillSpec, instructions_text)。"""
    for f in _iter_skill_md(dirs):
        post = frontmatter.load(f)
        if post.get("name") != name:
            continue
        spec = AgenticSkillSpec.parse_obj(post.metadata)
        return spec, post.content
    raise KeyError(f"agentic skill not found: {name}")
