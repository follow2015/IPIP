# -*- coding: utf-8 -*-
"""
系统异常模块

定义系统级异常类。
"""
from typing import Any, Dict, Optional

from .base import BaseAppException


class SystemError(BaseAppException):
    """系统异常基类
    
    当系统级错误发生时抛出此类异常。
    """
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500
    ):
        """初始化系统异常
        
        Args:
            message: 异常消息
            code: 异常代码
            details: 异常详情
            status_code: HTTP状态码
        """
        super().__init__(
            message=message,
            code=code or "SYSTEM_ERROR",
            details=details,
            status_code=status_code
        )


class CacheError(SystemError):
    """缓存异常
    
    当缓存操作失败时抛出此异常。
    """
    
    def __init__(
        self,
        operation: str,
        cache_key: Optional[str] = None,
        cache_backend: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化缓存异常
        
        Args:
            operation: 缓存操作（GET、SET、DELETE等）
            cache_key: 缓存键
            cache_backend: 缓存后端（Redis、Memory等）
            message: 自定义异常消息
        """
        if not message:
            if cache_key and cache_backend:
                message = f"缓存{operation}操作失败：{cache_backend} 后端，键 {cache_key}"
            elif cache_key:
                message = f"缓存{operation}操作失败：键 {cache_key}"
            elif cache_backend:
                message = f"缓存{operation}操作失败：{cache_backend} 后端"
            else:
                message = f"缓存{operation}操作失败"
                
        details = {"operation": operation}
        if cache_key:
            details["cache_key"] = cache_key
        if cache_backend:
            details["cache_backend"] = cache_backend
            
        super().__init__(
            message=message,
            code="CACHE_ERROR",
            details=details
        )


class ConfigurationError(SystemError):
    """配置异常
    
    当配置错误或缺失时抛出此异常。
    """
    
    def __init__(
        self,
        config_key: Optional[str] = None,
        config_file: Optional[str] = None,
        reason: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化配置异常
        
        Args:
            config_key: 配置键
            config_file: 配置文件
            reason: 错误原因
            message: 自定义异常消息
        """
        if not message:
            if config_key and reason:
                message = f"配置错误：{config_key} - {reason}"
            elif config_key:
                message = f"配置错误：{config_key}"
            elif config_file:
                message = f"配置文件错误：{config_file}"
            else:
                message = "配置错误"
                
        details = {}
        if config_key:
            details["config_key"] = config_key
        if config_file:
            details["config_file"] = config_file
        if reason:
            details["reason"] = reason
            
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            details=details
        )


class ExternalServiceError(SystemError):
    """外部服务异常
    
    当外部服务调用失败时抛出此异常。
    """
    
    def __init__(
        self,
        service_name: str,
        operation: Optional[str] = None,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化外部服务异常
        
        Args:
            service_name: 服务名称
            operation: 操作名称
            status_code: HTTP状态码
            response_body: 响应体
            message: 自定义异常消息
        """
        if not message:
            if operation and status_code:
                message = f"外部服务 {service_name} 调用失败：{operation}，状态码 {status_code}"
            elif operation:
                message = f"外部服务 {service_name} 调用失败：{operation}"
            else:
                message = f"外部服务 {service_name} 调用失败"
                
        details = {"service_name": service_name}
        if operation:
            details["operation"] = operation
        if status_code:
            details["status_code"] = status_code
        if response_body:
            details["response_body"] = response_body[:500] + "..." if len(response_body) > 500 else response_body
            
        super().__init__(
            message=message,
            code="EXTERNAL_SERVICE_ERROR",
            details=details
        )


class FileSystemError(SystemError):
    """文件系统异常
    
    当文件系统操作失败时抛出此异常。
    """
    
    def __init__(
        self,
        operation: str,
        file_path: Optional[str] = None,
        reason: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化文件系统异常
        
        Args:
            operation: 文件操作（READ、WRITE、DELETE等）
            file_path: 文件路径
            reason: 失败原因
            message: 自定义异常消息
        """
        if not message:
            if file_path and reason:
                message = f"文件{operation}操作失败：{file_path} - {reason}"
            elif file_path:
                message = f"文件{operation}操作失败：{file_path}"
            else:
                message = f"文件{operation}操作失败"
                
        details = {"operation": operation}
        if file_path:
            details["file_path"] = file_path
        if reason:
            details["reason"] = reason
            
        super().__init__(
            message=message,
            code="FILE_SYSTEM_ERROR",
            details=details
        )


class NetworkError(SystemError):
    """网络异常
    
    当网络操作失败时抛出此异常。
    """
    
    def __init__(
        self,
        operation: str,
        endpoint: Optional[str] = None,
        timeout: Optional[int] = None,
        reason: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化网络异常
        
        Args:
            operation: 网络操作（REQUEST、CONNECT等）
            endpoint: 端点地址
            timeout: 超时时间
            reason: 失败原因
            message: 自定义异常消息
        """
        if not message:
            if endpoint and reason:
                message = f"网络{operation}操作失败：{endpoint} - {reason}"
            elif endpoint:
                message = f"网络{operation}操作失败：{endpoint}"
            else:
                message = f"网络{operation}操作失败"
                
        details = {"operation": operation}
        if endpoint:
            details["endpoint"] = endpoint
        if timeout:
            details["timeout"] = timeout
        if reason:
            details["reason"] = reason
            
        super().__init__(
            message=message,
            code="NETWORK_ERROR",
            details=details
        )


class ResourceExhaustionError(SystemError):
    """资源耗尽异常
    
    当系统资源耗尽时抛出此异常。
    """
    
    def __init__(
        self,
        resource_type: str,
        current_usage: Optional[str] = None,
        limit: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化资源耗尽异常
        
        Args:
            resource_type: 资源类型（MEMORY、DISK、CONNECTION等）
            current_usage: 当前使用量
            limit: 限制值
            message: 自定义异常消息
        """
        if not message:
            resource_names = {
                "MEMORY": "内存",
                "DISK": "磁盘空间",
                "CONNECTION": "连接数",
                "CPU": "CPU"
            }
            resource_display = resource_names.get(resource_type, resource_type)
            
            if current_usage and limit:
                message = f"{resource_display}资源耗尽：当前使用 {current_usage}，限制 {limit}"
            else:
                message = f"{resource_display}资源耗尽"
                
        details = {"resource_type": resource_type}
        if current_usage:
            details["current_usage"] = current_usage
        if limit:
            details["limit"] = limit
            
        super().__init__(
            message=message,
            code="RESOURCE_EXHAUSTION_ERROR",
            details=details,
            status_code=503
        )


class SSHConnectionError(NetworkError):
    """SSH 连接异常
    
    当 SSH 连接失败时抛出此异常。
    """
    
    def __init__(self, host: str = "", reason: str = "", message: Optional[str] = None):
        """初始化 SSH 连接异常"""
        if not message:
            if host and reason:
                message = f"SSH 连接失败 {host}：{reason}"
            elif host:
                message = f"SSH 连接失败：{host}"
            else:
                message = "SSH 连接失败"
        super().__init__(operation="SSH_CONNECT", endpoint=host, reason=reason, message=message)


class SwitchConfigError(SystemError):
    """交换机配置异常
    
    当交换机配置操作失败时抛出此异常。
    """
    
    def __init__(self, switch_id: Optional[int] = None, reason: str = "", message: Optional[str] = None):
        """初始化交换机配置异常"""
        if not message:
            if switch_id and reason:
                message = f"交换机 {switch_id} 配置失败：{reason}"
            elif reason:
                message = f"交换机配置失败：{reason}"
            else:
                message = "交换机配置失败"
        details = {}
        if switch_id:
            details["switch_id"] = switch_id
        if reason:
            details["reason"] = reason
        super().__init__(message=message, code="SWITCH_CONFIG_ERROR", details=details)