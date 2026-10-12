# -*- coding: utf-8 -*-
"""
日志API

提供前端错误日志收集功能。
"""
from app.utils.logging import get_logger, sanitize_log_text
from flask import Blueprint, request
from app.api.base import APIResponse, api_exception_handler
from app.utils import rate_limit_api
from app.openapi.doc import doc
from app.services.auth import login_required, permission_required

logger = get_logger(__name__)

logs_bp = Blueprint("logs", __name__)


@logs_bp.route("/error", methods=["POST"])
@doc(summary="接收前端错误日志", tags=["用户"], responses={200: "ApiResponse", 401: "ApiError"}, request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/LogErrorReportRequest"}}}})
@login_required
@rate_limit_api
@api_exception_handler
def log_error():
    """接收前端错误日志

    接收并记录前端JavaScript错误。

    Request Body:
        {
            "message": "错误消息",
            "url": "发生错误的URL",
            "line": 行号,
            "column": 列号,
            "error": "错误堆栈",
            "userAgent": "用户代理",
            "timestamp": "时间戳"
        }

    Returns:
        JSON响应
    """
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
            "前端JavaScript错误: %s | URL: %s | 位置: %s:%s | 时间: %s | "
            "用户代理: %s | 堆栈: %s",
            sanitize_log_text(message),
            sanitize_log_text(url, 300),
            line, column,
            sanitize_log_text(timestamp, 60),
            sanitize_log_text(user_agent, 300),
            sanitize_log_text(error_stack),
        )
        
        return APIResponse.success(message="错误日志已记录")
        
    except Exception as e:  # noqa: BLE001 -- 路由处理器顶层兜底：Service 层异常类型不可枚举，必须转结构化错误响应；收窄会漏掉未预期异常，以未格式化 500 冒泡给前端
        logger.error(f"记录前端错误日志失败: {str(e)}")
        return APIResponse.error(message="记录日志失败", status_code=500)


@logs_bp.route("/info", methods=["POST"])
@doc(summary="接收前端信息日志", tags=["用户"], responses={200: "ApiResponse", 401: "ApiError"}, request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/LogInfoReportRequest"}}}})
@login_required
@rate_limit_api
@api_exception_handler
def log_info():
    """接收前端信息日志

    接收并记录前端信息日志。

    Request Body:
        {
            "message": "日志消息",
            "level": "日志级别",
            "data": "附加数据",
            "timestamp": "时间戳"
        }

    Returns:
        JSON响应
    """
    try:
        data = request.get_json()
        
        if not data:
            return APIResponse.error(message="请求数据格式错误", status_code=400)
        
        message = data.get("message", "")
        level = data.get("level", "info")
        log_data = data.get("data", "")
        timestamp = data.get("timestamp", "")
        
        log_args = (
            sanitize_log_text(message),
            sanitize_log_text(timestamp, 60),
            sanitize_log_text(log_data),
        )

        if level == "error":
            logger.error("前端日志: %s | 时间: %s | 数据: %s", *log_args)
        elif level == "warning":
            logger.warning("前端日志: %s | 时间: %s | 数据: %s", *log_args)
        else:
            logger.info("前端日志: %s | 时间: %s | 数据: %s", *log_args)
        
        return APIResponse.success(message="日志已记录")
        
    except Exception as e:  # noqa: BLE001 -- 路由处理器顶层兜底：Service 层异常类型不可枚举，必须转结构化错误响应；收窄会漏掉未预期异常，以未格式化 500 冒泡给前端
        logger.error(f"记录前端日志失败: {str(e)}")
        return APIResponse.error(message="记录日志失败", status_code=500)

@logs_bp.route("/stats", methods=["GET"])
@doc(summary="获取日志统计", tags=["用户"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
@permission_required("audit:view")
@rate_limit_api
@api_exception_handler
def get_log_stats():
    """获取日志统计
    
    Returns:
        JSON响应，包含日志统计信息
    """
    try:
        stats = {
            "total": 0,
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "today_count": 0
        }
        
        return APIResponse.success(data=stats, message="获取日志统计成功")
        
    except Exception as e:  # noqa: BLE001 -- 路由处理器顶层兜底：Service 层异常类型不可枚举，必须转结构化错误响应；收窄会漏掉未预期异常，以未格式化 500 冒泡给前端
        logger.error(f"获取日志统计失败: {str(e)}")
        return APIResponse.error(message="获取日志统计失败", status_code=500)
