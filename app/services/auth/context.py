# -*- coding: utf-8 -*-
"""
认证上下文与 RBAC 权限聚合（原 app/utils/auth.py 的 context 部分，审计 P1-11 迁移）。

纯请求上下文/权限读取，不承载令牌签发逻辑，属本包最底层（叶子模块），
故 `permission` / `decorators` 都可以依赖它，而不产生循环。

`get_current_user_id` 的**实现**在 `app.utils.request_context`（纯 flask.g 访问器，
无任何业务依赖，utils 层内部也要用它）；此处 re-export，使认证服务的公共 API 保持完整。
"""
import hashlib
from typing import Optional

from flask import g

from app.utils.request_context import get_current_user_id  # noqa: F401  (re-export)

RBAC_CACHE_TTL = 300  # RBAC 权限缓存有效期（秒），原 1800(30min) 过长，权限变更最长 5min 生效


def _stable_hash(obj) -> str:
    """生成跨进程稳定的哈希键（内置 hash() 受 PYTHONHASHSEED 影响不稳定）"""
    return hashlib.sha256(repr(obj).encode("utf-8")).hexdigest()


def get_user_permissions(user_id: int) -> set:
    """获取用户通过角色继承的所有权限码集合。

    供技能引擎权限聚合校验使用，与 permission_required 装饰器复用同一份查询逻辑。

    Args:
        user_id: 用户 ID

    Returns:
        set[str]: 权限码集合；用户不存在返回空集。
    """
    from app.models.user import User
    try:
        user = User.query.get(user_id)
    except Exception:  # noqa: BLE001
        return set()
    if not user:
        return set()
    perms = set()
    for role in getattr(user, "roles", []) or []:
        for permission in getattr(role, "permissions", []) or []:
            code = getattr(permission, "code", None)
            if code:
                perms.add(code)
    return perms

