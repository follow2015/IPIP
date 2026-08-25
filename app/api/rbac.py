# -*- coding: utf-8 -*-
"""
RBAC权限管理API

提供角色和权限管理的API端点。
重构：API 层不再直接使用 db.session 或 Model.query，全部经由 RbacService。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request

from app.api.base import APIResponse, api_exception_handler
from app.utils.transactional import transactional
from app.services.rbac_service import rbac_service
from app.openapi.doc import doc, public
from app.utils.auth import login_required, permission_required
from app.exceptions.validation import ValidationError

logger = get_logger(__name__)


rbac_bp = Blueprint("rbac", __name__, url_prefix="/api/rbac")


@rbac_bp.route("/roles/", methods=["GET"])
@doc(summary="获取角色列表", tags=["RBAC"], responses={200: "RoleResponse", 401: "ApiError"})
@login_required
@permission_required("user:view")
@api_exception_handler
def get_roles():
    page     = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search   = request.args.get("search", "", type=str)
    status   = request.args.get("status", type=int)

    result = rbac_service.list_roles(
        page=page, per_page=per_page, search=search, status=status,
    )
    return APIResponse.paginated(
        data=result["data"],
        page=result["page"],
        per_page=result["per_page"],
        total=result["total"],
        message="获取角色列表成功",
    )


@rbac_bp.route("/roles/<int:role_id>/", methods=["GET"])
@doc(summary="获取角色详情", tags=["RBAC"], responses={200: "RoleResponse", 404: "ApiError"})
@login_required
@permission_required("user:view")
@api_exception_handler
def get_role(role_id):
    role = rbac_service.get_role(role_id)
    if not role:
        return APIResponse.error(message="角色不存在", status_code=404)
    role_dict = role.to_dict()
    role_dict["permissions"] = [p.code for p in role.permissions]
    role_dict["users"]       = [u.id  for u in role.users]
    return APIResponse.success(data=role_dict, message="获取角色详情成功")


@rbac_bp.route("/roles/", methods=["POST"])
@doc(summary="创建角色", tags=["RBAC"], responses={201: "RoleResponse", 409: "ApiError"})
@login_required
@permission_required("user:create")
@api_exception_handler
@transactional
def create_role():
    data = request.get_json(silent=True) or {}
    try:
        role = rbac_service.create_role(data)
    except ValidationError as e:
        status_code = 409 if "已存在" in str(e) else 400
        return APIResponse.error(str(e), status_code=status_code)

    return APIResponse.success(data=role.to_dict(), message="角色创建成功", status_code=201)


@rbac_bp.route("/roles/<int:role_id>/", methods=["PUT"])
@doc(summary="更新角色", tags=["RBAC"], responses={200: "RoleResponse", 409: "ApiError"})
@login_required
@permission_required("user:update")
@api_exception_handler
@transactional
def update_role(role_id):
    data = request.get_json(silent=True) or {}
    try:
        role = rbac_service.update_role(role_id, data)
    except ValidationError as e:
        return APIResponse.error(str(e), status_code=409)

    if not role:
        return APIResponse.error(message="角色不存在", status_code=404)
    return APIResponse.success(data=role.to_dict(), message="角色更新成功")


@rbac_bp.route("/roles/<int:role_id>/", methods=["DELETE"])
@doc(summary="删除角色", tags=["RBAC"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("user:delete")
@api_exception_handler
@transactional
def delete_role(role_id):
    try:
        result = rbac_service.delete_role(role_id)
    except ValidationError as e:
        return APIResponse.error(str(e), status_code=400)

    if not result:
        return APIResponse.error(message="角色不存在", status_code=404)
    return APIResponse.success(message="角色删除成功")


@rbac_bp.route("/roles/batch-delete", methods=["POST"])
@doc(summary="批量删除角色", tags=["RBAC"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("user:delete")
@api_exception_handler
@transactional
def batch_delete_roles():
    data = request.get_json(silent=True) or {}
    ids  = data.get("ids", [])

    if not isinstance(ids, list):
        return APIResponse.error("ID列表格式错误", status_code=400)

    result = rbac_service.batch_delete_roles(ids)
    message = f"成功删除 {result['deleted']} 个角色"
    if result["failed"]:
        message += f"，{result['failed_count']} 个删除失败"

    return APIResponse.success(data=result, message=message)


@rbac_bp.route("/roles/<int:role_id>/permissions/", methods=["GET"])
@doc(summary="获取角色权限列表", tags=["RBAC"], responses={200: "PermissionResponse", 404: "ApiError"})
@login_required
@permission_required("user:view")
@api_exception_handler
def get_role_permissions(role_id):
    perms = rbac_service.get_role_permissions(role_id)
    if perms is None:
        return APIResponse.error(message="角色不存在", status_code=404)
    return APIResponse.success(data=perms, message="获取角色权限成功")


@rbac_bp.route("/roles/<int:role_id>/permissions/", methods=["PUT", "POST"])
@doc(summary="更新角色权限", tags=["RBAC"], responses={200: "PermissionResponse", 400: "ApiError"})
@login_required
@permission_required("user:update")
@api_exception_handler
@transactional
def update_role_permissions(role_id):
    data = request.get_json(silent=True) or {}
    permission_codes = data.get("permissions", [])

    if not isinstance(permission_codes, list):
        return APIResponse.error("权限列表格式错误", status_code=400)

    try:
        result = rbac_service.update_role_permissions(role_id, permission_codes)
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="VALIDATION_ERROR", status_code=400)

    if result is None:
        return APIResponse.error(message="角色不存在", status_code=404)

    return APIResponse.success(data=result, message="角色权限更新成功")


@rbac_bp.route("/permissions/", methods=["GET"])
@doc(summary="获取权限列表", tags=["RBAC"], responses={200: "PermissionResponse", 401: "ApiError"})
@login_required
@permission_required("user:view")
@api_exception_handler
def get_permissions():
    page     = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    search   = request.args.get("search", "", type=str)
    category = request.args.get("category", "", type=str)

    result = rbac_service.list_permissions(
        page=page, per_page=per_page, search=search, category=category,
    )
    return APIResponse.paginated(
        data=result["data"],
        page=result["page"],
        per_page=result["per_page"],
        total=result["total"],
        message="获取权限列表成功",
    )


@rbac_bp.route("/permissions/categories/", methods=["GET"])
@doc(summary="获取权限分类列表", tags=["RBAC"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@permission_required("user:view")
@api_exception_handler
def get_permission_categories():
    categories = rbac_service.list_permission_categories()
    return APIResponse.success(data=categories, message="获取权限分类成功")


@rbac_bp.route("/users/<int:user_id>/roles/", methods=["GET"])
@doc(summary="获取用户角色列表", tags=["RBAC"], responses={200: "RoleResponse", 404: "ApiError"})
@login_required
@permission_required("user:view")
@api_exception_handler
def get_user_roles(user_id):
    roles = rbac_service.get_user_roles(user_id)
    if roles is None:
        return APIResponse.error(message="用户不存在", status_code=404)
    return APIResponse.success(data=roles, message="获取用户角色成功")


@rbac_bp.route("/users/<int:user_id>/roles/", methods=["PUT"])
@doc(summary="更新用户角色", tags=["RBAC"], responses={200: "RoleResponse", 400: "ApiError"})
@login_required
@permission_required("user:update")
@api_exception_handler
@transactional
def update_user_roles(user_id):
    data = request.get_json(silent=True) or {}
    role_ids = data.get("role_ids", [])

    if not isinstance(role_ids, list):
        return APIResponse.error("角色ID列表格式错误", status_code=400)

    try:
        result = rbac_service.update_user_roles(user_id, role_ids)
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="VALIDATION_ERROR", status_code=400)

    if result is None:
        return APIResponse.error(message="用户不存在", status_code=404)

    return APIResponse.success(data=result, message="用户角色更新成功")


def register_rbac_routes(app):
    app.register_blueprint(rbac_bp)
    logger.info("RBAC Blueprint 注册完成")
