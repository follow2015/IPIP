# -*- coding: utf-8 -*-
"""HTTPS 强制访问守卫

背景：登录密码为明文 JSON 传输（业界标准做法，安全性押在 HTTPS 上），
但应用层此前无任何 HTTPS 强制（无 Talisman/HSTS/SSL_REDIRECT），且
deploy 无 nginx 前置（gunicorn 直绑 0.0.0.0）——若某部署只监听 80，
密码明文过网且应用无任何提示。

设计（opt-in）：
- ENFORCE_HTTPS=true 时启用；未开启时零行为变化（部署无 TLS 时不会被锁死）
- X-Forwarded-Proto 仅在请求来自 TRUSTED_PROXIES 时采信，防止客户端
  伪造请求头绕过（与限流模块的可信代理口径一致）
- /api/health 豁免（本地/LB 探活通常为 HTTP，且不携带凭据）
- 命中 HTTPS 请求时自动附加 HSTS 响应头（max-age=1y）
"""
from flask import request

from app.utils.logging import get_logger

logger = get_logger(__name__)

_EXEMPT_PREFIXES = ("/api/health", "/metrics")

HSTS_HEADER = "Strict-Transport-Security"
HSTS_VALUE = "max-age=31536000; includeSubDomains"


def _is_https_request(app) -> bool:
    """判定当前请求是否可视为 HTTPS。

    request.is_secure 反映直连 socket 协议；TLS 在反代终止时依赖
    X-Forwarded-Proto，但仅信任 TRUSTED_PROXIES 内的来源。
    """
    if request.is_secure:
        return True
    if request.headers.get("X-Forwarded-Proto", "") == "https":
        return request.remote_addr in (app.config.get("TRUSTED_PROXIES") or [])
    return False


def register_https_guard(app) -> None:
    """注册 HTTPS 强制与 HSTS 中间件（ENFORCE_HTTPS=true 时生效）。"""
    from app.api.base import APIResponse

    if app.config.get("ENFORCE_HTTPS") and not (app.config.get("TRUSTED_PROXIES") or []):
        logger.warning(
            "ENFORCE_HTTPS=true 但 TRUSTED_PROXIES 未配置：反代终止 TLS 的部署"
            "（X-Forwarded-Proto=https）将被全部拒绝。直连 HTTPS（request.is_secure）"
            "不受影响。若经反代，请配置 TRUSTED_PROXIES=反代IP。",
        )

    @app.before_request
    def _enforce_https():
        if not app.config.get("ENFORCE_HTTPS"):
            return None
        if request.path.startswith(_EXEMPT_PREFIXES):
            if request.path == "/metrics" and app.config.get("METRICS_TOKEN"):
                pass  # 继续走下方 HTTPS 检查
            else:
                return None
        if _is_https_request(app):
            return None
        logger.warning("拒绝非 HTTPS 请求: path=%s remote=%s",
                       request.path, request.remote_addr)
        return APIResponse.error(
            message="请通过 HTTPS 访问本系统", status_code=400)

    @app.after_request
    def _add_hsts(response):
        if app.config.get("ENFORCE_HTTPS") and _is_https_request(app):
            response.headers.setdefault(HSTS_HEADER, HSTS_VALUE)
        return response
