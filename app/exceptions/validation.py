# -*- coding: utf-8 -*-
"""
数据验证异常模块

定义数据验证相关的异常类。
"""
from typing import Any, Dict, List, Optional

from .base import BaseAppException


class ValidationError(BaseAppException):
    
    def __init__(
        self,
        message: str = "数据验证失败",
        field: Optional[str] = None,
        errors: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None
    ):
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
    
    def __init__(
        self,
        message: str = "Schema验证失败",
        schema_errors: Optional[Dict[str, List[str]]] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        exception_details = details or {}
        if schema_errors:
            exception_details["schema_errors"] = schema_errors
            
        super().__init__(
            message=message,
            errors=schema_errors,
            details=exception_details
        )


class RequiredFieldError(ValidationError):
    
    def __init__(
        self,
        missing_fields: List[str],
        message: Optional[str] = None
    ):
        if not message:
            fields_str = "、".join(missing_fields)
            message = f"缺少必需字段：{fields_str}"
            
        super().__init__(
            message=message,
            details={"missing_fields": missing_fields}
        )


class InvalidFormatError(ValidationError):
    
    def __init__(
        self,
        field: str,
        expected_format: str,
        actual_value: Any = None,
        message: Optional[str] = None
    ):
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
    
    def __init__(
        self,
        field: str,
        value: Any,
        min_value: Optional[Any] = None,
        max_value: Optional[Any] = None,
        message: Optional[str] = None
    ):
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
