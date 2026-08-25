# -*- coding: utf-8 -*-
"""
错误报告API

接收前端错误报告并记录到日志文件。
"""
from flask import Blueprint, request, current_app
from app.openapi.doc import doc, public
from app.utils.auth import login_required
from app.utils.rate_limiting.decorators import rate_limit_api
from app.api.base import APIResponse
from app.utils.logging import get_logger
import json
import os
from datetime import datetime

errors_bp = Blueprint('errors', __name__)
logger = get_logger(__name__)


@errors_bp.route('/report', methods=['POST'])
@doc(summary='接收前端错误报告', tags=['健康检查'], responses={200: 'ApiResponse', 400: 'ApiError'})
@login_required
@rate_limit_api
def report_error():
    """接收前端错误报告
    
    Request Body:
        errors: 错误列表
        context: 错误上下文（可选）
    
    Returns:
        JSON响应，包含处理结果
    """
    try:
        data = request.get_json()
        
        if not data:
            return APIResponse.error(message="请求数据不能为空", status_code=400)
        
        log_dir = os.path.join(current_app.root_path, '..', 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_file = os.path.join(log_dir, 'frontend_errors.log')
        
        timestamp = datetime.now().isoformat()
        log_entry = {
            'timestamp': timestamp,
            'remote_addr': request.remote_addr,
            'report': data
        }
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            
        if data.get('errors'):
            for error in data.get('errors', []):
                logger.error(f"前端错误报告: {error}")

        return APIResponse.success(message="错误报告已接收")

    except Exception as e:
        logger.error(f"处理前端错误报告失败: {str(e)}")
        return APIResponse.error(message="服务器内部错误", status_code=500)
