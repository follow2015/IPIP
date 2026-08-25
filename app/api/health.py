# -*- coding: utf-8 -*-
"""
健康检查API

提供系统健康状态检查端点。
"""
from flask import Blueprint

from app.api.base import APIResponse
from app.openapi.doc import doc, public
from app.utils import error_statistics, health_checker
from app.utils.auth import login_required

health_bp = Blueprint("health", __name__)


@health_bp.route("", methods=["GET"])
@health_bp.route("/", methods=["GET"])
@public(summary="健康检查根端点", tags=["健康检查"], responses={200: "ApiResponse"})
def health_root():
    from datetime import datetime
    
    return APIResponse.success(
        data={
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'service': 'IPIP Management System'
        },
        message='系统运行正常'
    )


@health_bp.route("/check", methods=["GET"])
@public(summary="系统健康检查", tags=["健康检查"], responses={200: "ApiResponse", 503: "ApiError"})
def health_check():
    status = health_checker.check_all()

    http_status = 200 if status["overall_status"] == "healthy" else 503

    return APIResponse.success(data=status, message="健康检查完成", status_code=http_status)


@health_bp.route("/stats/errors", methods=["GET"])
@doc(summary="获取错误统计信息", tags=["健康检查"], responses={200: "ApiResponse", 401: "ApiError"})
@login_required
def error_stats():
    stats = error_statistics.get_statistics()

    return APIResponse.success(data=stats, message="错误统计获取成功")
