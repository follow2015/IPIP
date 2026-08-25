# -*- coding: utf-8 -*-
"""
统一日志配置模块

提供统一的日志配置、格式化器和处理器。
"""
import json
import logging
import os
import sys
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Any, Dict, Optional, Union

from config import get_config

config = get_config()


class JSONFormatter(logging.Formatter):
    """JSON格式化器
    
    将日志记录格式化为JSON格式，支持结构化日志。
    """
    
    def __init__(self, include_extra: bool = True):
        """初始化JSON格式化器
        
        Args:
            include_extra: 是否包含额外字段
        """
        super().__init__()
        self.include_extra = include_extra
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为JSON
        
        Args:
            record: 日志记录
            
        Returns:
            str: JSON格式的日志字符串
        """
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "thread": record.thread,
            "thread_name": record.threadName,
            "process": record.process,
        }
        
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        if self.include_extra and hasattr(record, 'extra'):
            log_data["extra"] = record.extra
        
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
                'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
                'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
                'processName', 'process', 'getMessage', 'extra'
            } and not key.startswith('_'):
                log_data[key] = value
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


class StandardFormatter(logging.Formatter):
    """标准格式化器
    
    提供统一的标准日志格式。
    """
    
    def __init__(self, include_extra: bool = True):
        """初始化标准格式化器
        
        Args:
            include_extra: 是否包含额外字段
        """
        super().__init__(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        self.include_extra = include_extra
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录
        
        Args:
            record: 日志记录
            
        Returns:
            str: 格式化后的日志字符串
        """
        formatted = super().format(record)
        
        if self.include_extra and hasattr(record, 'extra') and record.extra:
            extra_str = " | ".join(f"{k}={v}" for k, v in record.extra.items())
            formatted = f"{formatted} | {extra_str}"
        
        return formatted


class LoggingConfig:
    """日志配置类
    
    提供统一的日志配置管理。
    """
    
    LEVEL_MAPPING = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }
    
    DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s"
    DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    
    @classmethod
    def get_level(cls, level_name: str) -> int:
        """获取日志级别
        
        Args:
            level_name: 级别名称
            
        Returns:
            int: 日志级别
        """
        return cls.LEVEL_MAPPING.get(level_name.upper(), logging.INFO)
    
    @classmethod
    def create_file_handler(
        cls,
        filename: str,
        level: Union[str, int] = logging.INFO,
        formatter: Optional[logging.Formatter] = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 10,
        encoding: str = 'utf-8'
    ) -> RotatingFileHandler:
        """创建文件处理器
        
        Args:
            filename: 文件名
            level: 日志级别
            formatter: 格式化器
            max_bytes: 最大文件大小
            backup_count: 备份文件数量
            encoding: 文件编码
            
        Returns:
            RotatingFileHandler: 文件处理器
        """
        log_dir = os.path.dirname(filename)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        handler = RotatingFileHandler(
            filename=filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=encoding
        )
        
        if isinstance(level, str):
            level = cls.get_level(level)
        handler.setLevel(level)
        
        if formatter is None:
            formatter = StandardFormatter()
        handler.setFormatter(formatter)
        
        return handler
    
    @classmethod
    def create_console_handler(
        cls,
        level: Union[str, int] = logging.INFO,
        formatter: Optional[logging.Formatter] = None,
        stream=None
    ) -> logging.StreamHandler:
        """创建控制台处理器
        
        Args:
            level: 日志级别
            formatter: 格式化器
            stream: 输出流
            
        Returns:
            logging.StreamHandler: 控制台处理器
        """
        handler = logging.StreamHandler(stream or sys.stdout)
        
        if isinstance(level, str):
            level = cls.get_level(level)
        handler.setLevel(level)
        
        if formatter is None:
            formatter = StandardFormatter()
        handler.setFormatter(formatter)
        
        return handler
    
    @classmethod
    def create_timed_rotating_handler(
        cls,
        filename: str,
        when: str = 'midnight',
        interval: int = 1,
        backup_count: int = 30,
        level: Union[str, int] = logging.INFO,
        formatter: Optional[logging.Formatter] = None,
        encoding: str = 'utf-8'
    ) -> TimedRotatingFileHandler:
        """创建按时间轮转的文件处理器
        
        Args:
            filename: 文件名
            when: 轮转时机 ('S', 'M', 'H', 'D', 'midnight')
            interval: 轮转间隔
            backup_count: 备份文件数量
            level: 日志级别
            formatter: 格式化器
            encoding: 文件编码
            
        Returns:
            TimedRotatingFileHandler: 时间轮转处理器
        """
        log_dir = os.path.dirname(filename)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        handler = TimedRotatingFileHandler(
            filename=filename,
            when=when,
            interval=interval,
            backupCount=backup_count,
            encoding=encoding
        )
        
        if isinstance(level, str):
            level = cls.get_level(level)
        handler.setLevel(level)
        
        if formatter is None:
            formatter = StandardFormatter()
        handler.setFormatter(formatter)
        
        return handler
    
    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """获取默认日志配置
        
        Returns:
            Dict[str, Any]: 默认配置
        """
        return {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'standard': {
                    'format': cls.DEFAULT_FORMAT,
                    'datefmt': cls.DEFAULT_DATE_FORMAT,
                },
                'json': {
                    '()': JSONFormatter,
                    'include_extra': True,
                },
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': config.LOG_LEVEL,
                    'formatter': 'standard',
                    'stream': 'ext://sys.stdout',
                },
                'file': {
                    'class': 'logging.handlers.RotatingFileHandler',
                    'level': config.LOG_LEVEL,
                    'formatter': 'standard',
                    'filename': os.path.join(config.LOG_DIR, 'app.log'),
                    'maxBytes': config.LOG_MAX_BYTES,
                    'backupCount': config.LOG_BACKUP_COUNT,
                    'encoding': 'utf-8',
                },
                'error_file': {
                    'class': 'logging.handlers.RotatingFileHandler',
                    'level': 'ERROR',
                    'formatter': 'standard',
                    'filename': os.path.join(config.LOG_DIR, 'error.log'),
                    'maxBytes': config.LOG_MAX_BYTES,
                    'backupCount': config.LOG_BACKUP_COUNT,
                    'encoding': 'utf-8',
                },
                'json_file': {
                    'class': 'logging.handlers.RotatingFileHandler',
                    'level': config.LOG_LEVEL,
                    'formatter': 'json',
                    'filename': os.path.join(config.LOG_DIR, 'app.json'),
                    'maxBytes': config.LOG_MAX_BYTES,
                    'backupCount': config.LOG_BACKUP_COUNT,
                    'encoding': 'utf-8',
                },
            },
            'loggers': {
                'app': {
                    'level': config.LOG_LEVEL,
                    'handlers': ['console', 'file', 'error_file', 'json_file'],
                    'propagate': False,
                },
                'sqlalchemy.engine': {
                    'level': 'WARNING',
                    'handlers': ['file'],
                    'propagate': False,
                },
                'werkzeug': {
                    'level': 'WARNING',
                    'handlers': ['file'],
                    'propagate': False,
                },
            },
            'root': {
                'level': 'WARNING',
                'handlers': ['console', 'file'],
            },
        }