# -*- coding: utf-8 -*-
"""
基础异常类模块

定义应用程序的基础异常类，所有自定义异常都应继承自此类。
"""
from typing import Any, Dict, Optional


class BaseAppException(Exception):
    """应用基础异常类
    
    所有应用程序自定义异常的基类，提供统一的异常接口和行为。
    
    Attributes:
        message: 异常消息
        code: 异常代码，用于标识异常类型
        details: 异常详细信息字典
        status_code: HTTP状态码（用于API响应）
    """
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 400
    ):
        """初始化基础异常
        
        Args:
            message: 异常消息，描述发生的错误
            code: 异常代码，默认使用类名
            details: 异常详细信息，包含额外的错误上下文
            status_code: HTTP状态码，用于API响应
        """
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        self.status_code = status_code
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """将异常转换为字典格式
        
        Returns:
            Dict: 包含异常信息的字典
        """
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details
        }
    
    def __str__(self) -> str:
        """返回异常的字符串表示
        
        Returns:
            str: 异常的字符串描述
        """
        return f"{self.code}: {self.message}"
    
    def __repr__(self) -> str:
        """返回异常的详细字符串表示
        
        Returns:
            str: 异常的详细描述
        """
        return (
            f"{self.__class__.__name__}("
            f"message='{self.message}', "
            f"code='{self.code}', "
            f"details={self.details}, "
            f"status_code={self.status_code})"
        )