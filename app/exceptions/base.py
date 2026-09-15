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


class PresetResponseError(BaseAppException):
    """预置响应异常 —— 「不吞异常地返回指定响应」契约。

    背景
    ----
    ``@transactional``（app/utils/transactional.py）只在被包裹函数**正常返回**时
    commit、异常**传播出去**时 rollback。因此 API 层若在 ``except`` 里直接
    ``return APIResponse.error(...)``，异常就被吞掉 → 装饰器误判为成功 → 已 flush
    的写入被提交，形成"半成品提交"（审计 P0#2）。

    但 API 层有时确实需要返回一个**定制的**业务响应（自定义 error_code /
    status_code，例如 ``409 VLAN_CONFLICT``），不能改用通用异常 —— 那会改变
    对外契约。本异常即该场景的表达：承载"原本要返回的响应"，抛出后由全局
    处理器（app/exceptions/handlers.py）**逐字段原样还原**成与原先完全一致的
    响应体。于是异常真正传播出去触发 rollback，而对外的状态码 / 错误码 / 消息
    零变化。

    用法::

        except Exception as e:
            logger.error("设备删除失败: %s", e)
            raise PresetResponseError(
                message="设备删除失败",
                error_code="DEVICE_DELETE_ERROR",
                status_code=500,
            ) from e

    Attributes:
        error_code: 响应体 ``error_code``。为 ``None`` 表示**不输出该字段**，
            与 ``APIResponse.error(error_code=None)`` 的行为一致。注意不能直接用
            ``self.code`` 判断 —— ``BaseAppException`` 会用类名兜底，故此处单独保存原值。
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        status_code: int = 500
    ):
        """初始化预置响应异常

        Args:
            message: 响应体 message
            error_code: 响应体 error_code；None 表示不输出该字段
            status_code: HTTP 状态码
        """
        self.error_code = error_code
        super().__init__(
            message=message,
            code=error_code,  # 仅用于日志可读性，响应体由 self.error_code 决定
            details=None,
            status_code=status_code
        )