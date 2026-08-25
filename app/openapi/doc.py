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
    return _path_registry
