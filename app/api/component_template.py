# -*- coding: utf-8 -*-
"""
配件模板管理 API 路由

提供配件模板的 CRUD + 按类别查询接口。
重构：API 层不再直接使用 db.session / Model.query，全部经由 ComponentTemplateService。
"""
from flask import Blueprint, request

from app.api.base import APIResponse, api_exception_handler
from app.openapi.doc import doc, public
from app.services.component_template_service import component_template_service
from app.utils import login_required, permission_required, rate_limit_api
from app.utils.transactional import transactional
from app.exceptions.validation import ValidationError

component_template_bp = Blueprint(
    "component_template", __name__, url_prefix="/api/component-templates"
)


@component_template_bp.route("", methods=["GET"])
@doc(summary="列出配件模板", tags=["设备"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
@api_exception_handler
def list_templates():
    """列出配件模板，支持按类别、启用状态和客户筛选。

    Query Parameters:
        category: 按类别筛选 (cpu/memory/disk/nic/gpu)
        is_active: 是否只返回启用的 (可选，不传则返回全部)
        customer_id: 按客户ID筛选 (可选)
        include_global: 传 customer_id 时是否包含全局通用模板 (默认 true)
    """
    category = request.args.get("category")
    customer_id = request.args.get("customer_id", type=int)
    is_active_str = request.args.get("is_active")
    include_global = request.args.get("include_global", "true").lower() == "true"

    is_active = None
    if is_active_str is not None:
        is_active = is_active_str.lower() == "true"

    data = component_template_service.list_templates(
        category=category,
        is_active=is_active,
        customer_id=customer_id,
        include_global=include_global,
    )
    return APIResponse.success(data=data)


@component_template_bp.route("/<int:template_id>", methods=["GET"])
@doc(summary="获取单个配件模板", tags=["设备"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
@api_exception_handler
def get_template(template_id):
    """获取单个配件模板"""
    t = component_template_service.get_template(template_id)
    if not t:
        return APIResponse.error(message="模板不存在", status_code=404)
    return APIResponse.success(data=t.to_dict())


@component_template_bp.route("", methods=["POST"])
@doc(summary="创建配件模板", tags=["设备"], responses={201: "ApiResponse", 409: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@api_exception_handler
@transactional
def create_template():
    """创建配件模板

    Request Body:
        category: 配件类别 (cpu/memory/disk/nic/gpu)
        brand: 品牌
        model: 型号
        spec: 规格详情 (JSON)
        is_active: 是否启用 (默认 true)
        sort_order: 排序权重
        remark: 备注
    """
    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    try:
        t = component_template_service.create_template(data)
    except ValidationError as e:
        return APIResponse.error(message=str(e), status_code=409)

    return APIResponse.success(data=t.to_dict(), message="模板创建成功", status_code=201)


@component_template_bp.route("/<int:template_id>", methods=["PUT"])
@doc(summary="更新配件模板", tags=["设备"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@api_exception_handler
@transactional
def update_template(template_id):
    """更新配件模板"""
    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    try:
        t = component_template_service.update_template(template_id, data)
    except ValidationError as e:
        return APIResponse.error(message=str(e), status_code=409)

    if not t:
        return APIResponse.error(message="模板不存在", status_code=404)
    return APIResponse.success(data=t.to_dict(), message="模板更新成功")


@component_template_bp.route("/<int:template_id>", methods=["DELETE"])
@doc(summary="删除配件模板", tags=["设备"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("device:update")
@rate_limit_api
@api_exception_handler
@transactional
def delete_template(template_id):
    """删除配件模板"""
    result = component_template_service.delete_template(template_id)
    if not result:
        return APIResponse.error(message="模板不存在", status_code=404)
    return APIResponse.success(message="模板删除成功")
