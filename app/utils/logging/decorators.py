# -*- coding: utf-8 -*-
"""
日志装饰器模块

提供各种日志记录装饰器，用于自动记录函数执行、异常处理等。
"""
import functools
import time
from typing import Callable, Optional

from app.utils.logging.manager import get_logger


def _get_current_user_id():
    """延迟导入避免循环依赖: auth → logging → decorators → auth"""
    from app.utils.auth import get_current_user_id
    return get_current_user_id()


def log_function_call(
    logger_name: Optional[str] = None,
    log_args: bool = False,
    log_result: bool = False,
    log_execution_time: bool = True,
    level: str = 'INFO'
) -> Callable:
    """记录函数调用的装饰器
    
    Args:
        logger_name: 日志记录器名称
        log_args: 是否记录函数参数
        log_result: 是否记录函数返回值
        log_execution_time: 是否记录执行时间
        level: 日志级别
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name or f"{func.__module__}.{func.__name__}")
            
            extra_info = {
                'function': func.__name__,
                'module': func.__module__,
            }
            
            if log_args:
                extra_info.update({
                    'args': args,
                    'kwargs': kwargs,
                    'args_count': len(args),
                    'kwargs_count': len(kwargs)
                })
            
            start_time = time.time() if log_execution_time else None
            
            try:
                logger.log(
                    getattr(logger._logger, level.lower(), logger.info),
                    f"开始执行函数: {func.__name__}",
                    extra=extra_info
                )
                
                result = func(*args, **kwargs)
                
                if start_time:
                    elapsed_time = time.time() - start_time
                    extra_info['elapsed_time'] = elapsed_time
                
                if log_result:
                    extra_info['result'] = result
                
                logger.log(
                    getattr(logger._logger, level.lower(), logger.info),
                    f"函数执行成功: {func.__name__}",
                    extra=extra_info
                )
                
                return result
                
            except Exception as e:
                if start_time:
                    elapsed_time = time.time() - start_time
                    extra_info['elapsed_time'] = elapsed_time
                
                extra_info.update({
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                })
                
                logger.error(
                    f"函数执行失败: {func.__name__}",
                    extra=extra_info
                )
                
                raise
        
        return wrapper
    return decorator


def log_database_operation(
    operation_type: str,
    logger_name: Optional[str] = None
) -> Callable:
    """记录数据库操作的装饰器
    
    Args:
        operation_type: 操作类型 (CREATE, READ, UPDATE, DELETE)
        logger_name: 日志记录器名称
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name or f"{func.__module__}.database")
            
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                elapsed_time = time.time() - start_time
                
                logger.log_database_query({
                    'operation_type': operation_type,
                    'function': func.__name__,
                    'module': func.__module__,
                    'duration': elapsed_time,
                    'success': True
                })
                
                return result
                
            except Exception as e:
                elapsed_time = time.time() - start_time
                
                logger.log_database_query({
                    'operation_type': operation_type,
                    'function': func.__name__,
                    'module': func.__module__,
                    'duration': elapsed_time,
                    'success': False,
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                })
                
                raise
        
        return wrapper
    return decorator


def log_cache_operation(
    operation_type: str,
    logger_name: Optional[str] = None
) -> Callable:
    """记录缓存操作的装饰器
    
    Args:
        operation_type: 操作类型 (GET, SET, DELETE)
        logger_name: 日志记录器名称
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name or f"{func.__module__}.cache")
            
            cache_key = None
            if args:
                cache_key = str(args[0]) if args else None
            
            try:
                result = func(*args, **kwargs)
                
                operation_info = {
                    'operation': operation_type,
                    'function': func.__name__,
                    'key': cache_key
                }
                
                if operation_type.upper() == 'GET':
                    operation_info['hit'] = result is not None
                
                logger.log_cache_operation(operation_info)
                
                return result
                
            except Exception as e:
                logger.error(
                    f"缓存操作失败: {operation_type}",
                    extra={
                        'operation': operation_type,
                        'function': func.__name__,
                        'key': cache_key,
                        'error_type': type(e).__name__,
                        'error_message': str(e)
                    }
                )
                
                raise
        
        return wrapper
    return decorator


def log_api_endpoint(
    endpoint_name: Optional[str] = None,
    logger_name: Optional[str] = None,
    log_request_data: bool = False,
    log_response_data: bool = False
) -> Callable:
    """记录API端点调用的装饰器
    
    Args:
        endpoint_name: 端点名称
        logger_name: 日志记录器名称
        log_request_data: 是否记录请求数据
        log_response_data: 是否记录响应数据
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from flask import request, g
            
            logger = get_logger(logger_name or f"{func.__module__}.api")
            
            start_time = time.time()
            endpoint = endpoint_name or func.__name__
            
            request_info = {
                'endpoint': endpoint,
                'method': request.method,
                'path': request.path,
                'user_id': _get_current_user_id(),
                'ip': request.remote_addr,
                'user_agent': request.headers.get('User-Agent', ''),
                'request_id': getattr(g, 'request_id', None)
            }
            
            if log_request_data and request.is_json:
                request_info['request_data'] = request.get_json()
            
            try:
                result = func(*args, **kwargs)
                elapsed_time = time.time() - start_time
                
                status_code = 200
                if hasattr(result, 'status_code'):
                    status_code = result.status_code
                elif isinstance(result, tuple) and len(result) > 1:
                    status_code = result[1]
                
                request_info.update({
                    'duration': elapsed_time,
                    'status_code': status_code,
                    'success': True
                })
                
                if log_response_data:
                    request_info['response_data'] = result
                
                logger.log_request(request_info)
                
                return result
                
            except Exception as e:
                elapsed_time = time.time() - start_time
                
                request_info.update({
                    'duration': elapsed_time,
                    'status_code': 500,
                    'success': False,
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                })
                
                logger.log_request(request_info)
                
                raise
        
        return wrapper
    return decorator


def log_authentication_attempt(
    auth_type: str = 'login',
    logger_name: Optional[str] = None
) -> Callable:
    """记录认证尝试的装饰器
    
    Args:
        auth_type: 认证类型
        logger_name: 日志记录器名称
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from flask import request, g
            
            logger = get_logger(logger_name or f"{func.__module__}.auth")
            
            username = None
            if args and hasattr(args[0], 'get'):
                username = args[0].get('username')
            elif kwargs:
                username = kwargs.get('username')
            
            try:
                result = func(*args, **kwargs)
                
                success = True
                user_id = None
                
                if isinstance(result, dict):
                    success = result.get('success', True)
                    user_id = result.get('user_id')
                elif hasattr(result, 'id'):
                    user_id = result.id
                
                auth_info = {
                    'username': username,
                    'user_id': user_id,
                    'auth_type': auth_type,
                    'success': success,
                    'ip': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'request_id': getattr(g, 'request_id', None)
                }
                
                logger.log_authentication(auth_info)
                
                return result
                
            except Exception as e:
                auth_info = {
                    'username': username,
                    'auth_type': auth_type,
                    'success': False,
                    'ip': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'request_id': getattr(g, 'request_id', None),
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                }
                
                logger.log_authentication(auth_info)
                
                raise
        
        return wrapper
    return decorator


def log_security_event(
    event_type: str,
    severity: str = 'medium',
    logger_name: Optional[str] = None
) -> Callable:
    """记录安全事件的装饰器
    
    Args:
        event_type: 事件类型
        severity: 严重程度 (low, medium, high, critical)
        logger_name: 日志记录器名称
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from flask import request, g
            
            logger = get_logger(logger_name or f"{func.__module__}.security")
            
            try:
                result = func(*args, **kwargs)
                
                event_info = {
                    'event_type': event_type,
                    'severity': severity,
                    'function': func.__name__,
                    'user_id': _get_current_user_id(),
                    'ip': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'request_id': getattr(g, 'request_id', None),
                    'details': {
                        'args_count': len(args),
                        'kwargs_count': len(kwargs)
                    }
                }
                
                logger.log_security_event(event_info)
                
                return result
                
            except Exception as e:
                event_info = {
                    'event_type': f"{event_type}_error",
                    'severity': 'high',
                    'function': func.__name__,
                    'user_id': _get_current_user_id(),
                    'ip': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'request_id': getattr(g, 'request_id', None),
                    'details': {
                        'error_type': type(e).__name__,
                        'error_message': str(e)
                    }
                }
                
                logger.log_security_event(event_info)
                
                raise
        
        return wrapper
    return decorator


def log_performance_critical(
    threshold_seconds: float = 1.0,
    logger_name: Optional[str] = None
) -> Callable:
    """记录性能关键操作的装饰器
    
    Args:
        threshold_seconds: 性能阈值（秒）
        logger_name: 日志记录器名称
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name or f"{func.__module__}.performance")
            
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                elapsed_time = time.time() - start_time
                
                if elapsed_time > threshold_seconds:
                    logger.warning(
                        f"性能警告: 函数执行时间超过阈值",
                        extra={
                            'function': func.__name__,
                            'module': func.__module__,
                            'elapsed_time': elapsed_time,
                            'threshold': threshold_seconds,
                            'args_count': len(args),
                            'kwargs_count': len(kwargs)
                        }
                    )
                else:
                    logger.debug(
                        f"性能监控: 函数执行正常",
                        extra={
                            'function': func.__name__,
                            'module': func.__module__,
                            'elapsed_time': elapsed_time,
                            'threshold': threshold_seconds
                        }
                    )
                
                return result
                
            except Exception as e:
                elapsed_time = time.time() - start_time
                
                logger.error(
                    f"性能监控: 函数执行异常",
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