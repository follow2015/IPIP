# -*- coding: utf-8 -*-
"""
认证授权服务（原 app/utils/auth.py，审计 P1-11）。

模块职责：
  context         请求上下文访问器 + RBAC 缓存常量（叶子）
  authentication  AuthenticationManager —— JWT 签发/校验/刷新/撤销/登录
  permission      PermissionManager —— RBAC 角色与权限判定
  decorators      HTTP 层鉴权装饰器（login_required / permission_required / ...）

本文件是认证服务公共 API 的**唯一真源**；`app/utils/auth.py` 只是兼容垫片，
两者导出的是**同一批对象**（不是拷贝），以保证既有 170+ 处导入与测试补丁继续生效。
"""
from app.services.auth.authentication import (
    AuthenticationManager,
    auth_manager,
    cache_manager,
    config,
    logger,
    password_manager,
)
from app.services.auth.context import (
    RBAC_CACHE_TTL,
    _stable_hash,
    get_current_user_id,
    get_user_permissions,
)
from app.services.auth.decorators import (
    _sse_error_response,
    login_required,
    permission_required,
    role_required,
    sse_login_required,
    sse_permission_required,
)
from app.services.auth.permission import PermissionManager, permission_manager

__all__ = [
    "AuthenticationManager",
    "PermissionManager",
    "auth_manager",
    "permission_manager",
    "login_required",
    "permission_required",
    "role_required",
    "sse_login_required",
    "sse_permission_required",
    "get_current_user_id",
    "get_user_permissions",
    "RBAC_CACHE_TTL",
    "config",
    "cache_manager",
    "password_manager",
    "logger",
]
