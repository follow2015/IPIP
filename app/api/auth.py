# -*- coding: utf-8 -*-
"""
认证API

提供认证相关的HTTP端点，业务逻辑已移至服务层。
"""
from app.utils.logging import get_logger
import re
from typing import Dict, Optional
from urllib.parse import urlparse
from flask import Blueprint, request

from app.api.base import APIResponse, api_exception_handler
from app.openapi.doc import doc, public
from app.services.qrcode_service import QRCodeService
from app.utils import rate_limit_api
from app.utils.transactional import transactional
from app.persistence.user_repository import UserRepository
from app.persistence.user_log_repository import UserLogRepository
from config import Config
from marshmallow import Schema, fields, validate, EXCLUDE


class LoginSchema(Schema):
    """用户登录请求Schema"""
    class Meta:
        unknown = EXCLUDE
    username = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    password = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    remember = fields.Bool(load_default=False)


class QRCodeConfirmSchema(Schema):
    """确认二维码登录请求Schema"""
    class Meta:
        unknown = EXCLUDE
    scene_id = fields.Str(required=True)
    code = fields.Str(required=True, validate=validate.Length(min=1, max=200))


class QRCodeCompleteSchema(Schema):
    """完成二维码登录请求Schema"""
    class Meta:
        unknown = EXCLUDE
    scene_id = fields.Str(required=True)

logger = get_logger(__name__)

auth_bp = Blueprint("auth", __name__)

qrcode_service = QRCodeService()


def verify_token(token: str) -> Optional[Dict]:
    """验证JWT令牌（兼容函数）"""
    from app.utils.auth import auth_manager
    return auth_manager.verify_token(token)


def _extract_bearer_token():
    """从请求头提取 Bearer Token，失败返回 None"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    return auth_header.split(' ')[1]


def require_permission(*permissions):
    """要求特定权限的装饰器（兼容函数）"""
    from app.utils.auth import auth_manager
    return auth_manager.require_permission(*permissions)


class AuthError(Exception):
    """认证错误异常"""
    def __init__(self, message, status_code=401):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class SecurityValidator:
    """安全验证器"""

    @staticmethod
    def validate_domain(domain):
        """验证域名格式和安全性"""
        if not domain:
            return False

        domain = domain.split(':')[0]

        domain_pattern = re.compile(
            r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$'
        )

        if not domain_pattern.match(domain):
            return False

        ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
        if ip_pattern.match(domain):
            parts = domain.split('.')
            for part in parts:
                if not 0 <= int(part) <= 255:
                    return False

        return True

    @staticmethod
    def validate_url(url):
        """验证URL格式和安全性"""
        try:
            parsed = urlparse(url)

            if parsed.scheme not in ('http', 'https'):
                return False

            if not SecurityValidator.validate_domain(parsed.netloc):
                return False

            return True
        except Exception:
            return False

    @staticmethod
    def get_allowed_domains():
        """获取允许的域名列表"""
        allowed_domains = set(['127.0.0.1', 'localhost'])

        try:
            if hasattr(Config, 'ALLOWED_DOMAINS') and Config.ALLOWED_DOMAINS:
                raw_domains = Config.ALLOWED_DOMAINS
                if isinstance(raw_domains, str):
                    raw_domains = raw_domains.split(',')
                config_domains = [
                    domain.strip()
                    for domain in raw_domains
                    if domain.strip() and SecurityValidator.validate_domain(domain.strip())
                ]
                allowed_domains.update(config_domains)
        except Exception as e:
            logger.error("读取ALLOWED_DOMAINS配置失败: %s", e)

        return list(allowed_domains)

    @staticmethod
    def validate_request_origin(request):
        """验证请求来源"""
        referer = request.headers.get('Referer')
        if not referer:
            raise AuthError("拒绝访问：缺少Referer头", 403)

        origin = request.headers.get('Origin')
        if origin and not SecurityValidator.validate_url(origin):
            raise AuthError("拒绝访问：非法Origin", 403)

        if not SecurityValidator.validate_url(referer):
            raise AuthError("拒绝访问：非法Referer格式", 403)

        parsed_referer = urlparse(referer)
        referer_domain = parsed_referer.netloc.split(':')[0]

        allowed_domains = SecurityValidator.get_allowed_domains()
        if referer_domain not in allowed_domains:
            logger.warning("拒绝访问：非法来源 %s，允许的域名: %s", referer_domain, allowed_domains)
            raise AuthError("拒绝访问：非法来源", 403)

        return referer, referer_domain

    @staticmethod
    def validate_username(username):
        """验证用户名格式（委托给 SecurityService 统一实现）"""
        from app.services.security_service import SecurityService
        return SecurityService.validate_username(username)

    @staticmethod
    def validate_password(password):
        """验证密码强度（委托给 SecurityService 统一实现，避免策略漂移）"""
        from app.services.security_service import SecurityService
        return SecurityService.validate_password(password)

    @staticmethod
    def hash_password(password):
        """对密码进行哈希处理"""
        from app.utils.security.password import password_manager
        return password_manager.hash_password(password)

    @staticmethod
    def verify_password(password, hashed_password):
        """验证密码"""
        from app.utils.security.password import password_manager
        return password_manager.verify_password(password, hashed_password)


@auth_bp.route("/login", methods=["POST"])
@public(summary="用户名密码登录", tags=["认证"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Login"}}}}, responses={200: "LoginDataResponse", 401: "ApiError"})
@rate_limit_api
@api_exception_handler
@transactional
def login():
    """用户名密码登录

    用户通过用户名和密码进行登录认证。

    Request Body:
        {
            "username": "用户名",
            "password": "密码",
            "remember": false
        }

    Returns:
        JSON响应，包含访问令牌和用户信息
    """
    from app.utils.auth import auth_manager
    from app.services.user_service import UserService

    data = request.get_json()

    if not data:
        return APIResponse.error(message="请求数据格式错误", status_code=400)

    username = data.get("username", "").strip()
    password = data.get("password", "")
    remember = data.get("remember", False)

    if not username:
        return APIResponse.error(message="用户名不能为空", status_code=400)

    if not password:
        return APIResponse.error(message="密码不能为空", status_code=400)

    if not SecurityValidator.validate_username(username):
        return APIResponse.error(message="用户名格式不正确", status_code=400)

    if not password or len(password) > 128:
        return APIResponse.error(message="密码格式不正确", status_code=400)

    from app.services.switch_events import _get_redis
    r = _get_redis()
    if r:
        attempt_key = f"login_attempts:{username}"
        attempts = int(r.get(attempt_key) or 0)
        if attempts >= 5:
            return APIResponse.error("登录失败次数过多，请5分钟后重试", status_code=429)

    try:

        user_service = UserService(UserRepository(), UserLogRepository())
        auth_result = auth_manager.authenticate_password(username, password, user_service)

        if not auth_result:
            if r:
                r.incr(f"login_attempts:{username}")
                r.expire(f"login_attempts:{username}", 300)  # 5分钟窗口
            return APIResponse.error(message="用户名或密码错误", status_code=401)

        if r:
            r.delete(f"login_attempts:{username}")

        logger.info("用户登录成功: %s (IP=%s, UA=%s)",
                    username, request.remote_addr,
                    request.headers.get('User-Agent', '')[:100])

        _login_user_id = auth_result["user"].get("id")
        if _login_user_id is not None:
            user_service.update_last_login(
                user_id=_login_user_id,
                ip=request.remote_addr,
                login_type="password",
                user_agent=request.headers.get('User-Agent', '')[:512],
            )

        from app.utils.auth import permission_manager
        user_roles = auth_result["user"].get("roles", [])
        user_permissions = []
        for role in user_roles:
            role_perms = permission_manager.get_role_permissions(role)
            user_permissions.extend(role_perms)
        user_permissions = list(set(user_permissions))

        return APIResponse.success(
            data={
                "token": auth_result["access_token"],
                "refresh_token": auth_result.get("refresh_token"),
                "user": auth_result["user"],
                "permissions": user_permissions,
                "expires_in": auth_result.get("expires_in", 3600)
            },
            message="登录成功"
        )

    except AuthError as e:
        logger.warning("登录认证失败: %s - %s", username, e.message)
        return APIResponse.error(message=e.message, status_code=e.status_code)
    except Exception as e:
        logger.error("登录过程发生错误: %s - %s", username, str(e))
        return APIResponse.error(message="登录失败，请稍后重试", status_code=500)


@auth_bp.route("/logout", methods=["POST"])
@doc(summary="用户登出", tags=["认证"], responses={200: "ApiResponse", 401: "ApiError"})
@rate_limit_api
@api_exception_handler
def logout():
    """用户登出

    注销当前用户的登录状态。

    Headers:
        Authorization: Bearer <token>

    Returns:
        JSON响应
    """
    from app.utils.auth import auth_manager

    try:
        token = _extract_bearer_token()
        if not token:
            return APIResponse.error(message="未提供有效的访问令牌", status_code=401)

        success = auth_manager.logout(token)

        if success:
            logger.info("用户登出成功")
            return APIResponse.success(message="登出成功")
        else:
            return APIResponse.error(message="登出失败", status_code=400)

    except Exception as e:
        logger.error("登出过程发生错误: %s", str(e))
        return APIResponse.error(message="登出失败，请稍后重试", status_code=500)


@auth_bp.route("/profile", methods=["GET"])
@doc(summary="获取用户资料", tags=["认证"], responses={200: "UserResponse", 401: "ApiError"})
@rate_limit_api
@api_exception_handler
def get_profile():
    """获取用户资料

    获取当前登录用户的详细信息。

    Headers:
        Authorization: Bearer <token>

    Returns:
        JSON响应，包含用户信息
    """
    from app.utils.auth import auth_manager
    from app.services.user_service import UserService

    try:
        token = _extract_bearer_token()
        if not token:
            return APIResponse.error(message="未提供有效的访问令牌", status_code=401)

        token_payload = auth_manager.verify_token(token)

        if not token_payload:
            return APIResponse.error(message="访问令牌无效或已过期", status_code=401)

        user_service = UserService(UserRepository(), UserLogRepository())
        user_id = token_payload.get('user_id')

        if not user_id:
            return APIResponse.error(message="令牌中缺少用户ID", status_code=401)

        user = user_service.get_by_id(user_id)

        if not user:
            return APIResponse.error(message="用户不存在", status_code=404)

        user_dict = user.to_dict(include_sensitive=False)

        from app.utils.auth import permission_manager
        user_permissions = []
        for role in user.roles:
            role_perms = permission_manager.get_role_permissions(role.name)
            user_permissions.extend(role_perms)
        user_permissions = list(set(user_permissions))

        user_roles = [role.name for role in user.roles]

        user_data = {
            "id": user_dict.get("id"),
            "username": user_dict.get("username"),
            "email": user_dict.get("email"),
            "name": user_dict.get("name"),
            "real_name": user_dict.get("real_name"),
            "department": user_dict.get("department"),
            "contact_phone": user_dict.get("contact_phone"),
            "roles": user_roles,
            "is_active": user_dict.get("is_active"),
            "status": user_dict.get("status"),
            "created_at": user_dict.get("created_at"),
            "updated_at": user_dict.get("updated_at"),
            "permissions": user_permissions
        }

        return APIResponse.success(
            data=user_data,
            message="获取用户资料成功"
        )

    except Exception as e:
        logger.error("获取用户资料失败: %s", str(e))
        return APIResponse.error(message="获取用户资料失败", status_code=500)


@auth_bp.route("/generate-qr", methods=["POST"])
@public(summary="生成登录二维码", tags=["认证"], responses={200: "ApiResponse"})
@rate_limit_api
@api_exception_handler
def generate_qr():
    """生成登录二维码

    生成一个用于微信扫码登录的二维码，包含唯一的场景ID。

    Returns:
        JSON响应，包含二维码图片URL和场景ID
    """
    result = qrcode_service.generate_qr_code()
    return APIResponse.success(data=result, message="二维码生成成功")


@auth_bp.route("/check-qr-login", methods=["GET"])
@public(summary="检查二维码登录状态", tags=["认证"], parameters=[{"name": "scene_id", "in": "query", "required": True, "schema": {"type": "string"}}], responses={200: "ApiResponse"})
@rate_limit_api
@api_exception_handler
def check_qr_login():
    """检查二维码登录状态

    轮询检查二维码的登录状态。

    Query Parameters:
        scene_id: 二维码场景ID

    Returns:
        JSON响应，包含登录状态
    """
    scene_id = request.args.get("scene_id")

    if not scene_id:
        return APIResponse.error(message="缺少scene_id参数", status_code=400)

    result = qrcode_service.check_qr_status(scene_id)

    if result["status"] == "expired":
        return APIResponse.success(data=result, message="二维码已过期")
    elif result["status"] == "confirmed":
        return APIResponse.success(data=result, message="登录成功")
    else:
        return APIResponse.success(data=result, message="状态检查成功")


@auth_bp.route("/confirm-qr-login", methods=["POST"])
@public(summary="确认二维码登录（微信端调用）", tags=["认证"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/QRCodeConfirm"}}}}, responses={200: "ApiResponse", 400: "ApiError"})
@rate_limit_api
@api_exception_handler
def confirm_qr_login():
    """确认二维码登录（微信端调用）

    微信端扫码后调用此接口确认登录。
    使用微信授权码（code）换取 openid，后端校验，防止客户端伪造 openid。

    Request Body:
        {
            "scene_id": "场景ID",
            "code": "微信授权码（wx.login 获取）"
        }

    Returns:
        JSON响应
    """
    data = request.get_json()

    if not data or "scene_id" not in data or "code" not in data:
        return APIResponse.error(message="缺少必要参数(scene_id, code)", status_code=400)

    scene_id = data["scene_id"]
    code = data["code"]

    wechat_result = qrcode_service.exchange_code_for_openid(code)
    if not wechat_result:
        return APIResponse.error(message="微信授权失败", status_code=400)

    openid = wechat_result["openid"]
    user_info = wechat_result.get("user_info", {})

    success = qrcode_service.confirm_qr_scan(scene_id, openid, user_info)

    if not success:
        return APIResponse.error(message="二维码已过期或状态无效", status_code=400)

    return APIResponse.success(message="扫码成功")


@auth_bp.route("/complete-qr-login", methods=["POST"])
@public(summary="完成二维码登录（生成token）", tags=["认证"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/QRCodeComplete"}}}}, responses={200: "LoginDataResponse", 400: "ApiError"})
@rate_limit_api
@api_exception_handler
@transactional
def complete_qr_login():
    """完成二维码登录（生成token）

    微信端确认登录后调用此接口生成token。

    Request Body:
        {
            "scene_id": "场景ID"
        }

    Returns:
        JSON响应
    """
    from app.utils.auth import auth_manager
    from app.services.user_service import UserService

    data = request.get_json()

    if not data or "scene_id" not in data:
        return APIResponse.error(message="缺少scene_id参数", status_code=400)

    scene_id = data["scene_id"]

    cache_data = qrcode_service.cache_manager.get_qr_login(scene_id)

    if not cache_data:
        return APIResponse.error(message="二维码已过期", status_code=400)

    if cache_data.get("status") != "scanned":
        return APIResponse.error(message="二维码状态无效", status_code=400)

    openid = cache_data.get("openid")
    if not openid:
        return APIResponse.error(message="用户信息无效", status_code=400)

    user_service = UserService(UserRepository(), UserLogRepository())
    auth_result = auth_manager.authenticate_wechat(openid, user_service)

    if not auth_result:
        return APIResponse.error(message="用户未授权访问该系统", status_code=403)

    success = qrcode_service.complete_qr_login(
        scene_id,
        auth_result["access_token"],
        auth_result["user"]
    )

    if not success:
        return APIResponse.error(message="登录失败", status_code=500)

    return APIResponse.success(
        data={
            "token": auth_result["access_token"],
            "refresh_token": auth_result.get("refresh_token"),
            "user": auth_result["user"]
        },
        message="登录成功"
    )

