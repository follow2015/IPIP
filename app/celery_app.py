# -*- coding: utf-8 -*-
"""Celery 应用工厂（AI 长任务异步底座，方案 §Phase 1）。

设计要点：
- **不引入新中间件**：broker 与 result backend 均复用既有 Redis（db 分离）。
- **app context**：所有 task 运行在 `ContextTask` 内，自动持有 Flask app context，
  task 内部可直接使用 db.session / ORM / AuditService。
- **分层隔离**：仅本模块与 `app/tasks/` 依赖 celery，API 与服务层不直接依赖。

worker 启动方式（supervisor，二选一，-Q 必须含 voice 否则语音 task 无人消费）：
    celery -A app.celery_app.celery worker -Q ai --loglevel=info --concurrency=2
    celery -A app.celery_app.celery worker -Q voice --loglevel=info --concurrency=4
    celery -A app.celery_app.celery worker -Q ai,voice --loglevel=info --concurrency=2


worker 的 `-A app.celery_app.celery` 只会 import 本模块，**不会执行
`create_app()`**。两条进程路径因此不同：

- Web 进程：`create_app()` → `init_celery(app)` → `_APP` 被显式赋值；
- Worker 进程：只 import 本模块 → `_APP` 保持 None，直到首个 task 执行时
  由 `_get_flask_app()` 惰性创建。

不能改成模块级 `from app import create_app; _APP = create_app()`：`app/__init__.py`
会 import 本模块，形成循环导入。函数内延迟 import 是避开该循环的标准做法。


task 靠 `@celery.task` 装饰器注册，**不 import 模块就不会注册**。worker 启动时
Celery 只加载 `-A` 指定的模块，故必须用 `conf.imports` 显式声明，否则报
`Received unregistered task`。
"""
from celery import Celery

from app.utils.logging import get_logger

logger = get_logger(__name__)

_ALL_TASK_MODULES = ("app.tasks.ai_tasks", "app.tasks.voice_tasks")

celery = Celery("ipip")

_APP = None

try:
    from config import Config

    celery.config_from_object(Config, namespace="CELERY")
except Exception as e:  # noqa: BLE001
    logger.warning("celery.config_load_failed %s", e)

import importlib.util

_TASK_MODULES = []
for _mod in _ALL_TASK_MODULES:
    if importlib.util.find_spec(_mod) is not None:
        _TASK_MODULES.append(_mod)
    else:
        logger.warning("celery task module %s not found, skipping (deploy without AI?)", _mod)

celery.conf.imports = tuple(celery.conf.imports or ()) + tuple(_TASK_MODULES)


def _get_flask_app():
    """获取 Flask app，首次调用时惰性创建并缓存。

    worker 进程不会主动执行 `create_app()`，故在此处兜底创建，保证 task 始终
    运行在 app context 内。Web 进程已由 `init_celery()` 赋值，直接复用。

    Returns:
        Flask 应用实例。
    """
    global _APP
    if _APP is None:
        from app import create_app  # 延迟导入：避免与 app/__init__.py 循环导入

        _APP = create_app()
    return _APP


class ContextTask(celery.Task):
    """自动持有 Flask app context 的 task 基类。

    没有它，task 内的 db.session / current_app 都会抛
    "Working outside of application context"。
    """

    def __call__(self, *args, **kwargs):
        with _get_flask_app().app_context():
            return self.run(*args, **kwargs)


celery.Task = ContextTask


def init_celery(app) -> Celery:
    """把 Flask app 绑定到 Celery 实例。

    在 `create_app()` 末尾调用。幂等：重复调用只会重新绑定。

    绑定 app 使 worker 路径与 web 路径共用同一个实例（避免 worker 重新创建
    一份 app 配置，导致两侧 Redis / 密钥配置漂移）。

    Args:
        app: Flask 应用实例。

    Returns:
        绑定完成的 Celery 实例（即模块级 `celery`）。
    """
    global _APP
    _APP = app

    celery.conf.update(
        broker_url=app.config.get("CELERY_BROKER_URL"),
        result_backend=app.config.get("CELERY_RESULT_BACKEND"),
    )
    celery.Task = ContextTask
    return celery
