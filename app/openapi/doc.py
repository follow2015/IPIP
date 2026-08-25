# -*- coding: utf-8 -*-
"""OpenAPI 路由注解装饰器

为 Flask 路由函数添加 OpenAPI 元数据（summary、tags、request/response schema），
在 spec 构建时自动收集并注册到 APISpec。
"""
import functools
from typing import Any, Dict, List, Optional


_path_registry: Dict[str, Dict[str, Any]] = {}


def doc(
    summary: str = "",
    tags: Optional[List[str]] = None,
    request_body: Optional[Dict[str, Any]] = None,
    responses: Optional[Dict[int, Dict[str, Any]]] = None,
    parameters: Optional[List[Dict[str, Any]]] = None,
    security: Optional[List[Dict[str, List[str]]]] = None,
    deprecated: bool = False,
):
    """路由 OpenAPI 注解装饰器

    将 OpenAPI 元数据附加到视图函数上，供 spec 构建时读取。

    Args:
        summary: 端点摘要
        tags: 标签列表（如 ["设备"]）
        request_body: 请求体 schema（如 {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/DeviceCreate"}}}}）
        responses: 响应定义（如 {200: {"description": "成功", "content": {...}}}）
        parameters: 路径/查询参数定义
        security: 安全方案（默认 [{"BearerAuth": []}]）
        deprecated: 是否已废弃

    Example:
        @device_bp.route("/", methods=["GET"])
        @login_required
        @doc(summary="查询设备列表", tags=["设备"], responses={200: {"description": "设备列表"}})
        def list_devices():
            ...
    """
    def decorator(func):
        _security = security if security is not None else [{"BearerAuth": []}]

        meta = {
            "summary": summary,
            "tags": tags or [],
            "responses": responses or {},
            "deprecated": deprecated,
            "security": _security,
        }
        if request_body:
            meta["request_body"] = request_body
        if parameters:
            meta["parameters"] = parameters

        func._openapi_meta = meta
        _path_registry[func.__name__] = meta

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper._openapi_meta = meta
        return wrapper
    return decorator


def public(
    summary: str = "",
    tags: Optional[List[str]] = None,
    request_body: Optional[Dict[str, Any]] = None,
    responses: Optional[Dict[int, Dict[str, Any]]] = None,
    parameters: Optional[List[Dict[str, Any]]] = None,
    deprecated: bool = False,
):
    """公开端点注解（不需要 JWT 认证）

    与 @doc 相同，但 security 为空列表（公开访问）。

    Args:
        summary: 端点摘要
        tags: 标签列表
        request_body: 请求体 schema
        responses: 响应定义
        parameters: 参数定义
        deprecated: 是否已废弃
    """
    return doc(
        summary=summary,
        tags=tags,
        request_body=request_body,
        responses=responses,
        parameters=parameters,
        security=[],
        deprecated=deprecated,
    )


def get_path_registry() -> Dict[str, Dict[str, Any]]:
    """获取全局路径注册表

    Returns:
        Dict: {function_name: openapi_meta}
    """
    return _path_registry
