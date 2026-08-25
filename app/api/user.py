# -*- coding: utf-8 -*-
"""
用户认证API

提供用户登录、注册、令牌刷新等端点，业务逻辑已移至服务层。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request, g

from app.api.base import APIResponse, RequestValidator, api_exception_handler
from app.openapi.doc import doc, public
from app.services.user_service import UserService
from app.services.security_service import SecurityService
from app.persistence.user_repository import UserRepository
from app.persistence.user_log_repository import UserLogRepository
from marshmallow import Schema, fields, validate, EXCLUDE

from app.utils import (
    auth_manager,
    login_required,
    permission_required,
    rate_limit_api,
    rate_limit_login,
)
from app.utils.transactional import transactional


class UserLoginSchema(Schema):
    """用户登录请求Schema"""
    class Meta:
        unknown = EXCLUDE
    username = fields.Str(required=True)
    password = fields.Str(required=True)


class UserRegisterSchema(Schema):
    """用户注册请求Schema"""
    class Meta:
        unknown = EXCLUDE
    username = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    password = fields.Str(required=True, validate=validate.Length(min=6, max=200))
    email = fields.Str(required=True, validate=validate.Length(max=200))
    role = fields.Str(validate=validate.Length(max=50), allow_none=True)


class RefreshTokenSchema(Schema):
    """刷新令牌请求Schema"""
    class Meta:
        unknown = EXCLUDE
    refresh_token = fields.Str(required=True)


class UserUpdateRequestSchema(Schema):
    """更新用户信息请求Schema"""
    class Meta:
        unknown = EXCLUDE
    username = fields.Str(validate=validate.Length(max=100), allow_none=True)
    name = fields.Str(validate=validate.Length(max=100), allow_none=True)
    email = fields.Str(validate=validate.Length(max=200), allow_none=True)
    department = fields.Str(validate=validate.Length(max=100), allow_none=True)
    contact_phone = fields.Str(validate=validate.Length(max=50), allow_none=True)
    status = fields.Int(allow_none=True)
    password = fields.Str(validate=validate.Length(min=6, max=200), allow_none=True)


class ChangePasswordSchema(Schema):
    """修改密码请求Schema"""
    class Meta:
        unknown = EXCLUDE
    username = fields.Str(required=True)
    user_id = fields.Int(required=True)
    old_password = fields.Str(required=True)
    new_password = fields.Str(required=True, validate=validate.Length(min=6))
    confirm_password = fields.Str(required=True)


class ResetPasswordSchema(Schema):
    """重置密码请求Schema"""
    class Meta:
        unknown = EXCLUDE
    password = fields.Str(required=True, validate=validate.Length(min=6))


logger = get_logger(__name__)
user_bp = Blueprint("user", __name__)

user_service = UserService(UserRepository(), UserLogRepository())
security_service = SecurityService()


def _get_client_ip() -> str:
    """从请求头中提取真实客户端 IP。

    优先读取反向代理写入的 X-Forwarded-For，取第一个非空段；
    否则回退到 request.remote_addr。
    """
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or ""



@user_bp.route("/login", methods=["POST"])
@public(summary="用户登录", tags=["用户"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/UserLogin"}}}}, responses={200: "LoginDataResponse", 401: "ApiError"})
@rate_limit_login
@api_exception_handler
@transactional
def login():
    """用户登录

    Request Body:
        username: 用户名
        password: 密码

    Returns:
        JSON响应，包含访问令牌、刷新令牌和用户信息
    """
    client_ip = _get_client_ip()

    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return APIResponse.error("用户名和密码不能为空", status_code=400)

    logger.info(f"登录尝试: username={username}, ip={client_ip}")

    auth_result = auth_manager.authenticate(username, password, user_service)

    if not auth_result:
        logger.warning(
            f"认证失败: username={username}, ip={client_ip}, reason=invalid_credentials"
        )
        return APIResponse.error(
            message="用户名或密码错误",
            error_code="INVALID_CREDENTIALS",
            status_code=401,
        )

    user = auth_result["user"]
    access_token = auth_result["access_token"]
    refresh_token = auth_result["refresh_token"]
    auth_type = auth_result.get("auth_type", "web")

    logged = user_service.update_last_login(
        user_id=user["id"], ip=client_ip, login_type=auth_type,
        user_agent=request.headers.get("User-Agent"),
    )
    if not logged:
        logger.warning(f"登录日志写入失败: user_id={user['id']}, ip={client_ip}")

    logger.info(
        f"登录成功: username={username}, user_id={user['id']}, "
        f"ip={client_ip}, auth_type={auth_type}"
    )

    return APIResponse.success(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user,
        },
        message="登录成功",
    )


@user_bp.route("/register", methods=["POST"])
@doc(summary="用户注册", tags=["用户"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/UserRegister"}}}}, responses={201: "UserResponse", 400: "ApiError", 409: "ApiError"})
@login_required
@permission_required("user:create")
@rate_limit_api
@transactional
@api_exception_handler
def register():
    """用户注册

    Request Body:
        username: 用户名
        password: 密码
        email:    邮箱
        role:     角色（可选，默认 user）

    Returns:
        JSON响应，包含新创建的用户信息
    """
    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    RequestValidator.validate_required_fields(data, ["username", "password", "email"])

    username = data["username"]
    password = data["password"]
    email    = data["email"]
    role     = "user"

    if not security_service.validate_username(username):
        return APIResponse.error("用户名格式无效", error_code="INVALID_USERNAME", status_code=400)

    is_valid, error_msg = security_service.validate_password(password)
    if not is_valid:
        return APIResponse.error(error_msg, error_code="WEAK_PASSWORD", status_code=400)

    if user_service.get_by_username(username):
        return APIResponse.error("用户名已存在", error_code="USERNAME_EXISTS", status_code=409)

    if user_service.get_by_email(email):
        return APIResponse.error("邮箱已被使用", error_code="EMAIL_EXISTS", status_code=409)

    user = user_service.create_user({
        "username":      username,
        "password":      password,
        "email":         email,
        "role":          role,
        "name":          data.get("name", username),
        "department":    data.get("department"),
        "contact_phone": data.get("contact_phone"),
    })

    return APIResponse.success(
        data=user.to_dict(exclude=["password"]),   # 字段名为 password，非 password_hash
        message="注册成功",
        status_code=201,
    )


@user_bp.route("/refresh", methods=["POST"])
@public(summary="刷新访问令牌", tags=["用户"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/RefreshToken"}}}}, responses={200: "LoginDataResponse", 401: "ApiError"})
@rate_limit_api
@api_exception_handler
def refresh_token():
    """刷新访问令牌

    Request Body:
        refresh_token: 刷新令牌
    """
    data = request.get_json()
    if not data or "refresh_token" not in data:
        return APIResponse.error("缺少refresh_token参数", status_code=400)

    new_token = auth_manager.refresh_token(data["refresh_token"])

    if not new_token:
        return APIResponse.error(
            "刷新令牌无效或已过期",
            error_code="INVALID_REFRESH_TOKEN",
            status_code=401,
        )

    return APIResponse.success(data=new_token, message="令牌刷新成功")


@user_bp.route("/logout", methods=["POST"])
@doc(summary="用户登出", tags=["用户"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@api_exception_handler
def logout():
    """用户登出 — 撤销当前访问令牌"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    auth_manager.revoke_token(token)
    return APIResponse.success(message="登出成功")



@user_bp.route("/verify", methods=["GET"])
@doc(summary="验证访问令牌", tags=["用户"], responses={200: "VerifyDataResponse", 401: "ApiError"})
@login_required
@api_exception_handler
def verify_token():
    """验证访问令牌，返回当前用户基本信息"""
    user_id = g.current_user["user_id"]
    user = user_service.get_by_id(user_id)

    if not user:
        return APIResponse.error("用户不存在", error_code="USER_NOT_FOUND", status_code=404)

    return APIResponse.success(
        data={
            "valid":    True,
            "user_id":  user.id,
            "username": user.username,
            "email":    user.email,
            "roles":    [r.name for r in user.roles],
        },
        message="令牌验证成功",
    )


@user_bp.route("/me", methods=["GET"])
@doc(summary="获取当前用户信息", tags=["用户"], responses={200: "UserResponse", 401: "ApiError"})
@login_required
@api_exception_handler
def get_current_user():
    """获取当前用户完整信息"""
    user_id = g.current_user["user_id"]
    user = user_service.get_by_id(user_id)

    if not user:
        return APIResponse.error("用户不存在", error_code="USER_NOT_FOUND", status_code=404)

    return APIResponse.success(
        data=user.to_dict(exclude=["password"]),
        message="获取用户信息成功",
    )


@user_bp.route("/me/profile", methods=["PUT"])
@doc(summary="更新当前用户个人信息", tags=["用户"], request_body={"content": {"application/json": {"schema": {"type": "object", "properties": {"username": {"type": "string", "maxLength": 100}, "name": {"type": "string", "maxLength": 100}, "email": {"type": "string", "maxLength": 200}, "contact_phone": {"type": "string", "maxLength": 50}}}}}}, responses={200: "UserResponse", 400: "ApiError", 401: "ApiError"})
@login_required
@transactional
@api_exception_handler
def update_my_profile():
    """更新当前用户个人信息（仅允许修改自己的 username/name/email/contact_phone）

    Request Body:
        username:      用户名（可选）
        name:          真实姓名（可选）
        email:         邮箱（可选）
        contact_phone: 联系电话（可选）
    """
    user_id = g.current_user["user_id"]
    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    allowed = ["username", "name", "email", "contact_phone"]
    update_data = {k: v for k, v in data.items() if k in allowed and v is not None}

    if not update_data:
        return APIResponse.error("没有需要更新的字段", status_code=400)

    updated = user_service.update_user(user_id, update_data)

    return APIResponse.success(
        data=updated.to_dict(exclude=["password"]),
        message="个人信息更新成功",
    )


@user_bp.route("/me/login-logs", methods=["GET"])
@doc(summary="获取当前用户登录日志", tags=["用户"], parameters=[{"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "per_page", "in": "query", "schema": {"type": "integer", "default": 20}}], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@api_exception_handler
def get_my_login_logs():
    """获取当前用户的登录日志

    Query Parameters:
        page:      页码（默认1）
        per_page: 每页数量（默认20，最大100）
    """
    user_id   = g.current_user["user_id"]
    page      = request.args.get("page", 1, type=int)
    per_page  = min(request.args.get("per_page", 20, type=int), 100)

    result = user_service.get_login_logs(user_id=user_id, page=page, page_size=per_page)

    return APIResponse.paginated(
        data=result["data"],
        page=result["page"],
        per_page=result["page_size"],
        total=result["total_count"],
        message="获取登录日志成功",
    )


@user_bp.route("/<int:user_id>/login-logs", methods=["GET"])
@doc(summary="管理员获取指定用户登录日志", tags=["用户"], parameters=[{"name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}}, {"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "per_page", "in": "query", "schema": {"type": "integer", "default": 20}}], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@permission_required("user:view")
@api_exception_handler
def get_user_login_logs(user_id):
    """管理员获取指定用户的登录日志

    Path Parameters:
        user_id: 用户ID

    Query Parameters:
        page:      页码（默认1）
        per_page: 每页数量（默认20，最大100）
    """
    page      = request.args.get("page", 1, type=int)
    per_page  = min(request.args.get("per_page", 20, type=int), 100)

    result = user_service.get_login_logs(user_id=user_id, page=page, page_size=per_page)

    return APIResponse.paginated(
        data=result["data"],
        page=result["page"],
        per_page=result["page_size"],
        total=result["total_count"],
        message="获取用户登录日志成功",
    )


@user_bp.route("/login-logs", methods=["GET"])
@doc(summary="管理员获取全局登录日志", tags=["用户"], parameters=[{"name": "user_id", "in": "query", "schema": {"type": "integer"}}, {"name": "start_time", "in": "query", "schema": {"type": "string", "format": "date-time"}}, {"name": "end_time", "in": "query", "schema": {"type": "string", "format": "date-time"}}, {"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "per_page", "in": "query", "schema": {"type": "integer", "default": 20}}], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@permission_required("user:view")
@api_exception_handler
def get_all_login_logs():
    """管理员获取全局登录日志（支持按用户、时间段筛选）

    Query Parameters:
        user_id:     按用户ID过滤（可选）
        start_time:  起始时间 ISO 格式（可选）
        end_time:    结束时间 ISO 格式（可选）
        page:        页码（默认1）
        per_page:   每页数量（默认20，最大100）
    """
    user_id    = request.args.get("user_id", None, type=int)
    start_time = request.args.get("start_time", None, type=str)
    end_time   = request.args.get("end_time", None, type=str)
    page       = request.args.get("page", 1, type=int)
    per_page   = min(request.args.get("per_page", 20, type=int), 100)

    result = user_service.get_login_logs(
        user_id=user_id, start_time=start_time, end_time=end_time,
        page=page, page_size=per_page,
    )

    return APIResponse.paginated(
        data=result["data"],
        page=result["page"],
        per_page=result["page_size"],
        total=result["total_count"],
        message="获取登录日志成功",
    )



@user_bp.route("/", methods=["GET"])
@doc(summary="获取用户列表", tags=["用户"], parameters=[{"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "per_page", "in": "query", "schema": {"type": "integer", "default": 20}}, {"name": "search", "in": "query", "schema": {"type": "string"}}, {"name": "all", "in": "query", "schema": {"type": "string", "default": "false"}}, {"name": "active_only", "in": "query", "schema": {"type": "string", "default": "false"}}], responses={200: "UserResponse", 401: "ApiError"})
@login_required
@permission_required("user:view")
@rate_limit_api
@api_exception_handler
def list_users():
    """获取用户列表（支持分页、搜索过滤）

    Query Parameters:
        page:       页码（默认1）
        per_page:   每页数量（默认20）
        search:     搜索关键词，模糊匹配用户名/邮箱/姓名（可选）
        all:        是否获取所有用户，不分页（默认false）
        active_only: 配合 all=true 使用，只返回激活用户
    """
    get_all = request.args.get("all", "false").lower() == "true"
    search = request.args.get("search", type=str)

    if get_all:
        active_only = request.args.get("active_only", "false").lower() == "true"
        users = user_service.get_all_users(active_only=active_only)
        return APIResponse.success(
            data=[u.to_dict(exclude=["password"]) for u in users],
            message="获取用户列表成功",
        )

    page, per_page = RequestValidator.validate_pagination_params()

    if search:
        result = user_service.user_repository.search(
            search_fields=["username", "email", "name"],
            keyword=search,
            page=page,
            page_size=per_page,
        )
        users = result.get("data", [])
        total = result.get("total_count", 0)
    else:
        users, total = user_service.get_paginated(page=page, per_page=per_page)

    return APIResponse.paginated(
        data=[u.to_dict(exclude=["password"]) for u in users],
        page=page,
        per_page=per_page,
        total=total,
        message="获取用户列表成功",
    )


@user_bp.route("/<int:user_id>/", methods=["PUT"])
@doc(summary="更新用户信息", tags=["用户"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/UserUpdateRequest"}}}}, parameters=[{"name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "UserResponse", 400: "ApiError", 401: "ApiError", 404: "ApiError"})
@login_required
@permission_required("user:update")
@rate_limit_api
@transactional
@api_exception_handler
def update_user(user_id):
    """更新用户信息

    Request Body:
        username:      用户名（可选）
        name:          真实姓名（可选）
        email:         邮箱（可选）
        department:    部门（可选）
        contact_phone: 联系电话（可选）
        status:        状态 0=正常 1=停用（可选）
        password:      新密码（可选，为空则不修改）
    """
    user = user_service.get_by_id(user_id)
    if not user:
        return APIResponse.error("用户不存在", status_code=404)

    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    allowed = ["username", "name", "email", "department", "contact_phone", "status", "password"]
    update_data = {k: v for k, v in data.items() if k in allowed and v is not None}

    if not update_data:
        return APIResponse.error("没有需要更新的字段", status_code=400)

    updated = user_service.update_user(user_id, update_data)

    return APIResponse.success(
        data=updated.to_dict(exclude=["password"]),
        message="用户更新成功",
    )


@user_bp.route("/batch-delete", methods=["POST"])
@doc(summary="批量删除用户", tags=["用户"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchDelete"}}}}, responses={200: "ApiResponse", 400: "ApiError", 401: "ApiError"})
@login_required
@permission_required("user:delete")
@rate_limit_api
@transactional
@api_exception_handler
def batch_delete_users():
    """批量删除用户

    Request Body:
        ids: 用户ID列表
    """
    data = request.get_json()
    if not data or "ids" not in data:
        return APIResponse.error("请提供要删除的用户ID列表", status_code=400)

    ids = data.get("ids", [])
    if not isinstance(ids, list):
        return APIResponse.error("ID列表格式错误", status_code=400)

    deleted_count = 0
    failed_ids    = []

    for user_id in ids:
        try:
            if user_service.delete_user(user_id):
                deleted_count += 1
            else:
                failed_ids.append(user_id)
        except Exception as e:
            logger.error(f"删除用户 {user_id} 失败: {e}")
            failed_ids.append(user_id)

    message = f"成功删除 {deleted_count} 个用户"
    if failed_ids:
        message += f"，{len(failed_ids)} 个删除失败"

    return APIResponse.success(
        data={
            "deleted_count": deleted_count,
            "failed_count":  len(failed_ids),
            "failed_ids":    failed_ids,
        },
        message=message,
    )


@user_bp.route("/<int:user_id>/permissions", methods=["GET"])
@doc(summary="获取用户权限列表", tags=["用户"], parameters=[{"name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 401: "ApiError", 404: "ApiError"})
@login_required
@permission_required("user:view")
@api_exception_handler
def get_user_permissions(user_id):
    """获取用户的权限列表

    返回用户通过角色继承的所有权限。

    Args:
        user_id: 用户ID

    Returns:
        JSON响应，包含用户权限列表
    """
    user = user_service.get_by_id(user_id)
    if not user:
        return APIResponse.error("用户不存在", error_code="USER_NOT_FOUND", status_code=404)

    permissions = []
    seen_codes = set()

    for role in user.roles:
        for permission in role.permissions:
            if permission.code not in seen_codes:
                permissions.append(permission.to_dict())
                seen_codes.add(permission.code)

    return APIResponse.success(
        data=permissions,
        message="获取用户权限成功",
    )



@user_bp.route("/change-password", methods=["POST"])
@doc(summary="修改当前用户密码", tags=["用户"], request_body={"content": {"application/json": {"schema": {"type": "object", "required": ["old_password", "new_password"], "properties": {"old_password": {"type": "string"}, "new_password": {"type": "string", "minLength": 6}}}}}}, responses={200: "ApiResponse", 400: "ApiError", 401: "ApiError"})
@login_required
@transactional
@api_exception_handler
def change_password():
    """修改当前用户密码（仅允许修改自己的密码，需验证原密码）

    Request Body:
        old_password: 原密码
        new_password: 新密码
    """
    user_id = g.current_user["user_id"]
    data = request.get_json()
    if not data:
        return APIResponse.error("请求数据不能为空", status_code=400)

    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if not old_password or not new_password:
        return APIResponse.error("原密码和新密码不能为空", status_code=400)

    if new_password != data.get("confirm_password", new_password):
        return APIResponse.error("两次输入的新密码不一致", status_code=400)

    user_service.change_password(user_id, old_password, new_password)

    logger.info(f"用户 user_id={user_id} 通过API成功修改密码")
    return APIResponse.success(message="密码修改成功")


@user_bp.route("/<int:user_id>/reset-password", methods=["POST"])
@doc(summary="重置用户密码", tags=["用户"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ResetPassword"}}}}, parameters=[{"name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 400: "ApiError", 401: "ApiError"})
@login_required
@permission_required("user:update")
@transactional
def reset_user_password(user_id):
    """
    重置用户密码

    管理员重置指定用户的密码。不传密码时自动随机生成。

    Args:
        user_id: 用户ID

    Request Body:
        password: 新密码（可选，不传则随机生成）

    Returns:
        JSON响应，包含重置结果和新密码
    """
    import secrets
    import string

    data = request.get_json(silent=True) or {}
    new_password = data.get('password')

    if not new_password:
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        new_password = ''.join(secrets.choice(chars) for _ in range(12))

    is_valid, error_msg = security_service.validate_password(new_password)
    if not is_valid:
        return APIResponse.error(message=error_msg, status_code=400)

    try:
        user_service.reset_password(user_id, new_password)
        logger.info(f"用户 {user_id} 通过API成功重置密码")
        return APIResponse.success(data={"reset": True, "new_password": new_password}, message="密码重置成功，请通过安全渠道通知用户新密码")
    except Exception as e:
        logger.error(f"重置密码失败: user_id={user_id}, error={e}")
        return APIResponse.error(message=str(e), status_code=500)
