# -*- coding: utf-8 -*-
"""能力注册表：技能模块只能调用这里登记的既有能力，杜绝任何代码执行。

写操作类能力注册时声明 requires_permission，技能执行前由 skills/permission.py
聚合校验，不在路由层单独判断。
"""
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CapabilityEntry:
    fn: Callable
    requires_permission: Optional[str] = None


_REGISTRY: Dict[str, CapabilityEntry] = {}


def register_capability(name: str, requires_permission: Optional[str] = None):
    """装饰器：登记一个能力，可选声明所需权限码。

    Args:
        name: 能力名，技能 YAML 中 step.call 引用此名。
        requires_permission: 写操作类能力需声明（如 "ai:execute"），只读能力留 None。
    """
    def deco(fn: Callable) -> Callable:
        if name in _REGISTRY:
            logger.warning("capability overridden: %s", name)
        _REGISTRY[name] = CapabilityEntry(fn=fn, requires_permission=requires_permission)
        return fn
    return deco


def get_capability(name: str) -> Optional[Callable]:
    """返回能力函数本身；未注册返回 None。"""
    entry = _REGISTRY.get(name)
    return entry.fn if entry else None


def get_required_permission(name: str) -> Optional[str]:
    """返回能力声明的所需权限码；未注册或无权限声明返回 None。"""
    entry = _REGISTRY.get(name)
    return entry.requires_permission if entry else None


def is_registered(name: str) -> bool:
    """能力是否已注册。"""
    return name in _REGISTRY
