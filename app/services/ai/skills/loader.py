# -*- coding: utf-8 -*-
"""扫描技能目录：启动仅解析元数据进目录；全文惰性加载。"""
import threading
from pathlib import Path
from typing import List

import yaml

from app.services.ai.skills.schema import SkillSpec
from app.utils.logging import get_logger

logger = get_logger(__name__)


_CATALOG_CACHE: dict = {}
_CATALOG_LOCK = threading.Lock()


def _dirs_key(dirs: List[str]) -> str:
    """将目录列表转为缓存 key（排序去重，保证顺序无关）。"""
    return "|".join(sorted(set(dirs)))


def default_skill_dirs() -> List[str]:
    """Tier 1 技能目录（builtin + custom），返回绝对路径。"""
    from config import Config
    return [Config.AI_BUILTIN_SKILLS_DIR, Config.AI_CUSTOM_SKILLS_DIR]


def default_agentic_dirs() -> List[str]:
    """Tier 2 agentic 技能目录，返回绝对路径。"""
    from config import Config
    return [Config.AI_AGENTIC_SKILLS_DIR]


def _iter_yaml(dirs: List[str]):
    for d in dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        for f in sorted(p.glob("*.yaml")) + sorted(p.glob("*.yml")):
            yield f


def _custom_disabled(name: str, path: Path) -> bool:
    """P0-1：检查技能是否被禁用（对齐 skill_admin_service._is_disabled 语义）。

    仅 custom 目录技能可被 <name>.disabled 标记禁用；builtin 技能不可禁用，
    故 custom 同名禁用不误杀 builtin 同名技能。

    Args:
        name: 技能名（YAML 的 name 字段）。
        path: 技能 YAML 文件路径（用于判断是否位于 custom 目录）。

    Returns:
        True 表示该技能文件属 custom 且存在禁用标记，应从目录/加载中剔除。
    """
    try:
        from config import Config
        custom = Path(Config.AI_CUSTOM_SKILLS_DIR).resolve()
        if path.resolve().parent != custom:
            return False
        return (custom / f"{name}.disabled").exists()
    except Exception as e:  # noqa: BLE001
        logger.warning("skill.disabled_check_failed name=%s: %s", name, e)
        return False


def load_catalog(dirs: List[str]) -> List[dict]:
    """仅元数据：给 LLM 的菜单，成本低、可全量常驻内存。

    M4 修复：基于文件 mtime 缓存，仅当任一 YAML 文件 mtime 变化时才重新读盘解析。
    P0-1：custom 目录下带 .disabled 标记的技能不进菜单（禁用即不可见）。
    """
    key = _dirs_key(dirs)
    with _CATALOG_LOCK:
        cached = _CATALOG_CACHE.get(key)

    files = list(_iter_yaml(dirs))
    current_mtimes = {}
    for f in files:
        try:
            current_mtimes[str(f)] = f.stat().st_mtime
        except OSError:
            continue

    with _CATALOG_LOCK:
        cached = _CATALOG_CACHE.get(key)
        if cached is not None and cached.get("mtime") == current_mtimes:
            return cached["catalog"]

    catalog = []
    for f in files:
        try:
            meta = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            name = meta.get("name")
            if name and _custom_disabled(name, f):
                continue
            catalog.append({
                "name": name,
                "title": meta.get("title") or meta.get("name"),
                "description": meta.get("description", ""),
                "category": meta.get("category", "general"),
                "params": meta.get("params", []),
                "triggers": meta.get("triggers", []),
                "_path": str(f),
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("skip unparsable skill %s: %s", f, e)

    with _CATALOG_LOCK:
        _CATALOG_CACHE[key] = {"mtime": current_mtimes, "catalog": catalog}
    return catalog


def invalidate_catalog_cache(dirs: List[str] | None = None) -> None:
    """清空 catalog 缓存（热加载时调用）。

    Args:
        dirs: 指定目录列表则只清该 key，None 则清空所有缓存。
    """
    with _CATALOG_LOCK:
        if dirs is None:
            _CATALOG_CACHE.clear()
        else:
            _CATALOG_CACHE.pop(_dirs_key(dirs), None)


def load_skill(name: str, dirs: List[str]) -> SkillSpec:
    """惰性：AI 选中才读盘 + 全量 schema 校验。

    P0-1：custom 目录下带 .disabled 标记的技能拒绝加载（禁用对执行路径生效）。
    跳过被禁文件而非整体 raise——builtin 目录可能有同名技能仍可用。
    """
    for f in _iter_yaml(dirs):
        meta = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if meta.get("name") != name:
            continue
        if _custom_disabled(name, f):
            continue
        return SkillSpec.parse_obj(meta)
    raise KeyError(f"skill not found: {name}")
