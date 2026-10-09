# -*- coding: utf-8 -*-
"""CSP 违规上报端点（OD-7 第一阶段）

浏览器发现页面违反 ``Content-Security-Policy-Report-Only`` 策略时，会向
``report-uri`` 指向的地址 POST 一份 JSON（``Content-Type: application/csp-report``，
新版为 ``application/reports+json``），形如::

    {"csp-report": {"document-uri": "...", "violated-directive": "...",
                    "blocked-uri": "...", "source-file": "...", ...}}

本端点只做**收集**（写日志），不解析入库——Report-Only 阶段的产出就是
"真实违规清单"，供第二阶段（切强制模式）确定允许源。日志即清单：
运维 `grep "CSP 违规上报" app.log | sort | uniq -c` 即可聚合。

设计取舍：
- **匿名可访问**：浏览器上报不带自定义头，且登录页本身也在 CSP 覆盖范围内
  （用户此刻必然未登录）；报告不含敏感数据（只有 URI 与指令名）。
- **不做存储**：第一步的目标是"清单稳定"，日志聚合足够；等清单证明某类违规
  需要长期跟踪时再考虑落库（那时也知道该存什么字段）。
- **防打爆哨兵而非配额**：全站 60 秒滑窗（进程内，多 worker 时阈值按 worker
  数天然放大）+ 单条 4KB 上限。超限静默丢弃并照常返回 204 —— 浏览器不关心
  响应体，返回非 2xx 只会让它重试，放大噪音。
- content-type 宽松处理：部分代理/浏览器会改写 content-type，只认"能解析出
  JSON"这一条，不校验媒体类型。
"""
import json
import threading
import time
from collections import deque

from flask import Blueprint, request

from app.openapi.doc import public
from app.utils.logging import get_logger

logger = get_logger(__name__)

security_bp = Blueprint("security", __name__)

_CSP_BODY_LIMIT = 4096
_CSP_WINDOW_SECONDS = 60
_CSP_MAX_PER_WINDOW = 120
_window: deque = deque()
_window_lock = threading.Lock()


def _consume_rate_slot() -> bool:
    """占一个滑窗名额；窗口已满返回 False（调用方静默丢弃）。"""
    now = time.monotonic()
    with _window_lock:
        while _window and now - _window[0] > _CSP_WINDOW_SECONDS:
            _window.popleft()
        if len(_window) >= _CSP_MAX_PER_WINDOW:
            return False
        _window.append(now)
        return True


@security_bp.route("/csp-report", methods=["POST"])
@public(summary="CSP 违规上报", tags=["安全"], responses={204: {"description": "只收不回（No Content）"}})
def csp_report():
    """接收浏览器 CSP Report-Only 违规报告并写入日志（204 No Content）。

    匿名端点：见模块 docstring「匿名可访问」。任何情况下都返回 204，
    解析失败 / 超限 / 超大 body 一律静默丢弃 —— 上报通道自身不应成为
    前端报错或攻击者探测差异的信源。
    """
    if not _consume_rate_slot():
        return "", 204
    body = request.get_data(cache=False)
    if len(body) > _CSP_BODY_LIMIT:
        return "", 204
    try:
        report = json.loads(body.decode("utf-8", errors="replace"))
        if not isinstance(report, dict):
            raise ValueError("csp-report 根节点不是对象")
    except (ValueError, UnicodeDecodeError):
        return "", 204
    entry = report.get("csp-report", report)  # reports+json 顶层无 "csp-report" 包裹
    logger.warning(
        "CSP 违规上报: document-uri=%s violated-directive=%s blocked-uri=%s source-file=%s",
        str(entry.get("document-uri", "?"))[:200],
        str(entry.get("violated-directive", "?"))[:100],
        str(entry.get("blocked-uri", "?"))[:200],
        str(entry.get("source-file", "?"))[:200],
    )
    return "", 204
