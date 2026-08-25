# -*- coding: utf-8 -*-
"""
日志接口定义

定义日志记录的统一接口，支持结构化日志和多种输出格式。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from enum import Enum


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormatter(ABC):
    
    @abstractmethod
    def format(self, record: Dict[str, Any]) -> str:
        pass
    
    @abstractmethod
    def get_format_name(self) -> str:
        pass


class LogHandler(ABC):
    
    @abstractmethod
    def emit(self, record: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    def set_level(self, level: LogLevel) -> None:
        pass
    
    @abstractmethod
    def set_formatter(self, formatter: LogFormatter) -> None:
        pass
    
    @abstractmethod
    def close(self) -> None:
        pass
    
    @abstractmethod
    def flush(self) -> None:
        pass


class Logger(ABC):
    
    @abstractmethod
    def debug(self, message: str, extra: Dict[str, Any] = None, 
              exc_info: bool = False) -> None:
        pass
    
    @abstractmethod
    def info(self, message: str, extra: Dict[str, Any] = None) -> None:
        pass
    
    @abstractmethod
    def warning(self, message: str, extra: Dict[str, Any] = None) -> None:
        pass
    
    @abstractmethod
    def error(self, message: str, extra: Dict[str, Any] = None, 
              exc_info: bool = True) -> None:
        pass
    
    @abstractmethod
    def critical(self, message: str, extra: Dict[str, Any] = None, 
                 exc_info: bool = True) -> None:
        pass
    
    @abstractmethod
    def log(self, level: LogLevel, message: str, 
            extra: Dict[str, Any] = None, exc_info: bool = False) -> None:
        pass
    
    @abstractmethod
    def set_level(self, level: LogLevel) -> None:
        pass
    
    @abstractmethod
    def add_handler(self, handler: LogHandler) -> None:
        pass
    
    @abstractmethod
    def remove_handler(self, handler: LogHandler) -> None:
        pass
    
    @abstractmethod
    def get_handlers(self) -> List[LogHandler]:
        pass
    
    @abstractmethod
    def is_enabled_for(self, level: LogLevel) -> bool:
        pass


class StructuredLogger(Logger):
    
    @abstractmethod
    def log_event(self, event_name: str, data: Dict[str, Any] = None, 
                  level: LogLevel = LogLevel.INFO) -> None:
        pass
    
    @abstractmethod
    def log_request(self, request_info: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    def log_database_query(self, query_info: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    def log_cache_operation(self, operation_info: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    def log_authentication(self, auth_info: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    def log_security_event(self, event_info: Dict[str, Any]) -> None:
        pass


class LogManager(ABC):
    
    @abstractmethod
    def get_logger(self, name: str) -> Logger:
        pass
    
    @abstractmethod
    def create_logger(self, name: str, level: LogLevel = LogLevel.INFO, 
                     handlers: List[LogHandler] = None) -> Logger:
        pass
    
    @abstractmethod
    def configure_logging(self, config: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    def get_log_files(self) -> List[str]:
        pass
    
    @abstractmethod
    def rotate_logs(self) -> None:
        pass
    
    @abstractmethod
    def cleanup_old_logs(self, days: int = 30) -> int:
        pass
    
    @abstractmethod
    def get_log_statistics(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def search_logs(self, query: str, start_time: Optional[int] = None, 
                   end_time: Optional[int] = None, 
                   level: Optional[LogLevel] = None) -> List[Dict[str, Any]]:
        pass
