# -*- coding: utf-8 -*-
"""OpenAPI 规范端点

提供 /api/openapi.json（规范文件）和 /api/docs（Swagger UI）端点。

安全：匿名用户可借此获取全部 API 端点/参数/权限要求，用于侦察，
故两个端点均要求登录鉴权；生产环境可设环境变量 ENABLE_SWAGGER_DOCS=false
完全关闭（返回 404），避免暴露。
"""
import os

from flask import Blueprint, jsonify, current_app
from app.utils.auth import login_required

openapi_bp = Blueprint("openapi", __name__)


def _docs_disabled() -> bool:
    """生产环境通过 ENABLE_SWAGGER_DOCS=false 完全关闭文档端点。"""
    return os.environ.get("ENABLE_SWAGGER_DOCS", "true").lower() in ("false", "0", "no")


@openapi_bp.route("/openapi.json", methods=["GET"])
@login_required
def get_openapi_spec():
    """返回 OpenAPI 3.0 规范 JSON

    动态生成规范，包含所有已注册的 Schema 和路径信息。
    """
    if _docs_disabled():
        return jsonify({"error": "not found"}), 404
    from app.openapi.spec import get_spec
    from app.openapi.paths import register_all_paths

    spec = get_spec()
    register_all_paths(spec)

    return jsonify(spec.to_dict())


@openapi_bp.route("/docs", methods=["GET"])
@login_required
def swagger_ui():
    """Swagger UI 页面（内联 HTML，无需外部依赖）"""
    if _docs_disabled():
        return jsonify({"error": "not found"}), 404
    html = """<!DOCTYPE html>
<html>
<head>
    <title>IPIP API Docs</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" type="text/css"
          href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
    SwaggerUIBundle({
        url: "/api/openapi.json",
        dom_id: '#swagger-ui',
        presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.presets.SwaggerUIStandaloneLayout],
        layout: "BaseLayout"
    })
</script>
</body>
</html>"""
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}
