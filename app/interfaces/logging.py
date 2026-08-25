# -*- coding: utf-8 -*-
"""
日志接口定义

定义日志记录的统一接口，支持结构化日志和多种输出格式。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from enum import Enum


class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormatter(ABC):
    """日志格式化器接口
    
    定义日志消息的格式化方式。
    """
    
    @abstractmethod
    def format(self, record: Dict[str, Any]) -> str:
        """格式化日志记录
        
        Args:
            record: 日志记录字典
                - timestamp: 时间戳
                - level: 日志级别
                - message: 日志消息
                - module: 模块名
                - function: 函数名
                - line: 行号
                - extra: 额外数据
                
        Returns:
            str: 格式化后的日志字符串
        """
        pass
    
    @abstractmethod
    def get_format_name(self) -> str:
        """获取格式化器名称
        
        Returns:
            str: 格式化器名称
        """
        pass


class LogHandler(ABC):
    """日志处理器接口
    
    定义日志输出的处理方式。
    """
    
    @abstractmethod
    def emit(self, record: Dict[str, Any]) -> None:
        """输出日志记录
        
        Args:
            record: 日志记录字典
        """
        pass
    
    @abstractmethod
    def set_level(self, level: LogLevel) -> None:
        """设置日志级别
        
        Args:
            level: 日志级别
        """
        pass
    
    @abstractmethod
    def set_formatter(self, formatter: LogFormatter) -> None:
        """设置格式化器
        
        Args:
            formatter: 格式化器实例
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """关闭处理器"""
        pass
    
    @abstractmethod
    def flush(self) -> None:
        """刷新缓冲区"""
        pass


class Logger(ABC):
    """日志记录器接口
    
    提供统一的日志记录功能。
    """
    
    @abstractmethod
    def debug(self, message: str, extra: Dict[str, Any] = None, 
              exc_info: bool = False) -> None:
        """记录调试日志
        
        Args:
            message: 日志消息
            extra: 额外数据
            exc_info: 是否包含异常信息
        """
        pass
    
    @abstractmethod
    def info(self, message: str, extra: Dict[str, Any] = None) -> None:
        """记录信息日志
        
        Args:
            message: 日志消息
            extra: 额外数据
        """
        pass
    
    @abstractmethod
    def warning(self, message: str, extra: Dict[str, Any] = None) -> None:
        """记录警告日志
        
        Args:
            message: 日志消息
            extra: 额外数据
        """
        pass
    
    @abstractmethod
    def error(self, message: str, extra: Dict[str, Any] = None, 
              exc_info: bool = True) -> None:
        """记录错误日志
        
        Args:
            message: 日志消息
            extra: 额外数据
            exc_info: 是否包含异常信息
        """
        pass
    
    @abstractmethod
    def critical(self, message: str, extra: Dict[str, Any] = None, 
                 exc_info: bool = True) -> None:
        """记录严重错误日志
        
        Args:
            message: 日志消息
            extra: 额外数据
            exc_info: 是否包含异常信息
        """
        pass
    
    @abstractmethod
    def log(self, level: LogLevel, message: str, 
            extra: Dict[str, Any] = None, exc_info: bool = False) -> None:
        """记录指定级别的日志
        
        Args:
            level: 日志级别
            message: 日志消息
            extra: 额外数据
            exc_info: 是否包含异常信息
        """
        pass
    
    @abstractmethod
    def set_level(self, level: LogLevel) -> None:
        """设置日志级别
        
        Args:
            level: 日志级别
        """
        pass
    
    @abstractmethod
    def add_handler(self, handler: LogHandler) -> None:
        """添加日志处理器
        
        Args:
            handler: 日志处理器
        """
        pass
    
    @abstractmethod
    def remove_handler(self, handler: LogHandler) -> None:
        """移除日志处理器
        
        Args:
            handler: 日志处理器
        """
        pass
    
    @abstractmethod
    def get_handlers(self) -> List[LogHandler]:
        """获取所有处理器
        
        Returns:
            List[LogHandler]: 处理器列表
        """
        pass
    
    @abstractmethod
    def is_enabled_for(self, level: LogLevel) -> bool:
        """检查是否启用指定级别的日志
        
        Args:
            level: 日志级别
            
        Returns:
            bool: 启用返回True
        """
        pass


class StructuredLogger(Logger):
    """结构化日志记录器接口
    
    扩展基础日志记录器，支持结构化日志记录。
    """
    
    @abstractmethod
    def log_event(self, event_name: str, data: Dict[str, Any] = None, 
                  level: LogLevel = LogLevel.INFO) -> None:
        """记录事件日志
        
        Args:
            event_name: 事件名称
            data: 事件数据
            level: 日志级别
        """
        pass
    
    @abstractmethod
    def log_request(self, request_info: Dict[str, Any]) -> None:
        """记录请求日志
        
        Args:
            request_info: 请求信息
                - method: HTTP方法
                - url: 请求URL
                - user_id: 用户ID
                - ip: 客户端IP
                - user_agent: 用户代理
                - duration: 请求耗时
                - status_code: 响应状态码
        """
        pass
    
    @abstractmethod
    def log_database_query(self, query_info: Dict[str, Any]) -> None:
        """记录数据库查询日志
        
        Args:
            query_info: 查询信息
                - query: SQL查询语句
                - params: 查询参数
                - duration: 执行耗时
                - rows_affected: 影响行数
        """
        pass
    
    @abstractmethod
    def log_cache_operation(self, operation_info: Dict[str, Any]) -> None:
        """记录缓存操作日志
        
        Args:
            operation_info: 操作信息
                - operation: 操作类型（get, set, delete）
                - key: 缓存键
                - hit: 是否命中（仅get操作）
                - ttl: 过期时间（仅set操作）
        """
        pass
    
    @abstractmethod
    def log_authentication(self, auth_info: Dict[str, Any]) -> None:
        """记录认证日志
        
        Args:
            auth_info: 认证信息
                - user_id: 用户ID
                - username: 用户名
                - auth_type: 认证类型
                - success: 是否成功
                - ip: 客户端IP
                - user_agent: 用户代理
        """
        pass
    
    @abstractmethod
    def log_security_event(self, event_info: Dict[str, Any]) -> None:
        """记录安全事件日志
        
        Args:
            event_info: 事件信息
                - event_type: 事件类型
                - severity: 严重程度
                - user_id: 用户ID
                - ip: 客户端IP
                - details: 事件详情
        """
        pass


class LogManager(ABC):
    """日志管理器接口
    
    提供日志系统的统一管理。
    """
    
    @abstractmethod
    def get_logger(self, name: str) -> Logger:
        """获取日志记录器
        
        Args:
            name: 记录器名称
            
        Returns:
            Logger: 日志记录器实例
        """
        pass
    
    @abstractmethod
    def create_logger(self, name: str, level: LogLevel = LogLevel.INFO, 
                     handlers: List[LogHandler] = None) -> Logger:
        """创建日志记录器
        
        Args:
            name: 记录器名称
            level: 日志级别
            handlers: 处理器列表
            
        Returns:
            Logger: 日志记录器实例
        """
        pass
    
    @abstractmethod
    def configure_logging(self, config: Dict[str, Any]) -> None:
        """配置日志系统
        
        Args:
            config: 日志配置
                - level: 全局日志级别
                - format: 日志格式
                - handlers: 处理器配置
                - loggers: 记录器配置
        """
        pass
    
    @abstractmethod
    def get_log_files(self) -> List[str]:
        """获取日志文件列表
        
        Returns:
            List[str]: 日志文件路径列表
        """
        pass
    
    @abstractmethod
    def rotate_logs(self) -> None:
        """轮转日志文件"""
        pass
    
    @abstractmethod
    def cleanup_old_logs(self, days: int = 30) -> int:
        """清理旧日志文件
        
        Args:
            days: 保留天数
            
        Returns:
            int: 清理的文件数量
        """
        pass
    
    @abstractmethod
    def get_log_statistics(self) -> Dict[str, Any]:
        """获取日志统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
                - total_logs: 总日志数
                - error_count: 错误日志数
                - warning_count: 警告日志数
                - log_size: 日志文件大小
        """
        pass
    
    @abstractmethod
    def search_logs(self, query: str, start_time: Optional[int] = None, 
                   end_time: Optional[int] = None, 
                   level: Optional[LogLevel] = None) -> List[Dict[str, Any]]:
        """搜索日志
        
        Args:
            query: 搜索关键词
            start_time: 开始时间戳
            end_time: 结束时间戳
            level: 日志级别
            
        Returns:
            List[Dict[str, Any]]: 匹配的日志记录
        """
        pass