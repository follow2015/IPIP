# -*- coding: utf-8 -*-
"""
请求上下文访问器（纯 flask.g，无任何业务依赖）。

从 `app/utils/auth.py` 析出（审计 P1-11）：`get_current_user_id` 读的是
`g.current_user`，与认证服务的内部实现无关，是正牌的**工具函数**。
析出它有两个好处：

  1. utils 层内部（`app/utils/logging/*` 等）用它时保持 utils -> utils，
     不必绕道 `app.utils.auth` 垫片 —— 那条边在 AST 上看不见，实为 utils -> services，
     属"自指陷阱"（见 `tests/test_architecture_layering.py` 的 R1c）。
  2. 认证服务与 utils 层共用同一个实现，不产生第二份定义。

`app.utils.auth` / `app.services.auth` 均 re-export 本函数，既有消费方无需改动。
"""
from typing import Optional

from flask import g

def get_current_user_id() -> Optional[int]:
    """获取当前请求的认证用户ID

    统一从 g.current_user 读取 user_id，避免各处直接访问
    g.user_id（从未被设置）或 g.current_user["user_id"]（分散重复）。

    Returns:
        int | None: 用户ID，未认证或信息缺失时返回 None
    """
    current_user = getattr(g, 'current_user', None)
    if isinstance(current_user, dict):
        return current_user.get('user_id')
    return None

