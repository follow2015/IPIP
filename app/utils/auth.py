# -*- coding: utf-8 -*-
"""
兼容垫片（deprecated）：认证授权服务已迁至 `app.services.auth`（审计 P1-11）。

本文件**不含任何逻辑**，只把 `app.services.auth` 的公共对象 re-export 到旧路径，
使既有 170+ 处导入（130+ 文件）与全部测试补丁无需改动即可继续工作。

为什么保留而不是直接改全仓导入：
  - 迁移的风险面全在"漏符号 / 新旧路径各持一份对象"上，垫片让新路径成为唯一定义，
    旧路径只是门面，不存在两份对象；
  - 新旧路径的同一性由 `tests/test_auth_import_surface.py` 钉住（含 monkeypatch 接缝）。

移除条件：全仓消费方改指 `app.services.auth` 后，连同
`tests/test_architecture_layering.py` 的 MODULE_LEVEL_ALLOWLIST 条目一并删除。
"""
from app.services.auth import (  # noqa: F401  (公共 API 再导出)
    RBAC_CACHE_TTL,
    AuthenticationManager,
    PermissionManager,
    _stable_hash,
    _sse_error_response,
    auth_manager,
    cache_manager,
    config,
    get_current_user_id,
    get_user_permissions,
    logger,
    login_required,
    password_manager,
    permission_manager,
    permission_required,
    role_required,
    sse_login_required,
    sse_permission_required,
)
