# -*- coding: utf-8 -*-
"""
基础异常类模块

定义应用程序的基础异常类，所有自定义异常都应继承自此类。
"""
from typing import Any, Dict, Optional


class BaseAppException(Exception):
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 400
    ):
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        self.status_code = status_code
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details
        }
    
    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
    
    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message='{self.message}', "
            f"code='{self.code}', "
            f"details={self.details}, "
            f"status_code={self.status_code})"
        )
