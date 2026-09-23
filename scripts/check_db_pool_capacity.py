#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验「进程数 × 连接池容量」是否逼近 MySQL ``max_connections``（只读）。

用途（A-P1-6；随安装/上线自检）::

    make check-db-pool                            # 推荐（Makefile 已指向项目 venv）
    .venv/bin/python scripts/check_db_pool_capacity.py            # 按默认进程数算
    .venv/bin/python scripts/check_db_pool_capacity.py --workers 8 --celery-concurrency 8

    ⚠️ 必须用**项目 venv** 的解释器（需要项目依赖）；用系统 python3 会得到退出码 2
    而不是容量结论。


`config.py` 的连接池是 ``pool_size=10, max_overflow=20`` ⇒ **每个进程**最多
30 条连接。而本项目是**多进程**（gunicorn workers + celery worker + 独立监控进程），
于是实际峰值是 ``Σ 进程 × 30``：4 个 gunicorn worker 就已 120 条，再叠加 celery
与监控进程即逼近 MySQL 默认 ``max_connections=151``。

超限的表现**不是**清晰的报错，而是偶发的 "Too many connections" —— 出现时机取决于
当时有多少 worker 正好在压满溢出连接，排查方向极易被引向"某个接口慢"。故把它做成
**可在安装/上线时跑一次的确定性检查**。


* ``required > max_connections`` ⇒ **FAIL**（退出码 1）：上线前必须调小 worker 数或
  调大 ``max_connections``；
* ``required > 80% max_connections`` ⇒ **WARN**（退出码 0）：留不出故障余量；
* 否则 **OK**。

另报出当前 ``Threads_connected`` 作为参照（只读 ``SHOW STATUS``）。全程只读，
不写库、不改仓库文件。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def _pin_environment() -> None:
    """在**导入 app/config 之前**置位（两者都是**类定义期**读 env，晚了不生效）。

    * ``MONITOR_WORKER_IN_PROCESS=false`` —— 理由与 ``tests/conftest.py`` 同款：
      **跑一次容量自检不等于要跑监控**。真起了 4 个轮询线程 + outbox + 看门狗，
      进程退出时它们会在解释器关闭后继续提交任务（实测
      "cannot schedule new futures after interpreter shutdown"），而本脚本只是读两个数。
    * ``LOG_LEVEL=WARNING`` —— 自检只该输出结论，不该把应用启动日志刷一屏。

    ⚠️ 刻意放在**函数内**而不是模块顶层：本模块会被判据文件 import
    （`tests/test_db_pool_capacity.py`），顶层置 env 会污染整个测试会话。
    """
    os.environ.setdefault("MONITOR_WORKER_IN_PROCESS", "false")
    os.environ.setdefault("LOG_LEVEL", "WARNING")

WARN_RATIO = 0.8


def required_connections(processes: int, pool_size: int, max_overflow: int) -> int:
    """峰值连接需求 = 进程数 × (pool_size + max_overflow)。

    抽成纯函数便于单测：进程数是唯一的环境变量，池参数来自 ``config.py``。
    """
    if processes < 0:
        raise ValueError("processes 不得为负")
    return processes * (pool_size + max_overflow)


def judge(required: int, max_connections: int, warn_ratio: float = WARN_RATIO) -> str:
    """返回 ``"FAIL"`` / ``"WARN"`` / ``"OK"``。纯函数，便于穷举边界。"""
    if required > max_connections:
        return "FAIL"
    if required > max_connections * warn_ratio:
        return "WARN"
    return "OK"


def _pool_numbers() -> tuple[int, int]:
    """从 ``config.py`` 读池参数（**单一真源**：别在脚本里再写一份 10/20）。"""
    from config import Config

    opts = Config.SQLALCHEMY_ENGINE_OPTIONS
    return int(opts["pool_size"]), int(opts["max_overflow"])


def _processes(args) -> list[tuple[str, int]]:
    """参与连接池的进程清单（名字, 数量）。

    默认值**照抄部署实况**（`deploy/systemd/ipip.env.example` 的三个变量 + 两个
    单进程服务）：web 4 / celery-ai 2 / celery-voice 4 / monitor 1。
    每一项都可用命令行覆盖 —— 自检的价值在"把乘法摊开给人看"，
    而不是替运维猜他们的 GUNICORN_WORKERS。
    """
    def _pick(flag_value, env_name, fallback):
        if flag_value:
            return flag_value
        return int(os.getenv(env_name, str(fallback)))

    return [
        ("web(gunicorn)", _pick(args.workers, "GUNICORN_WORKERS", 4)),
        ("celery-ai", _pick(args.celery_ai, "CELERY_AI_CONCURRENCY", 2)),
        ("celery-voice", _pick(args.celery_voice, "CELERY_VOICE_CONCURRENCY", 4)),
        ("monitor", args.monitor_processes),
        ("其他(trapd/gateway 等占池进程)", args.other_processes),
    ]


def _db_limits() -> tuple[int | None, int | None]:
    """只读 ``max_connections`` 与 ``Threads_connected``；连不上库返回 (None, None)。"""
    try:
        from extensions import db
        from sqlalchemy import text
    except Exception as exc:  # noqa: BLE001
        print(f"[db-pool] 无法导入项目模块（要用项目 venv 跑）：{exc}")
        return None, None
    try:
        max_conn = db.session.execute(text("SELECT @@max_connections")).scalar()
        threads = db.session.execute(text("SHOW STATUS LIKE 'Threads_connected'")).fetchone()
        return int(max_conn), int(threads[1]) if threads else None
    except Exception as exc:  # noqa: BLE001 - 连不上库时不阻断：仍能报出"需求值"
        print(f"[db-pool] 连库失败（跳过实测对比，仅报需求值）：{exc}")
        return None, None


def main() -> int:
    _pin_environment()
    parser = argparse.ArgumentParser(description="连接池容量校验（只读）")
    parser.add_argument("--workers", type=int, default=0,
                        help="gunicorn worker 数（默认取 GUNICORN_WORKERS，缺省 4）")
    parser.add_argument("--celery-ai", type=int, default=0,
                        help="celery-ai 并发数（默认取 CELERY_AI_CONCURRENCY，缺省 2）")
    parser.add_argument("--celery-voice", type=int, default=0,
                        help="celery-voice 并发数（默认取 CELERY_VOICE_CONCURRENCY，缺省 4）")
    parser.add_argument("--monitor-processes", type=int, default=1,
                        help="独立监控进程数（run_monitor_service.py；缺省 1）")
    parser.add_argument("--other-processes", type=int, default=0,
                        help="其他会占池的进程数（trapd / realtime gateway 等；缺省 0）")
    args = parser.parse_args()

    from app import create_app  # noqa: F401 - 触发应用上下文（提供 db.session）

    pool_size, max_overflow = _pool_numbers()
    breakdown = _processes(args)
    processes = sum(n for _, n in breakdown)
    required = required_connections(processes, pool_size, max_overflow)

    app = create_app()
    with app.app_context():
        max_conn, threads_now = _db_limits()

    print("[db-pool] 池参数 pool_size=%d max_overflow=%d ⇒ 每进程最多 %d 条"
          % (pool_size, max_overflow, pool_size + max_overflow))
    for name, n in breakdown:
        if n:
            print("           %-34s %2d 进程 → %3d 条"
                  % (name, n, n * (pool_size + max_overflow)))
    print("[db-pool] 进程数合计 = %d；**峰值**需求 = %d 条连接"
          "（max_overflow 是按需创建 ⇒ 这是上界而非稳态占用）"
          % (processes, required))

    if max_conn is None:
        print("[db-pool] 未能读取 MySQL max_connections —— 请在有库凭据的环境复跑")
        return 0

    verdict = judge(required, max_conn)
    print("[db-pool] MySQL max_connections = %d，当前 Threads_connected = %s"
          % (max_conn, threads_now))
    print("[db-pool] 结论：%s" % verdict)
    if verdict == "FAIL":
        print(
            "[db-pool] 修复（二选一）：\n"
            "  · 调小 GUNICORN_WORKERS / CELERY_AI_CONCURRENCY / CELERY_VOICE_CONCURRENCY；\n"
            "  · 或调大 MySQL max_connections（并同步 innodb_open_files 等）。\n"
            "  注意 pool_size/max_overflow 是 config.py 的常量，改它属全局影响。"
        )
        return 1
    if verdict == "WARN":
        print("[db-pool] 余量不足 20%%：连接还被备份/运维/监控占用，建议下调进程数"
              "或抬高 max_connections。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
