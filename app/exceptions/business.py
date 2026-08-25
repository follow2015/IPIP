# -*- coding: utf-8 -*-
"""
业务逻辑异常模块

定义业务逻辑相关的异常类。
"""
from typing import Any, Dict, Optional

from .base import BaseAppException


class BusinessLogicError(BaseAppException):
    """业务逻辑异常基类
    
    当业务规则验证失败或业务逻辑错误时抛出此类异常。
    """
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 400
    ):
        """初始化业务逻辑异常
        
        Args:
            message: 异常消息
            code: 异常代码
            details: 异常详情
            status_code: HTTP状态码
        """
        super().__init__(
            message=message,
            code=code or "BUSINESS_LOGIC_ERROR",
            details=details,
            status_code=status_code
        )


class UserNotFoundError(BusinessLogicError):
    """用户不存在异常
    
    当查找的用户不存在时抛出此异常。
    """
    
    def __init__(
        self,
        user_identifier: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化用户不存在异常
        
        Args:
            user_identifier: 用户标识符（ID、用户名等）
            message: 自定义异常消息
        """
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
    """用户重复异常
    
    当尝试创建已存在的用户时抛出此异常。
    """
    
    def __init__(
        self,
        field: str,
        value: str,
        message: Optional[str] = None
    ):
        """初始化用户重复异常
        
        Args:
            field: 重复的字段名（如username、email）
            value: 重复的值
            message: 自定义异常消息
        """
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
    """权限不足异常
    
    当用户没有足够权限执行操作时抛出此异常。
    """
    
    def __init__(
        self,
        required_permission: Optional[str] = None,
        resource: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化权限不足异常
        
        Args:
            required_permission: 所需权限
            resource: 相关资源
            message: 自定义异常消息
        """
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
    """无效操作异常
    
    当尝试执行无效或不允许的操作时抛出此异常。
    """
    
    def __init__(
        self,
        operation: str,
        reason: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化无效操作异常
        
        Args:
            operation: 操作名称
            reason: 无效的原因
            message: 自定义异常消息
        """
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
    """资源冲突异常
    
    当资源处于冲突状态时抛出此异常。
    """
    
    def __init__(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        conflict_reason: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化资源冲突异常
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
            conflict_reason: 冲突原因
            message: 自定义异常消息
        """
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
    """业务规则违反异常
    
    当违反业务规则时抛出此异常。
    """
    
    def __init__(
        self,
        rule_name: str,
        rule_description: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化业务规则违反异常
        
        Args:
            rule_name: 规则名称
            rule_description: 规则描述
            message: 自定义异常消息
        """
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
    """设备不支持异常
    
    当尝试对不支持的设备类型执行操作时抛出。
    """
    
    def __init__(self, device_type: str = "", message: Optional[str] = None):
        """初始化设备不支持异常"""
        if not message:
            message = f"不支持的设备类型：{device_type}" if device_type else "不支持的设备类型"
        super().__init__(message=message, code="DEVICE_NOT_SUPPORTED", details={"device_type": device_type})


class IPAlreadyBannedException(BusinessLogicError):
    """IP 已被封禁异常"""
    
    def __init__(self, ip_address: str = "", message: Optional[str] = None):
        """初始化 IP 已封禁异常"""
        if not message:
            message = f"IP {ip_address} 已处于封禁状态" if ip_address else "IP 已处于封禁状态"
        super().__init__(message=message, code="IP_ALREADY_BANNED", status_code=409)


class IPNotBannedException(BusinessLogicError):
    """IP 未被封禁异常"""
    
    def __init__(self, ip_address: str = "", message: Optional[str] = None):
        """初始化 IP 未封禁异常"""
        if not message:
            message = f"IP {ip_address} 未处于封禁状态" if ip_address else "IP 未处于封禁状态"
        super().__init__(message=message, code="IP_NOT_BANNED")


class NoCoreSwitch(BusinessLogicError):
    """无核心交换机异常"""
    
    def __init__(self, room_id: Optional[int] = None, message: Optional[str] = None):
        """初始化无核心交换机异常"""
        if not message:
            message = f"机房 {room_id} 无可用核心交换机" if room_id else "无可用核心交换机"
        super().__init__(message=message, code="NO_CORE_SWITCH")


class BanCommandFailed(BusinessLogicError):
    """封禁命令执行失败异常"""

    def __init__(self, reason: str = "", message: Optional[str] = None):
        """初始化封禁命令失败异常"""
        if not message:
            message = f"封禁命令执行失败：{reason}" if reason else "封禁命令执行失败"
        super().__init__(message=message, code="BAN_COMMAND_FAILED")


class BanConfigNotFoundError(BusinessLogicError):
    """解封时交换机配置不存在（路由/ARP条目已消失），视为已通过其他方式解封"""

    def __init__(self, reason: str = "", message: Optional[str] = None):
        if not message:
            message = f"交换机上未找到对应配置，该IP可能已通过其他方式解封：{reason}" if reason else "交换机上未找到对应配置，该IP可能已通过其他方式解封"
        super().__init__(message=message, code="BAN_CONFIG_NOT_FOUND")


class ServiceError(BusinessLogicError):
    """Service 层统一异常

    当 Service 层捕获底层异常（如 DataAccessError）后，
    转换为此异常抛出，避免上层直接暴露 data access 层异常细节。
    原始异常通过 __cause__ 链保留，便于日志追踪。
    """

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500,
    ):
        """初始化 Service 层异常

        Args:
            message: 异常消息
            code: 异常代码
            details: 异常详情
            status_code: HTTP状态码
        """
        super().__init__(
            message=message,
            code=code or "SERVICE_ERROR",
            details=details,
            status_code=status_code,
        )