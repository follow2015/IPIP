# -*- coding: utf-8 -*-
"""
统一日志管理器

提供统一的日志记录接口和管理功能。
"""
import logging
import logging.config
import os
import time
from contextvars import ContextVar
from functools import wraps
from typing import Any, Dict, List, Optional

from flask import g, has_request_context, request

from app.interfaces.logging import LogManager, LogLevel, StructuredLogger
from app.utils.logging.config import LoggingConfig
from config import get_config

config = get_config()

_log_extra_var: ContextVar[Dict[str, Any]] = ContextVar('_log_extra_var', default={})


class _ExtraFilter(logging.Filter):
    """日志过滤器：从 ContextVar 注入 extra 字段到 LogRecord。

    替代原先的 setLogRecordFactory 全局替换方案，避免多线程竞态。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        extra = _log_extra_var.get({})
        if extra:
            record.extra = extra
        return True


class UnifiedLogger(StructuredLogger):
    """统一日志记录器
    
    实现StructuredLogger接口，提供统一的日志记录功能。
    """
    
    def __init__(self, name: str, logger: logging.Logger):
        """初始化统一日志记录器
        
        Args:
            name: 记录器名称
            logger: Python标准日志记录器
        """
        self.name = name
        self._logger = logger
        if not any(isinstance(f, _ExtraFilter) for f in self._logger.filters):
            self._logger.addFilter(_ExtraFilter())
    
    def _log_with_extra(self, level: int, message: str, extra: Dict[str, Any] = None, 
                       exc_info: bool = False, stack_info: bool = False, *args) -> None:
        """记录带额外信息的日志

        使用 contextvars 传递额外信息，避免全局 setLogRecordFactory 的多线程竞态问题。

        Args:
            level: 日志级别
            message: 日志消息（支持 % 格式化）
            extra: 额外信息
            exc_info: 是否包含异常信息
            *args: 消息格式化参数（兼容标准库 logging 的 % 格式化）
        """
        if args:
            try:
                message = message % args
            except (TypeError, ValueError):
                pass
        record_extra = {}
        
        if has_request_context():
            from app.utils.auth import get_current_user_id
            record_extra.update({
                'request_id': getattr(g, 'request_id', None),
                'user_id': get_current_user_id(),
                'ip_address': request.remote_addr,
                'method': request.method,
                'path': request.path,
                'user_agent': request.headers.get('User-Agent', ''),
            })
        
        if extra:
            record_extra.update(extra)
        
        if record_extra:
            token = _log_extra_var.set(record_extra)
            try:
                self._logger.log(level, message, exc_info=exc_info, stack_info=stack_info)
            finally:
                _log_extra_var.reset(token)
        else:
            self._logger.log(level, message, exc_info=exc_info, stack_info=stack_info)
    
    def debug(self, message: str, *args, extra: Dict[str, Any] = None, 
              exc_info: bool = False, stack_info: bool = False) -> None:
        """记录调试日志"""
        self._log_with_extra(logging.DEBUG, message, extra, exc_info, stack_info, *args)
    
    def info(self, message: str, *args, extra: Dict[str, Any] = None,
             exc_info: bool = False, stack_info: bool = False) -> None:
        """记录信息日志"""
        self._log_with_extra(logging.INFO, message, extra, exc_info, stack_info, *args)
    
    def warning(self, message: str, *args, extra: Dict[str, Any] = None,
                exc_info: bool = False, stack_info: bool = False) -> None:
        """记录警告日志"""
        self._log_with_extra(logging.WARNING, message, extra, exc_info, stack_info, *args)
    
    def error(self, message: str, *args, extra: Dict[str, Any] = None, 
              exc_info: bool = True, stack_info: bool = False) -> None:
        """记录错误日志"""
        self._log_with_extra(logging.ERROR, message, extra, exc_info, stack_info, *args)
    
    def exception(self, message: str, *args, extra: Dict[str, Any] = None,
                  exc_info: bool = True, stack_info: bool = False) -> None:
        """记录异常日志（等价于 error(exc_info=True)，兼容 stdlib logging.exception 语义）"""
        self._log_with_extra(logging.ERROR, message, extra, exc_info, stack_info, *args)
    
    def critical(self, message: str, *args, extra: Dict[str, Any] = None, 
                 exc_info: bool = True, stack_info: bool = False) -> None:
        """记录严重错误日志"""
        self._log_with_extra(logging.CRITICAL, message, extra, exc_info, stack_info, *args)
    
    def log(self, level: LogLevel, message: str, 
            extra: Dict[str, Any] = None, exc_info: bool = False) -> None:
        """记录指定级别的日志"""
        log_level = LoggingConfig.get_level(level.value)
        self._log_with_extra(log_level, message, extra, exc_info)
    
    def set_level(self, level: LogLevel) -> None:
        """设置日志级别"""
        log_level = LoggingConfig.get_level(level.value)
        self._logger.setLevel(log_level)
    
    def add_handler(self, handler) -> None:
        """添加日志处理器"""
        self._logger.addHandler(handler)
    
    def remove_handler(self, handler) -> None:
        """移除日志处理器"""
        self._logger.removeHandler(handler)
    
    def get_handlers(self) -> List:
        """获取所有处理器"""
        return self._logger.handlers
    
    def is_enabled_for(self, level: LogLevel) -> bool:
        """检查是否启用指定级别的日志"""
        log_level = LoggingConfig.get_level(level.value)
        return self._logger.isEnabledFor(log_level)
    
    def log_event(self, event_name: str, data: Dict[str, Any] = None, 
                  level: LogLevel = LogLevel.INFO) -> None:
        """记录事件日志"""
        extra = {
            'event_name': event_name,
            'event_data': data or {},
            'log_type': 'event'
        }
        self.log(level, f"事件: {event_name}", extra)
    
    def log_request(self, request_info: Dict[str, Any]) -> None:
        """记录请求日志"""
        extra = {
            'log_type': 'request',
            **request_info
        }
        message = f"请求: {request_info.get('method', 'UNKNOWN')} {request_info.get('url', 'UNKNOWN')}"
        if 'duration' in request_info:
            message += f" | 耗时: {request_info['duration']:.3f}s"
        if 'status_code' in request_info:
            message += f" | 状态: {request_info['status_code']}"
        
        status_code = request_info.get('status_code', 200)
        if status_code >= 500:
            level = LogLevel.ERROR
        elif status_code >= 400:
            level = LogLevel.WARNING
        else:
            level = LogLevel.INFO
        
        self.log(level, message, extra)
    
    def log_database_query(self, query_info: Dict[str, Any]) -> None:
        """记录数据库查询日志"""
        extra = {
            'log_type': 'database_query',
            **query_info
        }
        
        duration = query_info.get('duration', 0)
        message = f"数据库查询: 耗时 {duration:.3f}s"
        
        if 'rows_affected' in query_info:
            message += f" | 影响行数: {query_info['rows_affected']}"
        
        level = LogLevel.WARNING if duration > 1.0 else LogLevel.DEBUG
        self.log(level, message, extra)
    
    def log_cache_operation(self, operation_info: Dict[str, Any]) -> None:
        """记录缓存操作日志"""
        extra = {
            'log_type': 'cache_operation',
            **operation_info
        }
        
        operation = operation_info.get('operation', 'unknown')
        key = operation_info.get('key', 'unknown')
        message = f"缓存操作: {operation} | 键: {key}"
        
        if operation == 'get' and 'hit' in operation_info:
            message += f" | 命中: {'是' if operation_info['hit'] else '否'}"
        
        self.log(LogLevel.DEBUG, message, extra)
    
    def log_authentication(self, auth_info: Dict[str, Any]) -> None:
        """记录认证日志"""
        extra = {
            'log_type': 'authentication',
            **auth_info
        }
        
        username = auth_info.get('username', 'unknown')
        auth_type = auth_info.get('auth_type', 'unknown')
        success = auth_info.get('success', False)
        
        message = f"用户认证: {username} | 类型: {auth_type} | 结果: {'成功' if success else '失败'}"
        
        level = LogLevel.INFO if success else LogLevel.WARNING
        self.log(level, message, extra)
    
    def log_security_event(self, event_info: Dict[str, Any]) -> None:
        """记录安全事件日志"""
        extra = {
            'log_type': 'security_event',
            **event_info
        }
        
        event_type = event_info.get('event_type', 'unknown')
        severity = event_info.get('severity', 'medium')
        
        message = f"安全事件: {event_type} | 严重程度: {severity}"
        
        level_mapping = {
            'low': LogLevel.INFO,
            'medium': LogLevel.WARNING,
            'high': LogLevel.ERROR,
            'critical': LogLevel.CRITICAL
        }
        level = level_mapping.get(severity, LogLevel.WARNING)
        
        self.log(level, message, extra)

    def log_audit_event(self, audit_info: Dict[str, Any]) -> None:
        """记录审计事件日志，同时桥接到 AuditService

        Args:
            audit_info: 审计信息字典
                - action: 操作类型
                - resource: 资源类型
                - resource_id: 资源ID（可选）
                - user_id: 操作人ID（可选）
                - detail: 详情（可选）
                - ip_address: IP地址（可选）
                - severity: 严重程度 info/warning/critical（可选，默认info）
        """
        extra = {
            'log_type': 'audit_event',
            **audit_info
        }

        action = audit_info.get('action', 'unknown')
        resource = audit_info.get('resource', 'unknown')
        severity = audit_info.get('severity', 'info')

        message = f"审计事件: {action} | 资源: {resource}"

        level_mapping = {
            'info': LogLevel.INFO,
            'warning': LogLevel.WARNING,
            'critical': LogLevel.ERROR,
        }
        level = level_mapping.get(severity, LogLevel.INFO)

        self.log(level, message, extra)

        try:
            from app.services.audit_service import AuditService
            from app.persistence.audit_log_repository import AuditLogRepository
            audit_service = AuditService(AuditLogRepository())
            audit_service.log(
                user_id=audit_info.get('user_id'),
                action=action,
                resource=resource,
                resource_id=audit_info.get('resource_id'),
                detail=audit_info.get('detail'),
                ip_address=audit_info.get('ip_address'),
            )
        except Exception:
            self.log(LogLevel.WARNING, f"审计事件写入数据库失败: {action} | 资源: {resource}", exc_info=True)


class UnifiedLogManager(LogManager):
    """统一日志管理器
    
    实现LogManager接口，提供日志系统的统一管理。
    """
    
    def __init__(self):
        """初始化日志管理器"""
        self._loggers: Dict[str, UnifiedLogger] = {}
        self._initialized = False
        self._config = None
    
    def init_app(self, app=None) -> None:
        """初始化Flask应用日志系统（init_app别名）
        
        Args:
            app: Flask应用实例
        """
        self.initialize(app)
    
    def initialize(self, app=None) -> None:
        """初始化日志系统
        
        Args:
            app: Flask应用实例
        """
        if self._initialized:
            return
        
        if not os.path.exists(config.LOG_DIR):
            os.makedirs(config.LOG_DIR, exist_ok=True)
        
        self._config = LoggingConfig.get_default_config()
        
        logging.config.dictConfig(self._config)
        
        root_logger = logging.getLogger()
        root_logger.setLevel(LoggingConfig.get_level(config.LOG_LEVEL))
        
        if app:
            self._register_middleware(app)
        
        self._initialized = True
    
    def _register_middleware(self, app) -> None:
        """注册Flask中间件
        
        Args:
            app: Flask应用实例
        """
        @app.before_request
        def before_request():
            """请求前处理"""
            g.start_time = time.time()
            g.request_id = self._generate_request_id()
        
        @app.after_request
        def after_request(response):
            """请求后处理"""
            if hasattr(g, 'start_time'):
                duration = time.time() - g.start_time
                
                from app.utils.auth import get_current_user_id
                logger = self.get_logger('app.request')
                logger.log_request({
                    'method': request.method,
                    'url': request.url,
                    'path': request.path,
                    'user_id': get_current_user_id(),
                    'ip': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'duration': duration,
                    'status_code': response.status_code,
                    'request_id': getattr(g, 'request_id', None),
                })
                
                response.headers['X-Request-ID'] = getattr(g, 'request_id', '')
                response.headers['X-Response-Time'] = f"{duration:.3f}s"
            
            return response
    
    def _generate_request_id(self) -> str:
        """生成请求ID
        
        Returns:
            str: 请求ID
        """
        import uuid
        return str(uuid.uuid4())[:8]
    
    def get_logger(self, name: str) -> UnifiedLogger:
        """获取日志记录器"""
        if name not in self._loggers:
            python_logger = logging.getLogger(name)
            self._loggers[name] = UnifiedLogger(name, python_logger)
        
        return self._loggers[name]
    
    def create_logger(self, name: str, level: LogLevel = LogLevel.INFO, 
                     handlers: List = None) -> UnifiedLogger:
        """创建日志记录器"""
        python_logger = logging.getLogger(name)
        python_logger.setLevel(LoggingConfig.get_level(level.value))
        
        if handlers:
            for handler in handlers:
                python_logger.addHandler(handler)
        
        unified_logger = UnifiedLogger(name, python_logger)
        self._loggers[name] = unified_logger
        
        return unified_logger
    
    def configure_logging(self, config: Dict[str, Any]) -> None:
        """配置日志系统"""
        logging.config.dictConfig(config)
        self._config = config
    
    def get_log_files(self) -> List[str]:
        """获取日志文件列表"""
        log_files = []
        if os.path.exists(config.LOG_DIR):
            for filename in os.listdir(config.LOG_DIR):
                if filename.endswith('.log') or filename.endswith('.json'):
                    log_files.append(os.path.join(config.LOG_DIR, filename))
        return log_files
    
    def rotate_logs(self) -> None:
        """轮转日志文件"""
        for logger in self._loggers.values():
            for handler in logger.get_handlers():
                if hasattr(handler, 'doRollover'):
                    handler.doRollover()
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """清理旧日志文件"""
        import glob
        import time
        
        cleaned_count = 0
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        
        log_pattern = os.path.join(config.LOG_DIR, '*.log*')
        for log_file in glob.glob(log_pattern):
            try:
                if os.path.getmtime(log_file) < cutoff_time:
                    os.remove(log_file)
                    cleaned_count += 1
            except OSError:
                pass
        
        return cleaned_count
    
    def get_log_statistics(self) -> Dict[str, Any]:
        """获取日志统计信息"""
        stats = {
            'total_logs': 0,
            'error_count': 0,
            'warning_count': 0,
            'log_size': 0,
            'log_files': []
        }
        
        log_files = self.get_log_files()
        for log_file in log_files:
            try:
                file_size = os.path.getsize(log_file)
                stats['log_size'] += file_size
                stats['log_files'].append({
                    'name': os.path.basename(log_file),
                    'size': file_size,
                    'modified': os.path.getmtime(log_file)
                })
                
                if log_file.endswith('.log'):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            stats['total_logs'] += 1
                            if 'ERROR' in line:
                                stats['error_count'] += 1
                            elif 'WARNING' in line:
                                stats['warning_count'] += 1
            except (OSError, UnicodeDecodeError):
                pass
        
        return stats
    
    def search_logs(self, query: str, start_time: Optional[int] = None, 
                   end_time: Optional[int] = None, 
                   level: Optional[LogLevel] = None) -> List[Dict[str, Any]]:
        """搜索日志"""
        results = []
        
        log_files = self.get_log_files()
        for log_file in log_files:
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        if query.lower() in line.lower():
                            if level and level.value not in line:
                                continue
                            
                            results.append({
                                'file': os.path.basename(log_file),
                                'line': line_num,
                                'content': line.strip(),
                                'timestamp': None  # 需要解析时间戳
                            })
            except (OSError, UnicodeDecodeError):
                pass
        
        return results


log_manager = UnifiedLogManager()

logging_manager = log_manager


def get_logger(name: str = None) -> UnifiedLogger:
    """获取日志记录器的便捷函数
    
    Args:
        name: 记录器名称，默认为调用模块名
        
    Returns:
        UnifiedLogger: 统一日志记录器
    """
    if name is None:
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'unknown')
    
    return log_manager.get_logger(name)


def log_execution_time(logger_name: str = None):
    """记录函数执行时间的装饰器
    
    Args:
        logger_name: 日志记录器名称
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name or f"{func.__module__}.{func.__name__}")
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                elapsed_time = time.time() - start_time
                
                logger.info(
                    f"函数执行完成: {func.__name__}",
                    extra={
                        'function': func.__name__,
                        'module': func.__module__,
                        'elapsed_time': elapsed_time,
                        'args_count': len(args),
                        'kwargs_count': len(kwargs)
                    }
                )
                
                return result
            except Exception as e:
                elapsed_time = time.time() - start_time
                
                logger.error(
                    f"函数执行失败: {func.__name__}",
                    extra={
                        'function': func.__name__,
                        'module': func.__module__,
                        'elapsed_time': elapsed_time,
                        'error_type': type(e).__name__,
                        'error_message': str(e)
                    }
                )
                raise
        
        return wrapper
    return decorator