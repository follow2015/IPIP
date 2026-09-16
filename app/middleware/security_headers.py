# -*- coding: utf-8 -*-
"""基础安全响应头（审计 P2-15）

背景：应用此前只设 HSTS，且仅在 `ENFORCE_HTTPS=true` 且判定为 HTTPS 时设置；
`X-Frame-Options` / `X-Content-Type-Options` / `Referrer-Policy` 三者的缺失
意味着 Clickjacking、MIME sniffing 与 Referrer 泄漏三类风险没有任何缓解。

设计取舍：
- 一律 `setdefault`：不覆盖视图或其他中间件已显式设置的值（为将来上 CSP 留口）。
- 三个都是**纯响应头**，不改变响应体与状态码；对 SSE 长连接与 `/metrics` 抓取
  同样安全（本模块不设 CSP，避免误伤流式响应）。
- **本模块不引入 CSP**：antd + Vite 产物含内联样式，CSP 需结合前端实际资源加载
  逐步收紧（先 Report-Only 也需要上报通道），留待前端资源清单梳理后单独推进。
- 与 `ENFORCE_HTTPS` 无关：内网 HTTP 部署同样应带这三个头（它们与传输加密正交）。
- `X-Frame-Options: SAMEORIGIN` 而非 `DENY`：前端全仓无 `<iframe>` 消费，同源嵌入
  （若有）不受影响，跨源嵌入被拒 —— 恰好覆盖 Clickjacking 威胁面。
"""
from app.utils.logging import get_logger

logger = get_logger(__name__)

SECURITY_HEADERS = {
    "X-Frame-Options": "SAMEORIGIN",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def register_security_headers(app) -> None:
    """注册基础安全响应头（after_request，幂等）。

    Args:
        app: Flask 应用实例
    """

    @app.after_request
    def _add_security_headers(response):
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response
