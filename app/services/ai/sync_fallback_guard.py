# -*- coding: utf-8 -*-
"""O5：AI 同步回退分支的启动告警

`AI_ASYNC_ENABLED=0` 时，agentic 诊断与 remedial 执行会退回到**请求线程内**跑多轮
LLM（=1 时走 Celery）。生产部署是 gunicorn sync worker + `--timeout 120`：一轮 LLM
超过 120s 不给心跳，master 就强杀该 worker，并连带杀死同一 worker 上的全部在途
请求。

当前不触发（默认 AI_ASYNC_ENABLED=1），分支留着是短期兜底。真正的风险不是这个
分支本身，而是有人把它当成"关掉异步能省一个 Celery"的性能开关随手关掉 —— 那时
的故障形态是"AI 偶发 500，且同一批请求一起失败"，几乎没人会联想到 worker 超时。
故在启动时就把代价说清楚。

本模块只做告警，不改行为：删分支是破坏性变更（可能还有人在用），且同步路径在
开发/排障时确实有用。
"""
import os
from typing import Optional, Tuple

GUNICORN_SYNC_MESSAGE = (
    "AI_ASYNC_ENABLED=0 且运行在 gunicorn sync worker 下：AI 长任务（agentic 诊断 / "
    "remedial）会在请求线程内跑多轮 LLM，超过 gunicorn --timeout（默认 120s）会被 "
    "master 强杀，并连带杀死同一 worker 上的全部在途请求。请恢复 AI_ASYNC_ENABLED=1，"
    "或改用 gevent 等异步 worker 后再关。"
)

GENERIC_MESSAGE = (
    "AI_ASYNC_ENABLED=0：AI 长任务在请求线程内同步执行（不经 Celery），长任务会占住 "
    "worker 直到结束。生产请保持 AI_ASYNC_ENABLED=1。"
)


def _is_gunicorn_sync(server_software: Optional[str],
                      worker_class: Optional[str]) -> bool:
    """是否运行在 gunicorn sync worker 下。

    gunicorn 会设 SERVER_SOFTWARE=gunicorn/<ver>；worker 类型默认 sync，
    环境变量 GUNICORN_WORKER_CLASS 只在部署方显式设置时才存在。
    """
    server = (server_software or "").lower()
    if "gunicorn" not in server:
        return False
    wc = (worker_class or "").strip().lower()
    return not wc or wc == "sync" or wc.endswith("sync")


def sync_fallback_risk(
    async_enabled: bool,
    server_software: Optional[str] = None,
    worker_class: Optional[str] = None,
) -> Optional[Tuple[str, str]]:
    """评估同步回退分支的风险，返回 (日志级别, 文案)；无风险返回 None。

    Args:
        async_enabled: `AI_ASYNC_ENABLED` 的布尔值。
        server_software / worker_class: 缺省读环境变量（SERVER_SOFTWARE /
            GUNICORN_WORKER_CLASS），单测可直接注入。
    """
    if async_enabled:
        return None

    env = os.environ
    server = server_software if server_software is not None else env.get("SERVER_SOFTWARE", "")
    wc = worker_class if worker_class is not None else env.get("GUNICORN_WORKER_CLASS", "")

    if _is_gunicorn_sync(server, wc):
        return ("error", GUNICORN_SYNC_MESSAGE)
    return ("warning", GENERIC_MESSAGE)


def report_at_startup(app) -> Optional[str]:
    """启动自检入口（由 create_app 调用）。

    单独成一个函数而不是在 create_app 里内联：内联的启动自检只能靠"真的建一个
    Flask app"来测，而测试里多建一个 app 会重新 init db 单例，把后续用例的
    `Model.query` 打到错误引擎上（voice_tasks 曾因此在全量里整片红）。
    """
    from app.utils.logging import get_logger

    return warn_if_risky(
        get_logger(__name__), app.config.get("AI_ASYNC_ENABLED", True)
    )


def warn_if_risky(logger, async_enabled: bool, **kwargs) -> Optional[str]:
    """有风险就告警，返回实际使用的日志级别（无风险返回 None）。"""
    risk = sync_fallback_risk(async_enabled, **kwargs)
    if not risk:
        return None
    level, message = risk
    if level == "error":
        logger.error(message)
    else:
        logger.warning(message)
    return level
