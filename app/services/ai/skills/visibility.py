# -*- coding: utf-8 -*-
"""L2 入口技能可见性（技能膨胀治理 Phase C）。

按用户权限裁剪入口可见技能集：技能所需权限不属于用户权限时，该技能不进 prompt 的
技能目录。动机：不应让用户看到自己无权执行的技能（如只读用户不应见建单类技能），
同时减少 LLM 在"选中了也会被拒"的技能上的误选，顺带缩小目录体积。

与既有 check_skill_permission 的关系（二者语义同源，都基于权限码）：
- check_skill_permission：执行前校验，fail-closed，越权必拒并提示缺哪个权限；
- 本模块：入口裁剪，fail-open，让越权技能根本不出现在目录里。
本模块只做减法，不做最终裁决：执行路径的权限校验仍是唯一权威，因此 LLM 若仍
幻觉出被裁掉的技能名，会被既有校验挡回明确的权限提示。

fail-open 边界（裁剪本身是可用性风险，宁可多露不可误藏）：
- 开关关闭 / user_permissions 为空（权限未知）→ 不裁剪；
- 单个技能解析失败 → 视为无权限要求，保留可见；
- 裁剪后可见集为空 → 整体回退不裁剪（避免把 /ask 变成什么都答不了）。
"""
import os
import threading
from types import SimpleNamespace
from typing import Dict, Iterable, Optional, Set, Tuple

from app.services.ai.skills.permission import collect_required_permissions
from app.utils.logging import get_logger

logger = get_logger(__name__)

_REQUIRED_CACHE: Dict[str, Tuple[float, Set[str]]] = {}
_REQUIRED_LOCK = threading.Lock()


def _parse_required(path: str) -> Set[str]:
    """读单个技能 YAML 推导所需权限；任何异常都退化为无权限要求（fail-open）。"""
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
        steps = meta.get("steps")
        view = SimpleNamespace(
            steps=[SimpleNamespace(type=s.get("type"), call=s.get("call"))
                   for s in steps] if steps is not None else None,
            allowed_capabilities=meta.get("allowed_capabilities") or [],
        )
        return collect_required_permissions(view)
    except Exception as e:  # noqa: BLE001
        logger.warning("skill.visibility.parse_failed path=%s: %s", path, e)
        return set()


def _required_of(entry: dict) -> Set[str]:
    """取单个技能的所需权限（带 mtime 缓存）；无 _path 或读不到时返回空集（保留可见）。"""
    path = entry.get("_path")
    if not path:
        return set()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return set()

    with _REQUIRED_LOCK:
        cached = _REQUIRED_CACHE.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    required = _parse_required(path)
    with _REQUIRED_LOCK:
        _REQUIRED_CACHE[path] = (mtime, required)
    return required


def get_allowed_skill_names(merged: Iterable[dict], user_permissions,
                            enabled: bool = False) -> Optional[Set[str]]:
    """按用户权限裁剪后的可见技能名集合。

    Args:
        merged: 合并后的技能 catalog（每项需含 name；Tier1 项含 _path 用于解析权限）。
        user_permissions: 用户权限码集合；空集视为权限未知，不裁剪。
        enabled: 总开关（Config.AI_SKILL_VISIBILITY_FILTER），关闭时不做任何裁剪。

    Returns:
        None 表示不裁剪（全部可见，等价于现网行为）；否则为可见技能名集合。
    """
    if not enabled or not user_permissions:
        return None

    perms = set(user_permissions)
    allowed: Set[str] = set()
    for entry in merged:
        name = entry.get("name")
        if not name:
            continue
        if not (_required_of(entry) - perms):
            allowed.add(name)

    if not allowed:
        logger.warning("skill.visibility.empty_result user_perms=%s，回退不裁剪",
                       sorted(perms))
        return None
    return allowed
