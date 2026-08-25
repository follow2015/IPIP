# -*- coding: utf-8 -*-
"""
并发安全装饰器

提供各种并发安全的装饰器，简化线程安全代码的编写。
"""
import threading
import time
import functools
from typing import Callable, Optional, TypeVar
from app.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


def synchronized(lock: Optional[threading.Lock] = None):
    """同步装饰器
    
    为方法或函数添加同步锁，确保同一时间只有一个线程可以执行。
    
    Args:
        lock: 可选的锁对象，如果不提供则创建新锁
        
    Returns:
        Callable: 装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        func_lock = lock or threading.RLock()
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with func_lock:
                return func(*args, **kwargs)
        
        wrapper._lock = func_lock
        return wrapper
    
    return decorator


def retry_on_conflict(max_retries: int = 3, 
                     delay: float = 0.1, 
                     backoff: float = 2.0,
                     exceptions: tuple = (Exception,)):
    """冲突重试装饰器
    
    当发生指定异常时自动重试，支持指数退避。
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间
        backoff: 退避倍数
        exceptions: 需要重试的异常类型
        
    Returns:
        Callable: 装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"函数 {func.__name__} 第{attempt + 1}次执行失败: {e}, "
                            f"{current_delay:.2f}秒后重试"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"函数 {func.__name__} 重试{max_retries}次后仍然失败: {e}"
                        )
            
            raise last_exception
        
        return wrapper
    
    return decorator


def atomic_operation(isolation_level: str = "READ_COMMITTED"):
    """原子操作装饰器
    
    确保被装饰的函数在数据库事务中执行，支持事务隔离级别设置。
    
    Args:
        isolation_level: 事务隔离级别
        
    Returns:
        Callable: 装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from extensions import db
            
            if db.session.in_transaction():
                return func(*args, **kwargs)
            
            try:
                if hasattr(db.session, 'execute'):
                    VALID_ISOLATION_LEVELS = {
                        "READ_COMMITTED", "READ_UNCOMMITTED",
                        "REPEATABLE_READ", "SERIALIZABLE",
                    }
                    normalized = isolation_level.upper().replace(" ", "_")
                    if normalized not in VALID_ISOLATION_LEVELS:
                        raise ValueError(f"无效的事务隔离级别: {isolation_level}")
                    from sqlalchemy import text
                    db.session.execute(text(f"SET TRANSACTION ISOLATION LEVEL {normalized}"))
                
                result = func(*args, **kwargs)
                db.session.commit()
                return result
                
            except Exception as e:
                db.session.rollback()
                logger.error(f"原子操作失败，已回滚: {e}")
                raise
        
        return wrapper
    
    return decorator


def rate_limited(calls_per_second: float = 10.0, 
                burst_size: int = None):
    """频率限制装饰器
    
    限制函数的调用频率，支持令牌桶算法。
    
    Args:
        calls_per_second: 每秒允许的调用次数
        burst_size: 突发调用大小，默认为calls_per_second的2倍
        
    Returns:
        Callable: 装饰器函数
    """
    burst_size = burst_size or int(calls_per_second * 2)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        bucket_size = burst_size
        tokens = bucket_size
        last_update = time.time()
        lock = threading.RLock()
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal tokens, last_update
            
            with lock:
                now = time.time()
                tokens = min(bucket_size, tokens + (now - last_update) * calls_per_second)
                last_update = now
                
                if tokens >= 1:
                    tokens -= 1
                    return func(*args, **kwargs)
                else:
                    wait_time = (1 - tokens) / calls_per_second
                    raise RuntimeError(f"调用频率过高，请等待 {wait_time:.2f} 秒")
        
        return wrapper
    
    return decorator


def timeout(seconds: float):
    """超时装饰器

    为函数执行设置超时时间。使用线程 + Event 实现，兼容多线程环境
    （signal.SIGALRM 仅在主线程可用，Flask 工作线程中会抛 ValueError）。

    Args:
        seconds: 超时时间（秒）

    Returns:
        Callable: 装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result_container = [None]
            exception_container = [None]

            def target():
                try:
                    result_container[0] = func(*args, **kwargs)
                except Exception as e:
                    exception_container[0] = e

            worker = threading.Thread(target=target, daemon=True)
            worker.start()
            worker.join(timeout=seconds)

            if worker.is_alive():
                raise TimeoutError(f"函数 {func.__name__} 执行超时 ({seconds}秒)")

            if exception_container[0] is not None:
                raise exception_container[0]

            return result_container[0]

        return wrapper

    return decorator


def thread_local_cache(max_size: int = 128):
    """线程本地缓存装饰器
    
    为每个线程维护独立的函数结果缓存。
    
    Args:
        max_size: 缓存最大大小
        
    Returns:
        Callable: 装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        local_storage = threading.local()
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not hasattr(local_storage, 'cache'):
                local_storage.cache = {}
                local_storage.access_order = []
            
            cache = local_storage.cache
            access_order = local_storage.access_order
            
            cache_key = (args, tuple(sorted(kwargs.items())))
            
            if cache_key in cache:
                access_order.remove(cache_key)
                access_order.append(cache_key)
                return cache[cache_key]
            
            result = func(*args, **kwargs)
            
            cache[cache_key] = result
            access_order.append(cache_key)
            
            if len(cache) > max_size:
                oldest_key = access_order.pop(0)
                del cache[oldest_key]
            
            return result
        
        def clear_cache():
            if hasattr(local_storage, 'cache'):
                local_storage.cache.clear()
                local_storage.access_order.clear()
        
        wrapper.clear_cache = clear_cache
        return wrapper
    
    return decorator


def monitor_performance(log_slow_calls: bool = True, 
                       slow_threshold: float = 1.0):
    """性能监控装饰器
    
    监控函数执行时间，记录慢调用。
    
    Args:
        log_slow_calls: 是否记录慢调用
        slow_threshold: 慢调用阈值（秒）
        
    Returns:
        Callable: 装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        stats = {
            'call_count': 0,
            'total_time': 0.0,
            'min_time': float('inf'),
            'max_time': 0.0,
            'slow_calls': 0
        }
        stats_lock = threading.RLock()
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                
                with stats_lock:
                    stats['call_count'] += 1
                    stats['total_time'] += duration
                    stats['min_time'] = min(stats['min_time'], duration)
                    stats['max_time'] = max(stats['max_time'], duration)
                    
                    if duration > slow_threshold:
                        stats['slow_calls'] += 1
                        if log_slow_calls:
                            logger.warning(
                                f"慢调用检测: {func.__name__} 执行时间 {duration:.3f}秒 "
                                f"(阈值: {slow_threshold}秒)"
                            )
        
        def get_stats():
            with stats_lock:
                avg_time = stats['total_time'] / stats['call_count'] if stats['call_count'] > 0 else 0
                return {
                    **stats,
                    'avg_time': avg_time,
                    'slow_call_rate': stats['slow_calls'] / stats['call_count'] if stats['call_count'] > 0 else 0
                }
        
        def reset_stats():
            with stats_lock:
                stats.update({
                    'call_count': 0,
                    'total_time': 0.0,
                    'min_time': float('inf'),
                    'max_time': 0.0,
                    'slow_calls': 0
                })
        
        wrapper.get_stats = get_stats
        wrapper.reset_stats = reset_stats
        return wrapper
    
    return decorator


def circuit_breaker(failure_threshold: int = 5,
                   recovery_timeout: float = 60.0,
                   expected_exception: type = Exception):
    """断路器装饰器
    
    当连续失败次数达到阈值时，暂时停止调用函数，避免级联失败。
    
    Args:
        failure_threshold: 失败阈值
        recovery_timeout: 恢复超时时间
        expected_exception: 预期的异常类型
        
    Returns:
        Callable: 装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        state = {
            'failure_count': 0,
            'last_failure_time': None,
            'state': 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        }
        lock = threading.RLock()
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                now = time.time()
                
                if (state['state'] == 'OPEN' and 
                    state['last_failure_time'] and
                    now - state['last_failure_time'] > recovery_timeout):
                    state['state'] = 'HALF_OPEN'
                    logger.info(f"断路器 {func.__name__} 进入半开状态")
                
                if state['state'] == 'OPEN':
                    raise RuntimeError(f"断路器 {func.__name__} 处于开启状态，拒绝调用")
                
                try:
                    result = func(*args, **kwargs)
                    
                    if state['failure_count'] > 0:
                        state['failure_count'] = 0
                        if state['state'] == 'HALF_OPEN':
                            state['state'] = 'CLOSED'
                            logger.info(f"断路器 {func.__name__} 恢复到关闭状态")
                    
                    return result
                    
                except expected_exception as e:
                    state['failure_count'] += 1
                    state['last_failure_time'] = now
                    
                    if state['failure_count'] >= failure_threshold:
                        state['state'] = 'OPEN'
                        logger.error(
                            f"断路器 {func.__name__} 开启，连续失败 {state['failure_count']} 次"
                        )
                    
                    raise
        
        def get_state():
            with lock:
                return state.copy()
        
        def reset():
            with lock:
                state.update({
                    'failure_count': 0,
                    'last_failure_time': None,
                    'state': 'CLOSED'
                })
        
        wrapper.get_state = get_state
        wrapper.reset = reset
        return wrapper
    
    return decorator