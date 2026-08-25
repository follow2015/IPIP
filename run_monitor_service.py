# -*- coding: utf-8 -*-
"""监控独立微服务入口（Route A：独立 async 进程）

把设备健康监控从 Flask 进程内守护线程抽离为独立进程，由 asyncio 事件循环驱动探测轮次，
复用主 MySQL 的 Flask ORM 与 notification_service（告警经 Redis → realtime_gateway → SSE）。

用法：
    python run_monitor_service.py [environment]
    # environment 缺省读 FLASK_ENV，再缺省 production

说明：
- 本入口会设置 MONITOR_WORKER_IN_PROCESS=false 再 create_app，确保 HTTP 应用
  进程（若另行部署）可保持默认 in-Flask worker，而本独立服务进程不双跑；
  同时本服务通过 Redis 锁 monitor:lock:<loop> 与任何仍运行的 in-Flask worker 互斥。
- 生产部署建议：在 Flask HTTP 应用进程设置 MONITOR_WORKER_IN_PROCESS=false，
  仅由本独立服务承担监控，避免冗余探测。
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.monitoring.standalone_service import (
    StandaloneMonitorService,
    create_headless_monitor_app,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


def main() -> None:
    config_name = sys.argv[1] if len(sys.argv) > 1 else os.getenv("FLASK_ENV", "production")
    logger.info("启动监控独立服务（environment=%s）", config_name)
    app = create_headless_monitor_app(config_name)
    service = StandaloneMonitorService(app)
    service.run()


if __name__ == "__main__":
    main()
