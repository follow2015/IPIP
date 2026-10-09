# -*- coding: utf-8 -*-
"""M13：SSE 连接上限的「单副本」前提守卫

`main._ConnectionCounter` 是进程内的一个整数：`MAX_CONNECTIONS=500` 这个上限
只在**单进程**前提下成立。uvicorn 一旦加 `--workers 4`，就有 4 个互不可见的
计数器，实际硬上限变成 500×4=2000，而且没有任何一处会报错 —— 超限拒绝静默失效，
连"为什么内存先扛不住"都无从查起。

这不是实现缺陷（评审原文：设计本身诚实，有注释、无欺骗），是**前提没有执行机制
守着**。本模块把前提显式化：启动时解析 worker 数，>1 就打 ERROR。

为何不直接换成 Redis 全局计数：那要每个进程在连接建立/断开时各写一次 Redis，
并在进程被 SIGKILL 时靠 TTL 兜底（≈M4 量级的真改动）。评审把它列在 P3 治理池，
本模块先把"现在是单副本、扩容前必须先改这里"钉死 —— 包括给运维一个明确的
解除开关，避免告警常亮后被人当噪音忽略。
"""
import logging
import os
import sys

logger = logging.getLogger(__name__)

ALLOW_MULTI_WORKER_ENV = "SSE_ALLOW_MULTI_WORKER"

_WORKER_ENV_KEYS = ("WEB_CONCURRENCY", "UVICORN_WORKERS")


def _to_int(raw) -> int | None:
    """宽松解析正整数；无法解析返回 None（非法配置按"未配置"处理）。"""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def detect_worker_count(argv=None, env=None) -> int:
    """解析本服务的 worker 数（无迹象时按 1 处理）。

    三种来源，按可信度从高到低：
      - `--workers N` / `--workers=N`：uvicorn CLI。多 worker 时子进程由
        multiprocessing 派生，Linux 下 fork 继承 argv，故子进程也看得到。
      - `WEB_CONCURRENCY`：gunicorn 系（含 uvicorn 的 UvicornWorker）。
      - `UVICORN_WORKERS`：部分部署脚本改用 env 传参。

    注意：这只是"尽力发现"。uvicorn 也可能以编程方式 `uvicorn.run(workers=…)`
    启动而不留 argv 痕迹 —— 那种场景靠 service 文件里的注释兜底。
    """
    argv = sys.argv if argv is None else argv
    env = os.environ if env is None else env

    for i, arg in enumerate(argv):
        if arg == "--workers" and i + 1 < len(argv):
            n = _to_int(argv[i + 1])
            if n:
                return n
        if arg.startswith("--workers="):
            n = _to_int(arg.split("=", 1)[1])
            if n:
                return n

    for key in _WORKER_ENV_KEYS:
        n = _to_int(env.get(key, ""))
        if n:
            return n

    return 1


def check_single_replica(argv=None, env=None) -> bool:
    """单副本前提自检：符合前提返回 True，多副本返回 False。

    刻意**不抛异常**：误判的代价是网关起不来（全站 SSE 断开），漏报的代价是
    上限慢慢失效 —— 两者不对称，故只告警不阻断。
    """
    env = os.environ if env is None else env
    workers = detect_worker_count(argv, env)
    if workers <= 1:
        return True

    if str(env.get(ALLOW_MULTI_WORKER_ENV, "")).strip().lower() in ("1", "true", "yes"):
        logger.warning(
            "已声明多副本运行（%s=1）：确认 SSE 连接计数已改为跨进程实现，"
            "否则 MAX_CONNECTIONS 只是每进程的上限",
            ALLOW_MULTI_WORKER_ENV,
        )
        return True

    from . import config  # 延迟导入：避免与 config 形成导入环

    logger.error(
        "SSE 连接上限 %d 只在单副本下成立，检测到 workers=%d ⇒ 实际硬上限变成 %d，"
        "超限拒绝静默失效。二选一：去掉 --workers；或把 _ConnectionCounter 换成"
        "跨进程计数（改完置 %s=1 关闭本告警）",
        config.MAX_CONNECTIONS, workers, config.MAX_CONNECTIONS * workers,
        ALLOW_MULTI_WORKER_ENV,
    )
    return False
