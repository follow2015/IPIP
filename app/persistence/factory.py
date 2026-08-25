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
    """登记一个仓储类的构造器（自动注册与特例 DAO 共用）。"""
    BaseRepository._REGISTRY[repo_cls] = ctor  # type: ignore[assignment]


class RepositoryFactory:
    """Repository 工厂。

    通过注册表将仓储类型映射到其构造器。``create()`` 接受仓储类与可选 session，
    返回对应实例。实例不缓存。
    """

    def create(self, repo_cls: Type[T], session: Optional[Session] = None) -> T:
        """创建指定类型的 Repository 实例。

        Args:
            repo_cls: 仓储类（或其接口类）。
            session: 数据库会话；缺省使用全局 ``db.session``。

        Returns:
            T: 仓储实例。

        Raises:
            KeyError: 未注册的仓储类型。
        """
        ctor = BaseRepository._REGISTRY.get(repo_cls)  # type: ignore[var-annotated]
        if ctor is None:
            raise KeyError(f"未注册的 Repository 类型: {repo_cls}")
        return ctor(session or db.session)  # type: ignore[return-value]



_default_factory: Optional[RepositoryFactory] = None


def get_repository_factory() -> RepositoryFactory:
    """获取 Repository 工厂实例（进程级单例）。"""
    global _default_factory
    if _default_factory is None:
        _default_factory = RepositoryFactory()
    return _default_factory


def create_repository(repo_cls: Type[T], session: Optional[Session] = None) -> T:
    """便捷函数：创建指定类型的 Repository 实例。"""
    return get_repository_factory().create(repo_cls, session)



def _discover_repositories() -> None:
    """扫描 app.persistence 下所有子模块，触发各 Repository 子类的自动注册。

    具体仓储在定义时通过 ``BaseRepository.__init_subclass__`` 自注册，
    因此只需 import 对应模块即可完成登记，无需在本文件逐行维护。
    """
    import app.persistence as _pkg
    for mod in pkgutil.iter_modules(_pkg.__path__):
        name = mod.name
        if name in ("base", "factory", "__init__"):
            continue
        importlib.import_module(f"app.persistence.{name}")


_discover_repositories()

from app.persistence.switch_ext_repository import SwitchExtRepository  # noqa: E402
from app.persistence.user_log_repository import UserLogRepository  # noqa: E402
_register(SwitchExtRepository, lambda s: SwitchExtRepository())
_register(UserLogRepository, lambda s: UserLogRepository())
