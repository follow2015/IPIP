# -*- coding: utf-8 -*-
"""管理员守卫：需要「仅管理员可访问」的路由统一调用。

背景（整改 T2.6）：`mail_settings_routes` / `voice_settings_routes` /
`webhook_config_routes` 三个路由模块各自定义了一份**逐字相同**的
`_require_admin()` —— 3 份定义、13 个调用点，收敛为此处单一实现。

为何是**守卫函数**而不是装饰器
------------------------------
13 个调用点均为「handler 首条语句 + 逐字相同的错误响应」
（`if not require_admin(): return APIResponse.error("权限不足", "FORBIDDEN", 403)`），
理论上可以写成 `@require_admin` 装饰器。未采用的理由：

- `mail_settings_routes.delete_mail_config` 带 `@transactional`。改成装饰器必须
  处理装饰器顺序（403 不应的确不该在事务内返回），而收益只有省下约 26 行；
- 现有形态零语义变更，符合本任务「保留原有错误响应文案与状态码」的约束。

按 KISS 保持「守卫函数 + 调用点自行返回响应」的形态。若将来要装饰器化，
请连同 `@transactional` 的顺序问题一起决策。
"""
from flask import g

from app.persistence.user_log_repository import UserLogRepository
from app.persistence.user_repository import UserRepository
from app.services.user_service import UserService
from app.utils.logging import get_logger

logger = get_logger(__name__)


def require_admin() -> bool:
    """当前登录用户是否为管理员。

    前置条件：调用方必须已挂 `@login_required`（由它写入 `g.current_user`）；
    本函数自身**不做**登录校验，也不返回响应对象。

    行为与原三份 `_require_admin()` 完全一致：
    - 用户不存在或非管理员 → False
    - 管理员 → True

    Returns:
        bool：True 表示是管理员。
    """
    user_service = UserService(UserRepository(), UserLogRepository())
    user = user_service.get_by_id(g.current_user["user_id"])
    if not user or not user.is_admin():
        return False
    return True
