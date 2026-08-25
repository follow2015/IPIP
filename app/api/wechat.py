# -*- coding: utf-8 -*-
"""
微信认证API

提供微信小程序登录、网页授权登录、二维码扫码登录和JS-SDK配置等功能。
"""
from app.utils.logging import get_logger
from urllib.parse import quote

import requests
from flask import Blueprint, g, redirect, request

from app.services.user_service import UserService
from app.services.wx_service import WeChatService
from app.openapi.doc import doc, public
from app.utils.auth import auth_manager, login_required
from app.utils.transactional import transactional
from app.utils.qrcode_manager import QRCodeManager
from config import get_config
from app.api.base import APIResponse
from app.persistence.user_repository import UserRepository
from app.persistence.user_log_repository import UserLogRepository

logger = get_logger(__name__)
config = get_config()

wechat_bp = Blueprint("wechat", __name__, url_prefix="/api/wechat")

wx_service = WeChatService()
user_service = UserService(UserRepository(), UserLogRepository())

qr_manager = QRCodeManager()


def _mask_openid(openid: str) -> str:
    """脱敏 openid，仅保留前8位"""
    if not openid or len(openid) <= 8:
        return (openid or "") + "***"
    return openid[:8] + "***"


@wechat_bp.route("/js-sdk-config", methods=["GET"])
@doc(summary="获取微信JS-SDK配置", tags=["认证"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def get_js_sdk_config():
    """获取微信JS-SDK配置

    用于在网页中调用微信JS-SDK功能。

    Query Parameters:
        url: 当前页面的完整URL（必需）

    Returns:
        JSON: 包含appId、timestamp、nonceStr、signature等配置

    Example:
        GET /api/wechat/js-sdk-config?url=https://example.com/page
    """
    try:
        url = request.args.get("url")
        if not url:
            url = request.headers.get("Referer")

        if not url:
            return APIResponse.error(message="缺少URL参数", status_code=400)

        logger.info("用户 %s 请求微信JS-SDK配置，URL: %s", g.current_user['user_id'], url)

        wx_config = wx_service.generate_js_sdk_config(url)

        return APIResponse.success(data={"config": wx_config})

    except Exception as e:
        logger.error("获取微信JS-SDK配置失败: %s", e, exc_info=True)
        return APIResponse.error(message="获取微信配置失败", status_code=500)


@wechat_bp.route("/miniprogram-login", methods=["POST"])
@public(summary="微信小程序登录", tags=["认证"], responses={200: "ApiResponse", 400: "ApiError"})
def miniprogram_login():
    """微信小程序登录

    使用微信小程序的code换取openid，然后进行用户认证。

    Request Body:
        {
            "code": "微信小程序登录凭证"
        }

    Returns:
        JSON: 包含token和用户信息

    Example:
        POST /api/wechat/miniprogram-login
        {
            "code": "0x1a2b3c4d"
        }
    """
    try:
        data = request.get_json()
        if not data or "code" not in data:
            return APIResponse.error(message="缺少code参数", status_code=400)

        code = data["code"]

        url = "https://api.weixin.qq.com/sns/jscode2session"
        params = {
            "appid": config.WX_APPID,
            "secret": config.WX_SECRET,
            "js_code": code,
            "grant_type": "authorization_code",
        }

        logger.info("正在向微信服务器换取openid...")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        wx_data = response.json()

        if "errcode" in wx_data and wx_data["errcode"] != 0:
            error_msg = wx_data.get("errmsg", "未知错误")
            logger.error("微信API错误: %s", error_msg)
            return APIResponse.error(message=f"微信登录失败: {error_msg}", status_code=400)

        if "openid" not in wx_data:
            logger.error("微信返回数据中缺少openid")
            return APIResponse.error(message="微信登录失败：无法获取用户标识", status_code=400)

        openid = wx_data["openid"]
        session_key = wx_data.get("session_key")

        logger.info("成功获取openid: %s", _mask_openid(openid))

        auth_result = auth_manager.authenticate_wechat(openid, user_service)

        if not auth_result:
            logger.warning("微信用户未授权: %s", _mask_openid(openid))
            return APIResponse.error(message="用户未授权访问该系统", status_code=403)

        logger.info("微信小程序登录成功，用户ID: %s", auth_result['user']['id'])

        return APIResponse.success(data={
                "token": auth_result["access_token"],
                "refresh_token": auth_result["refresh_token"],
                "user": auth_result["user"],
                "auth_type": "wx",
                "openid": _mask_openid(openid),
            })

    except requests.RequestException as e:
        logger.error("微信API请求失败: %s", e, exc_info=True)
        return APIResponse.error(message="微信服务暂时不可用", status_code=500)
    except Exception as e:
        logger.error("微信小程序登录失败: %s", e, exc_info=True)
        return APIResponse.error(message="登录失败", status_code=500)


@wechat_bp.route("/web-auth", methods=["GET"])
@public(summary="微信网页授权登录", tags=["认证"], responses={200: "ApiResponse"})
def web_auth():
    """微信网页授权登录（第一步）

    重定向到微信授权页面获取code。

    Returns:
        Redirect: 重定向到微信授权页面
    """
    try:
        redirect_uri = request.url_root.rstrip("/") + "/api/wechat/web-auth-callback"

        is_local = any(domain in redirect_uri for domain in ["localhost", "127.0.0.1"])
        if not is_local:
            redirect_uri = redirect_uri.replace("http://", "https://")

        encoded_redirect_uri = quote(redirect_uri, safe="")

        wx_auth_url = (
            f"https://open.weixin.qq.com/connect/oauth2/authorize"
            f"?appid={config.WX_APPID}"
            f"&redirect_uri={encoded_redirect_uri}"
            f"&response_type=code"
            f"&scope=snsapi_base"
            f"&state=STATE#wechat_redirect"
        )

        logger.info("重定向到微信授权页面")
        return redirect(wx_auth_url)

    except Exception as e:
        logger.error("构建微信授权URL失败: %s", e, exc_info=True)
        return APIResponse.error(message="微信授权失败", status_code=500)


@wechat_bp.route("/web-auth-callback", methods=["GET"])
@public(summary="微信网页授权回调", tags=["认证"], responses={200: "ApiResponse", 400: "ApiError"})
def web_auth_callback():
    """微信网页授权回调（第二步）

    接收微信返回的code，换取access_token和openid，然后进行用户认证。

    Query Parameters:
        code: 微信授权码
        state: 状态参数

    Returns:
        Redirect: 重定向到前端页面，并在URL中携带token
    """
    try:
        code = request.args.get("code")
        state = request.args.get("state")

        if not code:
            logger.warning("微信授权回调缺少code参数")
            return APIResponse.error(message="微信授权失败：缺少code参数", status_code=400)

        logger.info("收到微信授权回调")

        url = "https://api.weixin.qq.com/sns/oauth2/access_token"
        params = {
            "appid": config.WX_APPID,
            "secret": config.WX_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        wx_data = response.json()

        logger.info("微信API响应: %s", wx_data)

        if "errcode" in wx_data and wx_data["errcode"] != 0:
            error_msg = wx_data.get("errmsg", "未知错误")
            logger.error("微信API错误: %s", error_msg)
            return APIResponse.error(message=f"微信授权失败：{error_msg}", status_code=400)

        if "openid" not in wx_data:
            logger.error("微信返回数据中缺少openid")
            return APIResponse.error(message="微信授权失败：无法获取用户标识", status_code=400)

        openid = wx_data["openid"]

        logger.info("成功获取openid: %s", _mask_openid(openid))

        auth_result = auth_manager.authenticate_wechat(openid, user_service)

        if not auth_result:
            logger.warning("微信用户未授权: %s", _mask_openid(openid))
            return APIResponse.error(message="用户未授权访问该系统", status_code=403)

        logger.info("微信网页授权登录成功，用户ID: %s", auth_result['user']['id'])

        token = auth_result["access_token"]
        frontend_url = "/"

        response = redirect(frontend_url)

        is_local = "localhost" in request.host or "127.0.0.1" in request.host
        response.set_cookie("token", token, httponly=True, samesite="Lax", secure=not is_local)

        return response

    except requests.RequestException as e:
        logger.error("微信API请求失败: %s", e, exc_info=True)
        return APIResponse.error(message="微信服务暂时不可用", status_code=500)
    except Exception as e:
        logger.error("微信授权回调处理失败: %s", e, exc_info=True)
        return APIResponse.error(message="系统错误", status_code=500)


@wechat_bp.route("/invalidate-cache", methods=["POST"])
@doc(summary="清除微信相关缓存", tags=["认证"], responses={200: "ApiResponse", 403: "ApiError"})
@login_required
def invalidate_cache():
    """清除微信相关缓存

    需要管理员权限。用于强制刷新access_token和jsapi_ticket。

    Returns:
        JSON: 操作结果
    """
    try:
        if g.current_user.get("role") != "admin":
            return APIResponse.error(message="权限不足", status_code=403)

        wx_service.invalidate_cache()

        logger.info("管理员 %s 清除了微信缓存", g.current_user['user_id'])

        return APIResponse.success(message="微信缓存已清除")

    except Exception as e:
        logger.error("清除微信缓存失败: %s", e, exc_info=True)
        return APIResponse.error(message="操作失败", status_code=500)



@wechat_bp.route("/qrcode", methods=["POST"])
@doc(summary="生成二维码", tags=["认证"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def generate_qrcode():
    """生成二维码（任务 7.1）
    
    生成用于微信扫码登录的二维码。
    
    Returns:
        JSON响应，包含二维码数据和场景ID
        
    Example Response:
        {
            "success": true,
            "data": {
                "scene_id": "1234567890123456",
                "qr_code": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
                "expires_at": 1234567890
            },
            "message": "二维码生成成功"
        }
    """
    try:
        logger.info("收到二维码生成请求")
        
        scene_id = qr_manager.generate_scene_id()
        
        expire_minutes = config.QR_CODE_EXPIRE_MINUTES
        success = qr_manager.create_qr_session(scene_id, expire_minutes)
        
        if not success:
            logger.error("创建二维码会话失败: scene_id=%s", scene_id)
            return APIResponse.error(
                message="二维码生成失败，请稍后重试",
                error_code="QR_SESSION_CREATE_FAILED",
                status_code=500
            )
        
        try:
            qr_code_data = qr_manager.generate_qr_code(scene_id)
        except Exception as e:
            logger.error("生成二维码图片失败: scene_id=%s, error=%s", scene_id, str(e), exc_info=True)
            return APIResponse.error(
                message="二维码生成失败",
                error_code="QR_CODE_GENERATE_FAILED",
                status_code=500
            )
        
        session_data = qr_manager.get_qr_session(scene_id)
        expires_at = session_data.get('expires_at') if session_data else None
        
        logger.info("二维码生成成功: scene_id=%s", scene_id)
        
        return APIResponse.success(
            data={
                "scene_id": scene_id,
                "qr_code": qr_code_data,
                "expires_at": expires_at
            },
            message="二维码生成成功"
        )
        
    except Exception as e:
        logger.error("二维码生成过程发生错误: error=%s", str(e), exc_info=True)
        return APIResponse.error(
            message="二维码生成失败",
            error_code="QR_CODE_ERROR",
            status_code=500
        )


@wechat_bp.route("/qrcode/status/<scene_id>", methods=["GET"])
@doc(summary="查询二维码状态", tags=["认证"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
def get_qrcode_status(scene_id: str):
    """查询二维码状态（任务 7.2）
    
    查询指定场景ID的二维码状态。
    
    Args:
        scene_id: 场景ID
        
    Returns:
        JSON响应，包含二维码状态和相关信息
        
    Example Response:
        {
            "success": true,
            "data": {
                "status": "waiting",  # waiting/scanned/confirmed/expired
                "scene_id": "1234567890123456",
                "expires_at": 1234567890,
                "user": {...},  # 仅在 confirmed 状态时返回
                "access_token": "...",  # 仅在 confirmed 状态时返回
                "refresh_token": "..."  # 仅在 confirmed 状态时返回
            },
            "message": "查询成功"
        }
    """
    try:
        logger.info("查询二维码状态: scene_id=%s", scene_id)
        
        session_data = qr_manager.get_qr_session(scene_id)
        
        if not session_data:
            logger.warning("二维码会话不存在或已过期: scene_id=%s", scene_id)
            return APIResponse.error(
                message="二维码不存在或已过期",
                error_code="QR_CODE_NOT_FOUND",
                status_code=404
            )
        
        status = session_data.get('status')
        expires_at = session_data.get('expires_at')
        
        response_data = {
            "status": status,
            "scene_id": scene_id,
            "expires_at": expires_at
        }
        
        if status == 'confirmed':
            user_id = session_data.get('user_id')
            openid = session_data.get('openid')
            
            if user_id and openid:
                user = user_service.get_by_id(user_id)
                
                if user:
                    user_roles = [role.name for role in user.roles] if hasattr(user, 'roles') else [user.role]
                    
                    access_token = auth_manager.generate_token(
                        user_id=user.id,
                        roles=user_roles,
                        token_type="access",
                        auth_type="wx",
                        openid=openid
                    )
                    refresh_token = auth_manager.generate_token(
                        user_id=user.id,
                        roles=user_roles,
                        token_type="refresh",
                        auth_type="wx",
                        openid=openid
                    )
                    
                    response_data['user'] = user.to_dict(include_sensitive=False)
                    response_data['access_token'] = access_token
                    response_data['refresh_token'] = refresh_token
                    
                    logger.info("二维码已确认，返回用户信息: user_id=%s", user_id)
        
        return APIResponse.success(
            data=response_data,
            message="查询成功"
        )
        
    except Exception as e:
        logger.error(
            "查询二维码状态失败: scene_id=%s, error=%s", scene_id, str(e),
            exc_info=True
        )
        return APIResponse.error(
            message="查询失败",
            error_code="QR_STATUS_QUERY_ERROR",
            status_code=500
        )


@wechat_bp.route("/qrcode/confirm", methods=["POST"])
@doc(summary="确认二维码", tags=["认证"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@transactional
def confirm_qrcode():
    """确认二维码（任务 7.3）
    
    微信端扫码后调用此接口确认登录。
    
    Request Body:
        {
            "scene_id": "1234567890123456",
            "openid": "oABC123...",
            "action": "scan" | "confirm"  # scan=已扫码，confirm=确认登录
        }
        
    Returns:
        JSON响应，包含操作结果
        
    Example Response:
        {
            "success": true,
            "data": {
                "status": "confirmed",
                "scene_id": "1234567890123456"
            },
            "message": "登录确认成功"
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return APIResponse.error(
                message="缺少请求数据",
                error_code="MISSING_REQUEST_DATA",
                status_code=400
            )
        
        scene_id = data.get('scene_id')
        openid = data.get('openid')
        action = data.get('action', 'confirm')  # 默认为 confirm
        
        if not scene_id or not openid:
            return APIResponse.error(
                message="缺少必需参数: scene_id 和 openid",
                error_code="MISSING_PARAMETERS",
                status_code=400
            )
        
        logger.info("收到二维码确认请求: scene_id=%s, openid=%s, action=%s", scene_id, _mask_openid(openid), action)
        
        session_data = qr_manager.get_qr_session(scene_id)
        
        if not session_data:
            logger.warning("二维码会话不存在或已过期: scene_id=%s", scene_id)
            return APIResponse.error(
                message="二维码不存在或已过期",
                error_code="QR_CODE_NOT_FOUND",
                status_code=404
            )
        
        current_status = session_data.get('status')
        
        if current_status == 'expired':
            return APIResponse.error(
                message="二维码已过期",
                error_code="QR_CODE_EXPIRED",
                status_code=400
            )
        
        if current_status == 'confirmed':
            return APIResponse.error(
                message="二维码已被确认",
                error_code="QR_CODE_ALREADY_CONFIRMED",
                status_code=400
            )
        
        user = user_service.get_by_openid(openid)
        
        if not user:
            logger.warning("微信用户不存在: openid=%s", _mask_openid(openid))
            return APIResponse.error(
                message="用户未授权访问该系统",
                error_code="USER_NOT_AUTHORIZED",
                status_code=403
            )
        
        if not user.is_active:
            logger.warning("微信用户已禁用: openid=%s", _mask_openid(openid))
            return APIResponse.error(
                message="用户已被禁用",
                error_code="USER_DISABLED",
                status_code=403
            )
        
        if action == 'scan':
            new_status = 'scanned'
            message = "扫码成功"
        else:
            new_status = 'confirmed'
            message = "登录确认成功"
        
        success = qr_manager.update_qr_session(
            scene_id=scene_id,
            status=new_status,
            openid=openid,
            user_id=user.id
        )
        
        if not success:
            logger.error("更新二维码会话状态失败: scene_id=%s", scene_id)
            return APIResponse.error(
                message="操作失败",
                error_code="QR_UPDATE_FAILED",
                status_code=500
            )
        
        if new_status == 'confirmed':
            client_ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                         or request.remote_addr or "")
            user_service.update_last_login(
                user.id, ip=client_ip, user_agent=request.headers.get("User-Agent"),
            )
        
        logger.info("二维码状态更新成功: scene_id=%s, status=%s, user_id=%s", scene_id, new_status, user.id)
        
        return APIResponse.success(
            data={
                "status": new_status,
                "scene_id": scene_id
            },
            message=message
        )
        
    except Exception as e:
        logger.error("确认二维码失败: error=%s", str(e), exc_info=True)
        return APIResponse.error(
            message="操作失败",
            error_code="QR_CONFIRM_ERROR",
            status_code=500
        )


@wechat_bp.route("/qrcode/auto-confirm", methods=["POST"])
@doc(summary="自动确认二维码（测试环境）", tags=["认证"], responses={200: "ApiResponse", 403: "ApiError"})
@login_required
@transactional
def auto_confirm_qrcode():
    """自动确认二维码（任务 7.4 - 仅测试环境）
    
    自动将二维码状态更新为 confirmed，用于测试环境快速测试。
    生产环境此端点将被禁用。
    
    Request Body:
        {
            "scene_id": "1234567890123456",
            "test_user_id": 1  # 可选，指定测试用户ID，默认使用第一个用户
        }
        
    Returns:
        JSON响应，包含操作结果和令牌
        
    Example Response:
        {
            "success": true,
            "data": {
                "status": "confirmed",
                "scene_id": "1234567890123456",
                "user": {...},
                "access_token": "...",
                "refresh_token": "..."
            },
            "message": "自动确认成功（测试环境）"
        }
    """
    try:
        if config.ENV not in ['development', 'testing']:
            logger.warning("尝试在生产环境使用自动确认功能: env=%s", config.ENV)
            return APIResponse.error(
                message="此功能仅在测试环境可用",
                error_code="FEATURE_NOT_AVAILABLE",
                status_code=403
            )
        
        data = request.get_json()
        
        if not data:
            return APIResponse.error(
                message="缺少请求数据",
                error_code="MISSING_REQUEST_DATA",
                status_code=400
            )
        
        scene_id = data.get('scene_id')
        test_user_id = data.get('test_user_id')
        
        if not scene_id:
            return APIResponse.error(
                message="缺少必需参数: scene_id",
                error_code="MISSING_PARAMETERS",
                status_code=400
            )
        
        logger.info("收到自动确认请求（测试环境）: scene_id=%s, test_user_id=%s", scene_id, test_user_id)
        
        session_data = qr_manager.get_qr_session(scene_id)
        
        if not session_data:
            logger.warning("二维码会话不存在或已过期: scene_id=%s", scene_id)
            return APIResponse.error(
                message="二维码不存在或已过期",
                error_code="QR_CODE_NOT_FOUND",
                status_code=404
            )
        
        if test_user_id:
            user = user_service.get_by_id(test_user_id)
        else:
            users, _ = user_service.get_paginated(page=1, per_page=1)
            user = users[0] if users else None
        
        if not user:
            logger.error("找不到测试用户")
            return APIResponse.error(
                message="找不到测试用户",
                error_code="TEST_USER_NOT_FOUND",
                status_code=404
            )
        
        test_openid = user.openid if hasattr(user, 'openid') and user.openid else f"test_openid_{user.id}"
        
        success = qr_manager.update_qr_session(
            scene_id=scene_id,
            status='confirmed',
            openid=test_openid,
            user_id=user.id
        )
        
        if not success:
            logger.error("更新二维码会话状态失败: scene_id=%s", scene_id)
            return APIResponse.error(
                message="自动确认失败",
                error_code="AUTO_CONFIRM_FAILED",
                status_code=500
            )
        
        access_token = auth_manager.generate_token(
            user_id=user.id,
            role=user.role,
            token_type="access",
            auth_type="wx",
            openid=test_openid
        )
        refresh_token = auth_manager.generate_token(
            user_id=user.id,
            role=user.role,
            token_type="refresh",
            auth_type="wx",
            openid=test_openid
        )
        
        client_ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                     or request.remote_addr or "")
        user_service.update_last_login(
            user.id, ip=client_ip, user_agent=request.headers.get("User-Agent"),
        )
        
        logger.info("自动确认成功（测试环境）: scene_id=%s, user_id=%s", scene_id, user.id)
        
        return APIResponse.success(
            data={
                "status": "confirmed",
                "scene_id": scene_id,
                "user": user.to_dict(include_sensitive=False),
                "access_token": access_token,
                "refresh_token": refresh_token
            },
            message="自动确认成功（测试环境）"
        )
        
    except Exception as e:
        logger.error("自动确认失败: error=%s", str(e), exc_info=True)
        return APIResponse.error(
            message="自动确认失败",
            error_code="AUTO_CONFIRM_ERROR",
            status_code=500
        )
