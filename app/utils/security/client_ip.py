# -*- coding: utf-8 -*-
"""客户端真实 IP 提取（n7 口径：不盲信 X-Forwarded-For）。

与 `app/__init__.py` 的 /metrics 端点、`app/api/voice_callback_routes.py` 算法同源：
仅当直连对端（remote_addr）落在 `TRUSTED_PROXIES` 内，才采信 XFF 最右段；
否则一律以 remote_addr 为准 —— XFF 最左段由请求方自行携带，可任意伪造。

注意配置键各自独立：本模块读 `TRUSTED_PROXIES`（全局），语音回调那处读
`VOICE_TRUSTED_PROXIES`（仅回调链路），二者只是算法一致，不共享同一份配置。

引入原因：登录链路写 `users_log.login_ip` 曾有三处各自为政的口径（一处裸
`request.remote_addr`，两处取 XFF 最左段），使安全中心的"异地登录检测"失真。
"""
import ipaddress

from flask import current_app, has_request_context, request

from app.utils.logging import get_logger

logger = get_logger(__name__)


def trusted_proxy_nets() -> list:
    """解析 TRUSTED_PROXIES 为 ip_network 列表（与 /metrics、https_guard 同一口径）。

    Returns:
        ip_network 列表；非法条目被忽略并告警，不抛异常。
    """
    nets = []
    for raw in (current_app.config.get("TRUSTED_PROXIES") or []):
        try:
            nets.append(ipaddress.ip_network(str(raw), strict=False))
        except ValueError:
            logger.warning("TRUSTED_PROXIES 含非法条目，已忽略: %s", raw)
    return nets


def get_client_ip(req=None) -> str:
    """取真实客户端 IP。

    Args:
        req: 可选请求对象；缺省使用当前请求上下文。

    Returns:
        客户端 IP；无请求上下文时返回空串（调用方不应在无上下文时写登录日志）。
    """
    if req is None:
        if not has_request_context():
            return ""
        req = request

    peer = req.remote_addr or ""
    try:
        peer_ip = ipaddress.ip_address(peer)
        trusted = any(peer_ip in net for net in trusted_proxy_nets())
    except ValueError:
        trusted = False

    xff = req.headers.get("X-Forwarded-For", "")
    if trusted and xff:
        return xff.split(",")[-1].strip()
    return peer
