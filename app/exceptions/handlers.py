# -*- coding: utf-8 -*-
"""
统一错误处理器模块

提供Flask应用的统一错误处理机制。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, Tuple

from flask import Flask, jsonify
from marshmallow import ValidationError as MarshmallowValidationError
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from werkzeug.exceptions import HTTPException

from .base import BaseAppException
from .business import BusinessLogicError
from .data_access import DataAccessError, DataIntegrityError
from .system import SystemError
from .validation import ValidationError, SchemaValidationError

logger = get_logger(__name__)


def _api_response():
    """延迟导入 APIResponse，避免与 app.api.base 的循环依赖。"""
    from app.api.base import APIResponse
    return APIResponse


def register_error_handlers(app: Flask) -> None:
    """注册统一的错误处理器
    
    Args:
        app: Flask应用实例
    """
    
    @app.errorhandler(BaseAppException)
    def handle_base_app_exception(error: BaseAppException) -> Tuple[Dict[str, Any], int]:
        """处理应用基础异常
        
        Args:
            error: 应用基础异常
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        if isinstance(error, (ValidationError, BusinessLogicError)):
            logger.warning(f"业务异常: {error.code} - {error.message}")
        elif isinstance(error, (DataAccessError, SystemError)):
            logger.error(f"系统异常: {error.code} - {error.message}", exc_info=True)
        else:
            logger.info(f"应用异常: {error.code} - {error.message}")
        
        return _api_response().error(
            message=error.message,
            error_code=error.code,
            details=[error.details] if error.details else None,
            status_code=error.status_code
        )
    
    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError) -> Tuple[Dict[str, Any], int]:
        """处理验证错误
        
        Args:
            error: 验证错误
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.warning(f"验证错误: {error.message}")
        
        details = []
        if error.field:
            details.append({"field": error.field, "errors": error.errors})
        elif error.errors:
            details.append({"errors": error.errors})
            
        return _api_response().error(
            message=error.message,
            error_code=error.code,
            details=details if details else None,
            status_code=error.status_code
        )
    
    @app.errorhandler(MarshmallowValidationError)
    def handle_marshmallow_error(error: MarshmallowValidationError) -> Tuple[Dict[str, Any], int]:
        """处理Marshmallow验证错误
        
        Args:
            error: Marshmallow验证错误
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.warning(f"Schema验证错误: {error.messages}")
        
        schema_error = SchemaValidationError(
            message="数据验证失败",
            schema_errors=error.messages
        )
        
        return _api_response().error(
            message=schema_error.message,
            error_code=schema_error.code,
            details=[schema_error.details],
            status_code=schema_error.status_code
        )
    
    @app.errorhandler(SQLAlchemyError)
    def handle_sqlalchemy_error(error: SQLAlchemyError) -> Tuple[Dict[str, Any], int]:
        """处理SQLAlchemy错误
        
        Args:
            error: SQLAlchemy错误
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.error(f"SQLAlchemy错误: {str(error)}", exc_info=True)
        
        if isinstance(error, IntegrityError):
            data_error = DataIntegrityError(
                constraint_type="UNKNOWN",
                message="数据完整性约束违反"
            )
            return _api_response().error(
                message=data_error.message,
                error_code=data_error.code,
                details=[data_error.details],
                status_code=data_error.status_code
            )
        else:
            data_error = DataAccessError(
                message="数据库操作失败"
            )
            return _api_response().error(
                message=data_error.message,
                error_code=data_error.code,
                status_code=data_error.status_code
            )
    
    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException) -> Tuple[Dict[str, Any], int]:
        """处理HTTP异常
        
        Args:
            error: HTTP异常
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.warning(f"HTTP异常: {error.code} - {error.description}")
        
        return _api_response().error(
            message=error.description or "请求错误",
            error_code=f"HTTP_{error.code}",
            status_code=error.code
        )
    
    @app.errorhandler(400)
    def handle_bad_request(error) -> Tuple[Dict[str, Any], int]:
        """处理400错误
        
        Args:
            error: 错误对象
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.warning("400 错误请求")
        return _api_response().error(
            message="错误的请求",
            error_code="BAD_REQUEST",
            status_code=400
        )
    
    @app.errorhandler(401)
    def handle_unauthorized(error) -> Tuple[Dict[str, Any], int]:
        """处理401错误
        
        Args:
            error: 错误对象
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.warning("401 未授权")
        return _api_response().error(
            message="未授权，请先登录",
            error_code="UNAUTHORIZED",
            status_code=401
        )
    
    @app.errorhandler(403)
    def handle_forbidden(error) -> Tuple[Dict[str, Any], int]:
        """处理403错误
        
        Args:
            error: 错误对象
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.warning("403 禁止访问")
        return _api_response().error(
            message="权限不足",
            error_code="FORBIDDEN",
            status_code=403
        )
    
    @app.errorhandler(404)
    def handle_not_found(error) -> Tuple[Dict[str, Any], int]:
        """处理404错误
        
        Args:
            error: 错误对象
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.warning("404 资源不存在")
        return _api_response().error(
            message="资源不存在",
            error_code="NOT_FOUND",
            status_code=404
        )
    
    @app.errorhandler(405)
    def handle_method_not_allowed(error) -> Tuple[Dict[str, Any], int]:
        """处理405错误
        
        Args:
            error: 错误对象
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.warning("405 方法不允许")
        return _api_response().error(
            message="方法不允许",
            error_code="METHOD_NOT_ALLOWED",
            status_code=405
        )
    
    @app.errorhandler(429)
    def handle_too_many_requests(error) -> Tuple[Dict[str, Any], int]:
        """处理429错误
        
        Args:
            error: 错误对象
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.warning("429 请求过多")
        return _api_response().error(
            message="请求过于频繁，请稍后再试",
            error_code="TOO_MANY_REQUESTS",
            status_code=429
        )
    
    @app.errorhandler(500)
    def handle_internal_server_error(error) -> Tuple[Dict[str, Any], int]:
        """处理500错误
        
        Args:
            error: 错误对象
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.error("500 服务器内部错误", exc_info=True)
        return _api_response().error(
            message="服务器内部错误",
            error_code="INTERNAL_SERVER_ERROR",
            status_code=500
        )
    
    @app.errorhandler(503)
    def handle_service_unavailable(error) -> Tuple[Dict[str, Any], int]:
        """处理503错误
        
        Args:
            error: 错误对象
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.error("503 服务不可用", exc_info=True)
        return _api_response().error(
            message="服务暂时不可用",
            error_code="SERVICE_UNAVAILABLE",
            status_code=503
        )
    
    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception) -> Tuple[Dict[str, Any], int]:
        """处理未预期的错误
        
        Args:
            error: 错误对象
            
        Returns:
            Tuple: (响应数据, HTTP状态码)
        """
        logger.error(f"未预期的错误: {str(error)}", exc_info=True)
        
        system_error = SystemError(
            message="服务器内部错误",
        )
        
        return _api_response().error(
            message=system_error.message,
            error_code=system_error.code,
            status_code=system_error.status_code
        )
    
    logger.info("统一错误处理器注册完成")


def handle_api_exception(error: Exception) -> Tuple[Dict[str, Any], int]:
    """处理API异常的通用函数
    
    Args:
        error: 异常对象
        
    Returns:
        Tuple: (响应数据, HTTP状态码)
    """
    if isinstance(error, BaseAppException):
        logger.warning(f"API异常: {error.code} - {error.message}")
        return _api_response().error(
            message=error.message,
            error_code=error.code,
            details=[error.details] if error.details else None,
            status_code=error.status_code
        )
    
    if isinstance(error, SQLAlchemyError):
        logger.error(f"数据库异常: {str(error)}", exc_info=True)
        if isinstance(error, IntegrityError):
            data_error = DataIntegrityError(
                constraint_type="UNKNOWN",
                message="数据完整性约束违反"
            )
            return _api_response().error(
                message=data_error.message,
                error_code=data_error.code,
                details=[data_error.details],
                status_code=data_error.status_code
            )
        else:
            data_error = DataAccessError(message="数据库操作失败")
            return _api_response().error(
                message=data_error.message,
                error_code=data_error.code,
                status_code=data_error.status_code
            )
    
    if isinstance(error, HTTPException):
        logger.warning(f"HTTP异常: {error.code} - {error.description}")
        return _api_response().error(
            message=error.description or "请求错误",
            error_code=f"HTTP_{error.code}",
            status_code=error.code
        )
    
    logger.error(f"未知API异常: {str(error)}", exc_info=True)
    system_error = SystemError(
        message="服务器内部错误",
    )
    
    return _api_response().error(
        message=system_error.message,
        error_code=system_error.code,
        status_code=system_error.status_code
    )