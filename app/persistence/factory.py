# -*- coding: utf-8 -*-
"""Repository 工厂（注册表驱动，支持自动发现）。

设计目标：
- 自动注册：所有继承 ``BaseRepository`` 的具体仓储，在类定义时即通过
  ``BaseRepository.__init_subclass__`` 自注册到 ``BaseRepository._REGISTRY``。
  本工厂在导入时扫描 ``app.persistence`` 包下所有子模块，触发自注册。
  **新增仓储 = 在 ``app.persistence`` 下新建一个文件即完成登记，无需改动本工厂**，
  从根源上消除旧版「手动逐行注册、易遗漏导致 KeyError」的结构性缺陷。
- 会话注入、不缓存实例：每次 ``create`` 注入当前 ``session``（默认 ``db.session``），
  返回新实例，避免旧版「全局单例缓存 + set_session 清空」导致的
  session 跨实例不一致问题。Flask 的 ``db.session`` 是请求级 scoped session，
  每次创建成本极低，无需缓存。

注意（F3 收口前的技术债）：
- ``SwitchExtRepository`` 与 ``UserLogRepository`` 是**游离在统一抽象之外的手写 DAO**
  （不继承 ``BaseRepository``、内部直接引用全局 ``db.session``），无法被自动发现，
  仍在本文件末尾显式注册。其会话一致性问题待 F3 服务层改造时收口。
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Callable, Dict, Optional, Type, TypeVar

from sqlalchemy.orm import Session

from app.utils.logging import get_logger
from app.persistence.base import BaseRepository
from extensions import db

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseRepository)


def _register(repo_cls: Type[T], ctor: Callable[[Optional[Session]], T]) -> None:
    BaseRepository._REGISTRY[repo_cls] = ctor


class RepositoryFactory:

    def create(self, repo_cls: Type[T], session: Optional[Session] = None) -> T:
        ctor = BaseRepository._REGISTRY.get(repo_cls)
        if ctor is None:
            raise KeyError(f"未注册的 Repository 类型: {repo_cls}")
        return ctor(session or db.session)


_default_factory: Optional[RepositoryFactory] = None


def get_repository_factory() -> RepositoryFactory:
    global _default_factory
    if _default_factory is None:
        _default_factory = RepositoryFactory()
    return _default_factory


def create_repository(repo_cls: Type[T], session: Optional[Session] = None) -> T:
    return get_repository_factory().create(repo_cls, session)


def _discover_repositories() -> None:
    import app.persistence as _pkg
    for mod in pkgutil.iter_modules(_pkg.__path__):
        name = mod.name
        if name in ("base", "factory", "__init__"):
            continue
        importlib.import_module(f"app.persistence.{name}")


_discover_repositories()

from app.persistence.switch_ext_repository import SwitchExtRepository
from app.persistence.user_log_repository import UserLogRepository
_register(SwitchExtRepository, lambda s: SwitchExtRepository())
_register(UserLogRepository, lambda s: UserLogRepository())
