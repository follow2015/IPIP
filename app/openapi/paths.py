# -*- coding: utf-8 -*-
"""OpenAPI 路径注册

从 Flask app 的 url_map 和视图函数的 _openapi_meta 属性
自动收集路径信息并注册到 APISpec。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from flask import current_app

if TYPE_CHECKING:
    from apispec import APISpec


TAG_DEFINITIONS = [
    {"name": "认证", "description": "登录/登出/Token 刷新"},
    {"name": "用户", "description": "用户管理 CRUD"},
    {"name": "机房", "description": "机房管理 CRUD"},
    {"name": "机柜", "description": "机柜管理 CRUD"},
    {"name": "设备", "description": "设备管理 CRUD + 批量操作"},
    {"name": "客户", "description": "客户管理 CRUD"},
    {"name": "交换机", "description": "交换机管理 + 端口操作 + 扫描"},
    {"name": "IP", "description": "IP 地址管理 + 封禁/解封"},
    {"name": "网段", "description": "网段管理"},
    {"name": "VLAN", "description": "VLAN 管理"},
    {"name": "RBAC", "description": "角色/权限管理"},
    {"name": "审计", "description": "审计日志查询"},
    {"name": "仪表盘", "description": "统计数据"},
    {"name": "链路聚合", "description": "LAG 管理"},
    {"name": "设备配置", "description": "配置备份/变更"},
    {"name": "健康检查", "description": "系统健康状态"},
]


def register_all_paths(spec: APISpec):
    for tag in TAG_DEFINITIONS:
        spec.tag(tag)

    app = current_app._get_current_object()

    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static" or rule.rule.startswith("/assets"):
            continue
        if not rule.rule.startswith("/api"):
            continue

        view_func = app.view_functions.get(rule.endpoint)
        if view_func is None:
            continue

        meta = getattr(view_func, "_openapi_meta", None)
        if meta is None:
            continue

        path = _flask_rule_to_openapi_path(rule.rule)
        methods = [m.lower() for m in rule.methods if m not in ("HEAD", "OPTIONS")]

        for method in methods:
            operation = _build_operation(meta, rule)
            try:
                spec.path(
                    path=path,
                    operations={method: operation},
                )
            except Exception:
                pass


def _flask_rule_to_openapi_path(rule: str) -> str:
    import re
    return re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", rule)


def _build_operation(meta: dict, rule) -> dict:
    operation = {
        "summary": meta.get("summary", ""),
        "tags": meta.get("tags", []),
        "responses": _resolve_responses(meta.get("responses", {})),
    }

    if meta.get("deprecated"):
        operation["deprecated"] = True

    if meta.get("request_body"):
        operation["requestBody"] = meta["request_body"]

    if meta.get("parameters"):
        operation["parameters"] = meta["parameters"]

    security = meta.get("security")
    if security is not None and security:
        operation["security"] = security

    return operation


def _resolve_responses(responses: dict) -> dict:
    resolved = {}
    for status_code, value in responses.items():
        if isinstance(value, str):
            resolved[status_code] = {
                "description": "成功",
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{value}"}
                    }
                },
            }
        elif isinstance(value, dict):
            if "schema" in value and isinstance(value["schema"], str):
                schema_name = value.pop("schema")
                resolved[status_code] = {
                    "description": value.get("description", "成功"),
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{schema_name}"}
                        }
                    },
                }
            else:
                resolved[status_code] = value
        else:
            resolved[status_code] = value
    return resolved
