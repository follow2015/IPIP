# -*- coding: utf-8 -*-
"""
数据访问异常模块

定义数据访问相关的异常类。
"""
from typing import Any, Dict, Optional

from .base import BaseAppException


class DataAccessError(BaseAppException):
    """数据访问异常基类
    
    当数据访问操作失败时抛出此类异常。
    """
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500,
        original_error: Optional[Exception] = None
    ):
        """初始化数据访问异常
        
        Args:
            message: 异常消息
            code: 异常代码
            details: 异常详情
            status_code: HTTP状态码
            original_error: 原始异常对象
        """
        super().__init__(
            message=message,
            code=code or "DATA_ACCESS_ERROR",
            details=details,
            status_code=status_code
        )
        self.original_error = original_error


class DatabaseConnectionError(DataAccessError):
    """数据库连接异常
    
    当数据库连接失败时抛出此异常。
    """
    
    def __init__(
        self,
        database_name: Optional[str] = None,
        connection_string: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化数据库连接异常
        
        Args:
            database_name: 数据库名称
            connection_string: 连接字符串（敏感信息会被隐藏）
            message: 自定义异常消息
        """
        if not message:
            if database_name:
                message = f"数据库连接失败：{database_name}"
            else:
                message = "数据库连接失败"
                
        details = {}
        if database_name:
            details["database_name"] = database_name
        if connection_string:
            try:
                safe_connection = connection_string.split('@')[-1] if '@' in connection_string else connection_string
                details["connection_info"] = safe_connection
            except Exception:
                details["connection_info"] = "***"
                
        super().__init__(
            message=message,
            code="DATABASE_CONNECTION_ERROR",
            details=details
        )


class QueryExecutionError(DataAccessError):
    """查询执行异常
    
    当SQL查询执行失败时抛出此异常。
    """
    
    def __init__(
        self,
        message: str,
        query_type: str = "QUERY",
        table_name: Optional[str] = None,
        error_details: Optional[str] = None,
        original_error: Optional[Exception] = None
    ):
        """初始化查询执行异常
        
        Args:
            message: 异常消息
            query_type: 查询类型（SELECT、INSERT、UPDATE、DELETE等）
            table_name: 表名
            error_details: 错误详情
            original_error: 原始异常对象
        """
        details = {"query_type": query_type}
        if table_name:
            details["table_name"] = table_name
        if error_details:
            details["error_details"] = error_details
        if original_error and not error_details:
            details["error_details"] = str(original_error)
            
        super().__init__(
            message=message,
            code="QUERY_EXECUTION_ERROR",
            details=details,
            original_error=original_error
        )
    
    def __str__(self) -> str:
        """包含原始错误信息的字符串表示"""
        base = f"{self.code}: {self.message}"
        if self.original_error:
            base += f" | {self.original_error}"
        return base


class TransactionError(DataAccessError):
    """事务异常
    
    当数据库事务操作失败时抛出此异常。
    """
    
    def __init__(
        self,
        operation: str,
        reason: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化事务异常
        
        Args:
            operation: 事务操作（BEGIN、COMMIT、ROLLBACK等）
            reason: 失败原因
            message: 自定义异常消息
        """
        if not message:
            if reason:
                message = f"事务{operation}失败：{reason}"
            else:
                message = f"事务{operation}失败"
                
        details = {"operation": operation}
        if reason:
            details["reason"] = reason
            
        super().__init__(
            message=message,
            code="TRANSACTION_ERROR",
            details=details
        )


class DataIntegrityError(DataAccessError):
    """数据完整性异常
    
    当数据完整性约束违反时抛出此异常。
    """
    
    def __init__(
        self,
        constraint_type: str,
        constraint_name: Optional[str] = None,
        table_name: Optional[str] = None,
        message: Optional[str] = None
    ):
        """初始化数据完整性异常
        
        Args:
            constraint_type: 约束类型（PRIMARY KEY、FOREIGN KEY、UNIQUE等）
            constraint_name: 约束名称
            table_name: 表名
            message: 自定义异常消息
        """
        if not message:
            constraint_names = {
                "PRIMARY KEY": "主键",
                "FOREIGN KEY": "外键",
                "UNIQUE": "唯一",
                "CHECK": "检查",
                "NOT NULL": "非空"
            }
            constraint_display = constraint_names.get(constraint_type, constraint_type)
            
            if table_name and constraint_name:
                message = f"数据完整性违反：表 {table_name} 的{constraint_display}约束 {constraint_name}"
            elif table_name:
                message = f"数据完整性违反：表 {table_name} 的{constraint_display}约束"
            else:
                message = f"数据完整性违反：{constraint_display}约束"
                
        details = {"constraint_type": constraint_type}
        if constraint_name:
            details["constraint_name"] = constraint_name
        if table_name:
            details["table_name"] = table_name
            
        super().__init__(
            message=message,
            code="DATA_INTEGRITY_ERROR",
            details=details,
            status_code=409
        )


class RecordNotFoundError(DataAccessError):
    """记录不存在异常
    
    当查找的数据记录不存在时抛出此异常。
    """
    
    def __init__(
        self,
        table_name: str,
        identifier: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None
    ):
        """初始化记录不存在异常
        
        Args:
            table_name: 表名
            identifier: 记录标识符
            message: 自定义异常消息
        """
        if not message:
            if identifier:
                id_str = ", ".join([f"{k}={v}" for k, v in identifier.items()])
                message = f"记录不存在：表 {table_name}，条件 {id_str}"
            else:
                message = f"记录不存在：表 {table_name}"
                
        details = {"table_name": table_name}
        if identifier:
            details["identifier"] = identifier
            
        super().__init__(
            message=message,
            code="RECORD_NOT_FOUND",
            details=details,
            status_code=404
        )


class DuplicateRecordError(DataAccessError):
    """重复记录异常
    
    当尝试插入重复记录时抛出此异常。
    """
    
    def __init__(
        self,
        table_name: str,
        duplicate_fields: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None
    ):
        """初始化重复记录异常
        
        Args:
            table_name: 表名
            duplicate_fields: 重复的字段和值
            message: 自定义异常消息
        """
        if not message:
            if duplicate_fields:
                fields_str = ", ".join([f"{k}={v}" for k, v in duplicate_fields.items()])
                message = f"记录重复：表 {table_name}，字段 {fields_str}"
            else:
                message = f"记录重复：表 {table_name}"
                
        details = {"table_name": table_name}
        if duplicate_fields:
            details["duplicate_fields"] = duplicate_fields
            
        super().__init__(
            message=message,
            code="DUPLICATE_RECORD",
            details=details,
            status_code=409
        )