# -*- coding: utf-8 -*-
"""
日志API

提供前端错误日志收集功能。
"""
from app.utils.logging import get_logger
from flask import Blueprint, request
from app.api.base import APIResponse, api_exception_handler
from app.utils import rate_limit_api
from app.openapi.doc import doc, public
from app.utils.auth import login_required

logger = get_logger(__name__)

logs_bp = Blueprint("logs", __name__)


@logs_bp.route("/error", methods=["POST"])
@doc(summary="接收前端错误日志", tags=["用户"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@rate_limit_api
@api_exception_handler
def log_error():
    try:
        data = request.get_json()
        
        if not data:
            return APIResponse.error(message="请求数据格式错误", status_code=400)
        
        message = data.get("message", "未知错误")
        url = data.get("url", "未知URL")
        line = data.get("line", 0)
        column = data.get("column", 0)
        error_stack = data.get("error", "")
        user_agent = data.get("userAgent", "")
        timestamp = data.get("timestamp", "")
        
        logger.error(
            f"前端JavaScript错误: {message} | "
            f"URL: {url} | "
            f"位置: {line}:{column} | "
            f"时间: {timestamp} | "
            f"用户代理: {user_agent} | "
            f"堆栈: {error_stack}"
        )
        
        return APIResponse.success(message="错误日志已记录")
        
    except Exception as e:
        logger.error(f"记录前端错误日志失败: {str(e)}")
        return APIResponse.error(message="记录日志失败", status_code=500)


@logs_bp.route("/info", methods=["POST"])
@doc(summary="接收前端信息日志", tags=["用户"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@rate_limit_api
@api_exception_handler
def log_info():
    try:
        data = request.get_json()
        
        if not data:
            return APIResponse.error(message="请求数据格式错误", status_code=400)
        
        message = data.get("message", "")
        level = data.get("level", "info")
        log_data = data.get("data", "")
        timestamp = data.get("timestamp", "")
        
        log_message = f"前端日志: {message} | 时间: {timestamp} | 数据: {log_data}"
        
        if level == "error":
            logger.error(log_message)
        elif level == "warning":
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        return APIResponse.success(message="日志已记录")
        
    except Exception as e:
        logger.error(f"记录前端日志失败: {str(e)}")
        return APIResponse.error(message="记录日志失败", status_code=500)

@logs_bp.route("/", methods=["GET"])
@public(summary="获取最近日志", tags=["用户"], responses={200: "ApiResponse"})
@rate_limit_api
@api_exception_handler
def get_logs():
    try:
        limit = request.args.get("limit", 10, type=int)
        level = request.args.get("level", type=str)
        
        limit = min(limit, 100)
        
        logs = []
        
        return APIResponse.success(data=logs, message="获取日志成功")
        
    except Exception as e:
        logger.error(f"获取日志失败: {str(e)}")
        return APIResponse.error(message="获取日志失败", status_code=500)


@logs_bp.route("/stats", methods=["GET"])
@public(summary="获取日志统计", tags=["用户"], responses={200: "ApiResponse"})
@rate_limit_api
@api_exception_handler
def get_log_stats():
    try:
        stats = {
            "total": 0,
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "today_count": 0
        }
        
        return APIResponse.success(data=stats, message="获取日志统计成功")
        
    except Exception as e:
        logger.error(f"获取日志统计失败: {str(e)}")
        return APIResponse.error(message="获取日志统计失败", status_code=500)
