# -*- coding: utf-8 -*-
"""
数据验证异常模块

定义数据验证相关的异常类。
"""
from typing import Any, Dict, List, Optional

from .base import BaseAppException


class ValidationError(BaseAppException):
    """数据验证异常
    
    当输入数据不符合验证规则时抛出此异常。
    """
    
    def __init__(
        self,
        message: str = "数据验证失败",
        field: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """初始化验证异常
        
        Args:
            message: 异常消息
            field: 验证失败的字段名
            errors: 详细的验证错误信息
            details: 额外的异常详情
        """
        exception_details = details or {}
        if field:
            exception_details["field"] = field
        if errors:
            exception_details["errors"] = errors
            
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details=exception_details,
            status_code=400
        )
        
        self.field = field
        self.errors = errors or {}


class SchemaValidationError(ValidationError):
    """Schema验证异常
    
    当使用Marshmallow等Schema验证失败时抛出此异常。
    """
    
    def __init__(
        self,
        message: str = "Schema验证失败",
        schema_errors: Optional[Dict[str, List[str]]] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """初始化Schema验证异常
        
        Args:
            message: 异常消息
            schema_errors: Schema验证错误详情
            details: 额外的异常详情
        """
        exception_details = details or {}
        if schema_errors:
            exception_details["schema_errors"] = schema_errors
            
        super().__init__(
            message=message,
            errors=schema_errors,
            details=exception_details
        )


class RequiredFieldError(ValidationError):
    """必需字段缺失异常
    
    当必需的字段缺失时抛出此异常。
    """
    
    def __init__(
        self,
        missing_fields: List[str],
        message: Optional[str] = None
    ):
        """初始化必需字段异常
        
        Args:
            missing_fields: 缺失的字段列表
            message: 自定义异常消息
        """
        if not message:
            fields_str = "、".join(missing_fields)
            message = f"缺少必需字段：{fields_str}"
            
        super().__init__(
            message=message,
            details={"missing_fields": missing_fields}
        )


class InvalidFormatError(ValidationError):
    """格式错误异常
    
    当数据格式不正确时抛出此异常。
    """
    
    def __init__(
        self,
        field: str,
        expected_format: str,
        actual_value: Any = None,
        message: Optional[str] = None
    ):
        """初始化格式错误异常
        
        Args:
            field: 字段名
            expected_format: 期望的格式
            actual_value: 实际值
            message: 自定义异常消息
        """
        if not message:
            message = f"字段 {field} 格式不正确，期望格式：{expected_format}"
            
        details = {
            "expected_format": expected_format
        }
        if actual_value is not None:
            details["actual_value"] = str(actual_value)
            
        super().__init__(
            message=message,
            field=field,
            details=details
        )


class ValueRangeError(ValidationError):
    """数值范围错误异常
    
    当数值不在允许范围内时抛出此异常。
    """
    
    def __init__(
        self,
        field: str,
        value: Any,
        min_value: Optional[Any] = None,
        max_value: Optional[Any] = None,
        message: Optional[str] = None
    ):
        """初始化数值范围错误异常
        
        Args:
            field: 字段名
            value: 实际值
            min_value: 最小值
            max_value: 最大值
            message: 自定义异常消息
        """
        if not message:
            if min_value is not None and max_value is not None:
                message = f"字段 {field} 的值必须在 {min_value} 到 {max_value} 之间"
            elif min_value is not None:
                message = f"字段 {field} 的值不能小于 {min_value}"
            elif max_value is not None:
                message = f"字段 {field} 的值不能大于 {max_value}"
            else:
                message = f"字段 {field} 的值超出允许范围"
                
        details = {"value": value}
        if min_value is not None:
            details["min_value"] = min_value
        if max_value is not None:
            details["max_value"] = max_value
            
        super().__init__(
            message=message,
            field=field,
            details=details
        )