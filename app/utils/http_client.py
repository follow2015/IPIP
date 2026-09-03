# -*- coding: utf-8 -*-
"""统一出站 HTTP 客户端（V4 收敛）。

此前 escalation_service / wechat_work / feishu / zabbix_adapter 各自维护
requests.Session 或裸 requests.post：裸调用每次新建连接（无 keep-alive），
Session 各自为政，超时与错误语义重复实现。本模块提供进程级共享连接池的
统一 POST 入口。

边界约定（KISS）：
- 不做重试：降级/重试语义属各业务域（升级 webhook best-effort、channels
  走 outbox 重试、zabbix 有批量缓存兜底），本模块不代管；
- 不统一超时数值：各域现有超时（zabbix 动态 monitor_timeout_seconds、
  channels API_TIMEOUT 常量）原样保留，仅收敛到同一参数入口；
- 连接层异常直接上抛，由调用方按各自语义处理。
"""
import requests

DEFAULT_TIMEOUT = 10  # 秒；调用方按域覆盖

_session = requests.Session()


def get_shared_session() -> requests.Session:
    """返回进程级共享 Session（连接池复用）。"""
    return _session


def post_json(url, payload, *, headers=None, timeout=DEFAULT_TIMEOUT,
              allow_redirects=False, verify=True) -> requests.Response:
    """统一 POST JSON（共享连接池）。

    Args:
        url: 目标 URL。
        payload: 将以 JSON 编码的请求体。
        headers: 额外请求头（如飞书签名所需的 Content-Type）。
        timeout: 超时秒数，各业务域覆盖。
        allow_redirects: 默认 False——webhook 类调用不跟随 3xx，
            避免把 POST 重定向为跨域 GET（原 wechat_work/feishu 行为）。
        verify: TLS 校验开关（zabbix 按凭据 verify_ssl 传入）。

    Returns:
        requests.Response（不自动 raise_for_status，语义由调用方决定）。
    """
    return _session.post(
        url, json=payload, headers=headers, timeout=timeout,
        allow_redirects=allow_redirects, verify=verify,
    )
