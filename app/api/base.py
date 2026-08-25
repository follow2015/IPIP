# -*- coding: utf-8 -*-
"""
API基础设施

提供统一的请求验证、响应格式化和错误处理机制。
"""
from functools import wraps
from typing import Any, Dict, Tuple

from flask import jsonify, request
from marshmallow import Schema
from marshmallow import ValidationError as MarshmallowValidationError

from app.exceptions.validation import ValidationError
from app.exceptions.handlers import handle_api_exception
from app.utils.logging import get_logger

logger = get_logger(__name__)


class APIResponse:
    """统一的API响应格式化器
    
    标准响应结构：
    {
        "success": true/false,
        "message": "操作成功",
        "data": { ... },          // 成功时可选
        "error_code": "10001",    // 失败时可选
        "timestamp": "2026-04-10T10:00:00Z"
    }
    """
    
    @staticmethod
    def success(data: Any = None, message: str = "操作成功", status_code: int = 200) -> Tuple[Dict, int]:
        """成功响应"""
        from datetime import datetime, timezone
        
        response = {
            'success': True,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if data is not None:
            response['data'] = data
            
        return jsonify(response), status_code
    
    @staticmethod
    def error(message: str, error_code: str = None, status_code: int = 400, details: Dict = None) -> Tuple[Dict, int]:
        """错误响应
        
        Args:
            message: 错误消息
            error_code: 错误代码（如 "10001"）
            status_code: HTTP状态码
            details: 错误详情（可选）
        """
        from datetime import datetime, timezone
        
        response = {
            'success': False,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if error_code:
            response['error_code'] = error_code
            
        if details:
            response['details'] = details
            
        return jsonify(response), status_code
    
    @staticmethod
    def paginated(data: list, page: int, per_page: int, total: int, message: str = "获取数据成功") -> Tuple[Dict, int]:
        """分页响应
        
        统一分页响应格式，将数据和分页信息嵌套在 data 字段中：
        {
            "success": true,
            "message": "获取数据成功",
            "data": {
                "data": [...数据列表...],
                "pagination": {
                    "page": 1,
                    "per_page": 20,
                    "total": 100,
                    "total_pages": 5
                }
            },
            "timestamp": "2026-04-10T10:00:00Z"
        }
        
        Args:
            data: 数据列表
            page: 当前页码
            per_page: 每页数量
            total: 总记录数
            message: 响应消息
            
        Returns:
            tuple: (响应字典, HTTP状态码)
        """
        from datetime import datetime, timezone
        
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0
        
        response = {
            'success': True,
            'message': message,
            'data': {
                'data': data,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'total_pages': total_pages
                }
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        return jsonify(response), 200


class RequestValidator:
    """统一的请求验证器"""
    
    @staticmethod
    def validate_json(schema: Schema, data: Dict = None) -> Dict:
        """验证JSON数据"""
        if data is None:
            data = request.get_json()
            
        if not data:
            raise ValidationError("请求数据不能为空")
            
        try:
            return schema.load(data)
        except MarshmallowValidationError as e:
            raise ValidationError(f"数据验证失败: {e.messages}")
    
    @staticmethod
    def validate_required_fields(data: Dict, required_fields: list) -> None:
        """验证必填字段"""
        missing_fields = []
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == '':
                missing_fields.append(field)
        
        if missing_fields:
            raise ValidationError(f"缺少必填字段: {', '.join(missing_fields)}")
    
    @staticmethod
    def validate_pagination_params() -> Tuple[int, int]:
        """验证分页参数"""
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        per_page = min(per_page, 100)
        
        if page < 1:
            page = 1
            
        if per_page < 1:
            per_page = 20
            
        return page, per_page


def api_exception_handler(f):
    """API异常处理装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValidationError as e:
            logger.warning("请求验证失败", extra={
                'validation_error': e.message,
                'function': f.__name__,
                'request_path': request.path,
                'request_method': request.method
            })
            return APIResponse.error(e.message, "VALIDATION_ERROR", 400)
        except Exception as e:
            try:
                from extensions import db
                db.session.rollback()
            except Exception:
                logger.warning("异常后 db.session.rollback() 失败", exc_info=True)
            logger.error("API处理异常", extra={
                'function': f.__name__,
                'request_path': request.path,
                'request_method': request.method,
                'error_type': type(e).__name__,
                'error_message': str(e)
            })
            return handle_api_exception(e)
    
    return decorated_function


def validate_request_json(schema: Schema):
    """请求JSON验证装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                validated_data = RequestValidator.validate_json(schema)
                return f(validated_data, *args, **kwargs)
            except ValidationError as e:
                return APIResponse.error(e.message, "VALIDATION_ERROR", 400)
        
        return decorated_function
    return decorator


class HTTPStatusCode:
    """HTTP状态码常量"""
    OK = 200
    CREATED = 201
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    INTERNAL_SERVER_ERROR = 500


class ErrorCode:
    """统一错误码体系"""
    VALIDATION_ERROR = "10001"
    AUTHENTICATION_ERROR = "10002"
    AUTHORIZATION_ERROR = "10003"
    NOT_FOUND = "10004"
    DUPLICATE_ERROR = "10005"
    IDEMPOTENCY_CONFLICT = "10006"
    RESOURCE_LOCKED = "10007"
    DEVICE_NOT_FOUND = "20001"
    DEVICE_U_CONFLICT = "20002"
    IP_NETWORK_NOT_FOUND = "30001"
    IP_ADDRESS_CONFLICT = "30002"
    SWITCH_CONN_FAILED = "40001"
    SWITCH_CMD_FAILED = "40002"