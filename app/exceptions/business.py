# -*- coding: utf-8 -*-
"""
业务逻辑异常模块

定义业务逻辑相关的异常类。
"""
from typing import Any, Dict, Optional

from .base import BaseAppException


class BusinessLogicError(BaseAppException):
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 400
    ):
        super().__init__(
            message=message,
            code=code or "BUSINESS_LOGIC_ERROR",
            details=details,
            status_code=status_code
        )


class UserNotFoundError(BusinessLogicError):
    
    def __init__(
        self,
        user_identifier: Optional[str] = None,
        message: Optional[str] = None
    ):
        if not message:
            if user_identifier:
                message = f"用户不存在：{user_identifier}"
            else:
                message = "用户不存在"
                
        details = {}
        if user_identifier:
            details["user_identifier"] = user_identifier
            
        super().__init__(
            message=message,
            code="USER_NOT_FOUND",
            details=details,
            status_code=404
        )


class DuplicateUserError(BusinessLogicError):
    
    def __init__(
        self,
        field: str,
        value: str,
        message: Optional[str] = None
    ):
        if not message:
            field_names = {
                "username": "用户名",
                "email": "邮箱",
                "phone": "手机号"
            }
            field_display = field_names.get(field, field)
            message = f"{field_display}已存在"
            
        super().__init__(
            message=message,
            code="DUPLICATE_USER",
            details={"field": field},
            status_code=409
        )


class InsufficientPermissionError(BusinessLogicError):
    
    def __init__(
        self,
        required_permission: Optional[str] = None,
        resource: Optional[str] = None,
        message: Optional[str] = None
    ):
        if not message:
            if required_permission and resource:
                message = f"权限不足，需要 {required_permission} 权限访问 {resource}"
            elif required_permission:
                message = f"权限不足，需要 {required_permission} 权限"
            else:
                message = "权限不足"
                
        details = {}
        if required_permission:
            details["required_permission"] = required_permission
        if resource:
            details["resource"] = resource
            
        super().__init__(
            message=message,
            code="INSUFFICIENT_PERMISSION",
            details=details,
            status_code=403
        )


class InvalidOperationError(BusinessLogicError):
    
    def __init__(
        self,
        operation: str,
        reason: Optional[str] = None,
        message: Optional[str] = None
    ):
        if not message:
            if reason:
                message = f"无效操作 {operation}：{reason}"
            else:
                message = f"无效操作：{operation}"
                
        details = {"operation": operation}
        if reason:
            details["reason"] = reason
            
        super().__init__(
            message=message,
            code="INVALID_OPERATION",
            details=details
        )


class ResourceConflictError(BusinessLogicError):
    
    def __init__(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        conflict_reason: Optional[str] = None,
        message: Optional[str] = None
    ):
        if not message:
            if resource_id and conflict_reason:
                message = f"{resource_type} {resource_id} 冲突：{conflict_reason}"
            elif resource_id:
                message = f"{resource_type} {resource_id} 存在冲突"
            else:
                message = f"{resource_type} 存在冲突"
                
        details = {"resource_type": resource_type}
        if resource_id:
            details["resource_id"] = resource_id
        if conflict_reason:
            details["conflict_reason"] = conflict_reason
            
        super().__init__(
            message=message,
            code="RESOURCE_CONFLICT",
            details=details,
            status_code=409
        )


class BusinessRuleViolationError(BusinessLogicError):
    
    def __init__(
        self,
        rule_name: str,
        rule_description: Optional[str] = None,
        message: Optional[str] = None
    ):
        if not message:
            if rule_description:
                message = f"违反业务规则 {rule_name}：{rule_description}"
            else:
                message = f"违反业务规则：{rule_name}"
                
        details = {"rule_name": rule_name}
        if rule_description:
            details["rule_description"] = rule_description
            
        super().__init__(
            message=message,
            code="BUSINESS_RULE_VIOLATION",
            details=details
        )


class DeviceNotSupported(BusinessLogicError):
    
    def __init__(self, device_type: str = "", message: Optional[str] = None):
        if not message:
            message = f"不支持的设备类型：{device_type}" if device_type else "不支持的设备类型"
        super().__init__(message=message, code="DEVICE_NOT_SUPPORTED", details={"device_type": device_type})


class IPAlreadyBannedException(BusinessLogicError):
    
    def __init__(self, ip_address: str = "", message: Optional[str] = None):
        if not message:
            message = f"IP {ip_address} 已处于封禁状态" if ip_address else "IP 已处于封禁状态"
        super().__init__(message=message, code="IP_ALREADY_BANNED", status_code=409)


class IPNotBannedException(BusinessLogicError):
    
    def __init__(self, ip_address: str = "", message: Optional[str] = None):
        if not message:
            message = f"IP {ip_address} 未处于封禁状态" if ip_address else "IP 未处于封禁状态"
        super().__init__(message=message, code="IP_NOT_BANNED")


class NoCoreSwitch(BusinessLogicError):
    
    def __init__(self, room_id: Optional[int] = None, message: Optional[str] = None):
        if not message:
            message = f"机房 {room_id} 无可用核心交换机" if room_id else "无可用核心交换机"
        super().__init__(message=message, code="NO_CORE_SWITCH")


class BanCommandFailed(BusinessLogicError):

    def __init__(self, reason: str = "", message: Optional[str] = None):
        if not message:
            message = f"封禁命令执行失败：{reason}" if reason else "封禁命令执行失败"
        super().__init__(message=message, code="BAN_COMMAND_FAILED")


class BanConfigNotFoundError(BusinessLogicError):

    def __init__(self, reason: str = "", message: Optional[str] = None):
        if not message:
            message = f"交换机上未找到对应配置，该IP可能已通过其他方式解封：{reason}" if reason else "交换机上未找到对应配置，该IP可能已通过其他方式解封"
        super().__init__(message=message, code="BAN_CONFIG_NOT_FOUND")


class ServiceError(BusinessLogicError):

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500,
    ):
        super().__init__(
            message=message,
            code=code or "SERVICE_ERROR",
            details=details,
            status_code=status_code,
        )
