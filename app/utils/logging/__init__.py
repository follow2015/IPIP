# -*- coding: utf-8 -*-
"""
统一日志记录模块

提供统一的日志记录接口、配置和管理功能。

主要组件:
- UnifiedLogManager: 统一日志管理器
- UnifiedLogger: 统一日志记录器
- JSONFormatter: JSON格式化器
- StandardFormatter: 标准格式化器
- LoggingConfig: 日志配置类

使用示例:
    # 基本使用
    from app.utils.logging import get_logger
    
    logger = get_logger(__name__)
    logger.info("这是一条信息日志")
    logger.error("这是一条错误日志", extra={'user_id': 123})
    
    # 结构化日志
    logger.log_event("user_login", {"user_id": 123, "ip": "192.168.1.1"})
    logger.log_request({
        "method": "POST",
        "url": "/api/users",
        "status_code": 201,
        "duration": 0.123
    })
    
    # 使用装饰器
    from app.utils.logging.decorators import log_function_call, log_api_endpoint
    
    @log_function_call(log_execution_time=True)
    def my_function():
        pass
    
    @log_api_endpoint(log_request_data=True)
    def api_endpoint():
        pass
"""

from .config import JSONFormatter, LoggingConfig, StandardFormatter
from .decorators import (
    log_api_endpoint,
    log_authentication_attempt,
    log_cache_operation,
    log_database_operation,
    log_function_call,
    log_performance_critical,
    log_security_event,
)
from .manager import UnifiedLogManager, UnifiedLogger, get_logger, log_manager

__all__ = [
    'UnifiedLogManager',
    'UnifiedLogger',
    'log_manager',
    'get_logger',
    
    'LoggingConfig',
    'JSONFormatter',
    'StandardFormatter',
    
    'log_function_call',
    'log_database_operation',
    'log_cache_operation',
    'log_api_endpoint',
    'log_authentication_attempt',
    'log_security_event',
    'log_performance_critical',
]

__version__ = '1.0.0'
__author__ = 'IP Management System'
__description__ = '统一日志记录模块'
