# -*- coding: utf-8 -*-
"""
API路由模块 - 精简版

所有业务逻辑已迁移到独立模块：
- 设备管理 → app/api/device.py（含 check-node-position）
- 机柜管理 → app/api/cabinet.py
- 客户管理 → app/api/customer.py
- 交换机管理 → app/api/switch.py
- 扫描功能 → app/api/scan.py
- 统计功能 → app/api/dashboard.py
- 密码管理 → app/api/user.py
- 网络详情 → app/api/network.py（含 network_detail）

本文件仅保留蓝图注册和错误处理。
"""
from flask import Blueprint
from app.api.base import APIResponse, ErrorCode
from app.utils.logging import get_logger

logger = get_logger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')



@api_bp.errorhandler(404)
def not_found(error):
    """404错误处理"""
    return APIResponse.error(message='接口不存在', error_code=ErrorCode.NOT_FOUND, status_code=404)


@api_bp.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    return APIResponse.error(message='服务器内部错误', status_code=500)
