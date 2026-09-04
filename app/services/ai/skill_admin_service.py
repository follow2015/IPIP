# -*- coding: utf-8 -*-
"""技能管理服务：列表/详情/启用禁用/热加载。

启用禁用持久化：在自定义技能目录下写 `<name>.disabled` 标记文件。
- builtin 技能只读，不可禁用（source=builtin）。
- custom 技能可启用禁用（source=custom），禁用后 load_catalog 跳过。
"""
from pathlib import Path
from typing import Any, Dict, List

import os
import re
import yaml
from flask import current_app

from app.services.ai.skills.loader import _iter_yaml, invalidate_catalog_cache
from app.services.ai.skills.schema import SkillSpec, SkillValidationError
from app.utils.logging import get_logger

logger = get_logger(__name__)

_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _validate_skill_name(name: str) -> str:
    """校验技能 name 安全性（C3 修复：防止路径遍历）。

    Args:
        name: 技能标识

    Returns:
        校验通过的 name

    Raises:
        ValueError: name 包含非法字符或格式
    """
    if not isinstance(name, str) or not _SKILL_NAME_PATTERN.match(name):
        raise ValueError(f"非法技能标识：{name!r}（仅允许小写字母/数字/下划线/连字符，1-64 字符）")
    return name


def _builtin_dir() -> str:
    from config import Config
    return Config.AI_BUILTIN_SKILLS_DIR


def _custom_dir() -> str:
    from config import Config
    return Config.AI_CUSTOM_SKILLS_DIR


def _skill_dirs() -> List[str]:
    return [_builtin_dir(), _custom_dir()]


def _is_disabled(name: str) -> bool:
    """检查自定义技能目录下是否存在 <name>.disabled 标记。"""
    _validate_skill_name(name)
    return (Path(_custom_dir()) / f"{name}.disabled").exists()


def _set_disabled(name: str, disabled: bool) -> None:
    _validate_skill_name(name)
    marker = Path(_custom_dir()) / f"{name}.disabled"
    if disabled:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    else:
        marker.unlink(missing_ok=True)


def _source_of(path: Path) -> str:
    """判断技能来源：builtin / custom。"""
    try:
        if path.resolve().is_relative_to(Path(_builtin_dir()).resolve()):
            return "builtin"
    except ValueError:
        pass
    return "custom"


def list_skills() -> List[Dict[str, Any]]:
    """列出所有技能元数据 + 启用状态 + 来源。"""
    skills = []
    for f in _iter_yaml(_skill_dirs()):
        try:
            meta = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            name = meta.get("name")
            if not name:
                continue
            source = _source_of(f)
            disabled = _is_disabled(name) if source == "custom" else False
            skills.append({
                "name": name,
                "title": meta.get("title") or name,
                "description": meta.get("description", ""),
                "category": meta.get("category", "general"),
                "version": meta.get("version", 1),
                "params": meta.get("params", []),
                "triggers": meta.get("triggers", []),
                "source": source,
                "enabled": not disabled,
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("skip unparsable skill %s: %s", f, e)
    return skills


def get_skill(name: str) -> Dict[str, Any]:
    """获取单个技能完整 YAML 内容 + 启用状态 + 来源。"""
    _validate_skill_name(name)
    for f in _iter_yaml(_skill_dirs()):
        meta = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if meta.get("name") != name:
            continue
        source = _source_of(f)
        disabled = _is_disabled(name) if source == "custom" else False
        meta["source"] = source
        meta["enabled"] = not disabled
        meta["_path"] = str(f)
        return meta
    raise KeyError(f"skill not found: {name}")


def set_skill_enabled(name: str, enabled: bool) -> None:
    """启用/禁用技能。builtin 技能不可禁用。"""
    _validate_skill_name(name)
    found = False
    for f in _iter_yaml(_skill_dirs()):
        meta = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if meta.get("name") != name:
            continue
        source = _source_of(f)
        if source != "custom":
            raise ValueError(f"builtin 技能不可禁用: {name}")
        found = True
        break
    if not found:
        raise KeyError(f"skill not found: {name}")
    _set_disabled(name, not enabled)


def reload_catalog() -> int:
    """热加载：重新扫描技能目录，返回技能数。

    M4 修复：清空 catalog mtime 缓存，强制下次 list_skills/load_catalog 重读磁盘。
    """
    invalidate_catalog_cache()
    return len(list_skills())


class BuiltinSkillProtected(Exception):
    """builtin 技能不可修改/删除。路由层据此返回 403（不靠字符串匹配）。"""


def _atomic_write_yaml(target: Path, payload: dict) -> None:
    """M1 修复：原子写 YAML。写临时文件 → os.replace 原子替换，避免半写被 loader 读到。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".yaml.tmp")
    tmp.write_text(
        yaml.safe_dump(
            payload,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=1000,
        ),
        encoding="utf-8",
    )
    os.replace(tmp, target)  # 原子替换（同 filesystem 内）


def _is_builtin_name(name: str) -> bool:
    """判断 name 是否与某 builtin 技能重名（遍历 builtin 目录比对 name 字段）。"""
    for f in _iter_yaml([_builtin_dir()]):
        meta = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if meta.get("name") == name:
            return True
    return False


def create_skill(content: dict) -> str:
    """创建自定义技能。校验 schema → 写 custom/<name>.yaml → 清缓存。

    Args:
        content: 技能完整定义（JSON dict）

    Returns:
        技能 name

    Raises:
        ValueError: name 非法 / 与 builtin 重名
        SkillValidationError: schema 校验失败
        FileExistsError: 技能已存在
    """
    name = content.get("name")
    if not isinstance(name, str):
        raise ValueError("name 必须为字符串")
    _validate_skill_name(name)
    spec = SkillSpec.model_validate(content)  # schema 校验，失败抛 ValidationError

    if _is_builtin_name(name):
        raise ValueError(f"与 builtin 技能重名：{name}")

    target = Path(_custom_dir()) / f"{name}.yaml"
    if target.exists():
        raise FileExistsError(f"技能已存在：{name}（用 PUT /skills/{name}/content 编辑）")

    payload = spec.model_dump(by_alias=True, exclude_none=True)
    _atomic_write_yaml(target, payload)
    invalidate_catalog_cache()
    logger.info("created skill: %s -> %s", name, target)
    return name


def update_skill_content(name: str, content: dict) -> None:
    """编辑自定义技能内容。builtin 不可改。

    Args:
        name: 技能标识
        content: 新的完整定义

    Raises:
        ValueError: name 非法 / body.name 与 url.name 不一致
        BuiltinSkillProtected: builtin 技能不可编辑
        SkillValidationError: schema 校验失败
        KeyError: 技能不存在
    """
    _validate_skill_name(name)
    custom_target = Path(_custom_dir()) / f"{name}.yaml"
    if not custom_target.exists():
        if _is_builtin_name(name):
            raise BuiltinSkillProtected(f"builtin 技能不可编辑: {name}")
        raise KeyError(f"skill not found: {name}")

    spec = SkillSpec.model_validate(content)
    if spec.name != name:
        raise ValueError("body.name 与 url.name 不一致")

    payload = spec.model_dump(by_alias=True, exclude_none=True)
    _atomic_write_yaml(custom_target, payload)
    invalidate_catalog_cache()
    logger.info("updated skill: %s", name)


def delete_skill(name: str) -> None:
    """删除自定义技能 + 清 .disabled 标记。builtin 不可删。

    Raises:
        ValueError: name 非法
        BuiltinSkillProtected: builtin 技能不可删除
        KeyError: 技能不存在
    """
    _validate_skill_name(name)
    target = Path(_custom_dir()) / f"{name}.yaml"
    if not target.exists():
        if _is_builtin_name(name):
            raise BuiltinSkillProtected(f"builtin 技能不可删除: {name}")
        raise KeyError(f"skill not found: {name}")

    target.unlink()
    (Path(_custom_dir()) / f"{name}.disabled").unlink(missing_ok=True)
    invalidate_catalog_cache()
    logger.info("deleted skill: %s", name)
