# -*- coding: utf-8 -*-
"""
统一频率限制器实现

提供统一的频率限制功能，整合多种存储后端和限制策略。
"""
from app.utils.logging import get_logger
import re
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

from flask import abort, g, request

from app.interfaces.rate_limiting import RateLimiter, RateLimitStorage, RateLimitStrategy
from app.utils.rate_limiting.storages import RedisRateLimitStorage, MemoryRateLimitStorage
from app.utils.rate_limiting.strategies import SlidingWindowStrategy
from config import get_config

logger = get_logger(__name__)
config = get_config()


class UnifiedRateLimiter(RateLimiter):
    """统一频率限制器
    
    整合了原有的两个频率限制器的功能，提供统一的接口。
    支持多种存储后端和限制策略。
    """
    
    def __init__(self, storage: Optional[RateLimitStorage] = None,
                 strategy: Optional[RateLimitStrategy] = None,
                 fail_close: bool = True):
        """初始化统一频率限制器

        Args:
            storage: 存储后端，如果为None则自动选择
            strategy: 限制策略，如果为None则使用滑动窗口策略
            fail_close: 异常时是否拒绝请求（True=安全优先，False=可用性优先）
                默认 True：Redis 不可用时拒绝请求，防止暴力破解绕过限流
        """
        self.enabled = getattr(config, 'RATELIMIT_ENABLED', True)
        self.fail_close = fail_close
        
        if storage is None:
            storage = self._create_default_storage()
        self.storage = storage
        
        if strategy is None:
            strategy = SlidingWindowStrategy()
        self.strategy = strategy
        
        logger.info(f"统一频率限制器: 初始化完成, storage={type(storage).__name__}, "
                   f"strategy={strategy.get_strategy_name()}, enabled={self.enabled}")
    
    def _create_default_storage(self) -> RateLimitStorage:
        """创建默认存储后端
        
        优先使用Redis，如果不可用则降级到内存存储。
        
        Returns:
            RateLimitStorage: 存储后端实例
        """
        try:
            redis_storage = RedisRateLimitStorage()
            redis_storage.redis_client.ping()
            logger.info("统一频率限制器: 使用Redis存储")
            return redis_storage
        except Exception as e:
            logger.warning(f"统一频率限制器: Redis不可用，降级到内存存储: {str(e)}")
            return MemoryRateLimitStorage()
    
    def is_allowed(self, key: str, limit: int, window: int) -> Tuple[bool, Dict[str, Any]]:
        """检查请求是否被允许
        
        Args:
            key: 限制键（通常是IP地址或用户标识）
            limit: 时间窗口内允许的最大请求数
            window: 时间窗口大小（秒）
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (是否允许, 限制信息)
        """
        if not self.enabled:
            return True, {
                'allowed': True,
                'limit': limit,
                'remaining': limit,
                'reset_time': None,
                'retry_after': 0
            }
        
        try:
            allowed, remaining = self.storage.check_limit(key, limit, window)
            reset_time = self.storage.get_reset_time(key)
            
            limit_info = {
                'allowed': allowed,
                'limit': limit,
                'remaining': remaining,
                'reset_time': reset_time,
                'retry_after': 0 if allowed else (reset_time - int(time.time()) if reset_time else window)
            }
            
            return allowed, limit_info
            
        except Exception as e:
            logger.error(f"频率限制检查失败: key={key}, error={str(e)}", exc_info=True)
            if self.fail_close:
                return False, {
                    'allowed': False,
                    'limit': limit,
                    'remaining': 0,
                    'reset_time': None,
                    'retry_after': 0,
                    'reason': 'rate_limit_error',
                }
            return True, {
                'allowed': True,
                'limit': limit,
                'remaining': limit,
                'reset_time': None,
                'retry_after': 0,
                'reason': 'rate_limit_error_fallback',
            }
    
    def reset(self, key: str) -> bool:
        """重置指定键的限制
        
        Args:
            key: 限制键
            
        Returns:
            bool: 重置成功返回True
        """
        try:
            return self.storage.reset_limit(key)
        except Exception as e:
            logger.error(f"频率限制重置失败: key={key}, error={str(e)}", exc_info=True)
            return False
    
    def get_limit_info(self, key: str, limit: int, window: int) -> Dict[str, Any]:
        """获取限制信息
        
        Args:
            key: 限制键
            limit: 限制数量
            window: 时间窗口
            
        Returns:
            Dict[str, Any]: 限制信息
        """
        try:
            current_count = self.storage.get_current_count(key)
            remaining = self.storage.get_remaining_count(key, limit)
            reset_time = self.storage.get_reset_time(key)
            
            return {
                'key': key,
                'limit': limit,
                'window': window,
                'current_count': current_count,
                'remaining': remaining,
                'reset_time': reset_time,
                'strategy': self.strategy.get_strategy_name(),
                'storage': type(self.storage).__name__
            }
            
        except Exception as e:
            logger.error(f"获取限制信息失败: key={key}, error={str(e)}", exc_info=True)
            return {
                'key': key,
                'limit': limit,
                'window': window,
                'current_count': 0,
                'remaining': limit,
                'reset_time': None,
                'strategy': self.strategy.get_strategy_name(),
                'storage': type(self.storage).__name__
            }
    
    def parse_limit_string(self, limit_string: str) -> Tuple[int, int]:
        """解析限制字符串
        
        Args:
            limit_string: 限制字符串，如 "100 per minute"
            
        Returns:
            Tuple[int, int]: (请求数量, 时间窗口秒数)
        """
        patterns = [
            r'(\d+)\s+per\s+(second|minute|hour|day)',
            r'(\d+)/(\d+)s',  # 100/60s
            r'(\d+)/(\d+)m',  # 100/1m  
            r'(\d+)/(\d+)h',  # 100/1h
            r'(\d+)/(\d+)d',  # 100/1d
        ]
        
        limit_string = limit_string.lower().strip()
        
        match = re.match(r'(\d+)\s+per\s+(second|minute|hour|day)', limit_string)
        if match:
            count = int(match.group(1))
            unit = match.group(2)
            
            unit_seconds = {
                'second': 1,
                'minute': 60, 
                'hour': 3600,
                'day': 86400
            }
            
            return count, unit_seconds[unit]
        
        for pattern in patterns[1:]:
            match = re.match(pattern, limit_string)
            if match:
                count = int(match.group(1))
                time_value = int(match.group(2))
                
                if 's' in pattern:
                    return count, time_value
                elif 'm' in pattern:
                    return count, time_value * 60
                elif 'h' in pattern:
                    return count, time_value * 3600
                elif 'd' in pattern:
                    return count, time_value * 86400
        
        raise ValueError(f"无效的限制字符串格式: {limit_string}")
    
    def get_client_identifier(self, request_context: Any = None) -> str:
        """获取客户端标识符
        
        Args:
            request_context: 请求上下文
            
        Returns:
            str: 客户端标识符
        """
        if hasattr(g, 'current_user') and g.current_user:
            user_id = g.current_user.get('user_id')
            if user_id:
                return f"user:{user_id}"
        
        if request_context is None and request:
            request_context = request
        
        if request_context:
            from flask import current_app
            trusted_proxies = current_app.config.get("TRUSTED_PROXIES", [])
            if trusted_proxies and hasattr(request_context, 'headers'):
                remote_addr = getattr(request_context, 'remote_addr', None)
                if remote_addr in trusted_proxies and request_context.headers.get('X-Forwarded-For'):
                    ip = request_context.headers.get('X-Forwarded-For').split(',')[0].strip()
                elif hasattr(request_context, 'remote_addr'):
                    ip = request_context.remote_addr
                else:
                    ip = 'unknown'
            elif hasattr(request_context, 'remote_addr'):
                ip = request_context.remote_addr
            else:
                ip = 'unknown'
        else:
            ip = 'unknown'
        
        return f"ip:{ip}"
    
    def limit_decorator(self, limit_string: str, 
                       key_func: Optional[Callable] = None,
                       error_handler: Optional[Callable] = None):
        """频率限制装饰器
        
        Args:
            limit_string: 限制字符串
            key_func: 自定义键生成函数
            error_handler: 自定义错误处理函数
            
        Returns:
            装饰器函数
        """
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                if not self.enabled:
                    return f(*args, **kwargs)
                
                try:
                    limit, window = self.parse_limit_string(limit_string)

                    if key_func:
                        key = key_func()
                    else:
                        client_id = self.get_client_identifier()
                        endpoint = getattr(request, 'endpoint', 'unknown') if request else 'unknown'
                        key = f"{client_id}:{endpoint}"

                    allowed, limit_info = self.is_allowed(key, limit, window)
                except Exception as e:
                    logger.error(f"频率限制装饰器执行失败: error={str(e)}", exc_info=True)
                    if self.fail_close:
                        abort(429, description="请求频率限制暂不可用，请稍后再试")
                    return f(*args, **kwargs)

                if not allowed:
                    logger.warning(f"请求频率超限: {key}, limit_info={limit_info}")

                    if error_handler:
                        return error_handler(limit_info)
                    else:
                        abort(429, description="请求过于频繁，请稍后再试")

                response = f(*args, **kwargs)

                if hasattr(response, 'headers'):
                    response.headers['X-RateLimit-Limit'] = str(limit_info['limit'])
                    response.headers['X-RateLimit-Remaining'] = str(limit_info['remaining'])
                    if limit_info['reset_time']:
                        response.headers['X-RateLimit-Reset'] = str(limit_info['reset_time'])

                return response
            
            return decorated_function
        return decorator
    
    def is_rate_limited(self, key: str, max_attempts: int = 5, 
                       window_seconds: int = 300) -> Tuple[bool, Optional[int]]:
        """检查是否触发频率限制（兼容原rate_limiter.py的API）
        
        Args:
            key: 限制键
            max_attempts: 最大尝试次数
            window_seconds: 时间窗口（秒）
            
        Returns:
            Tuple[bool, Optional[int]]: (是否触发限制, 剩余等待时间)
        """
        allowed, limit_info = self.is_allowed(key, max_attempts, window_seconds)
        
        if allowed:
            return False, None
        else:
            return True, limit_info.get('retry_after', window_seconds)
    
    def reset_limit(self, key: str) -> bool:
        """重置频率限制计数（兼容原rate_limiter.py的API）
        
        Args:
            key: 限制键
            
        Returns:
            bool: 操作是否成功
        """
        return self.reset(key)
    
    def get_remaining_attempts(self, key: str, max_attempts: int = 5) -> int:
        """获取剩余尝试次数（兼容原rate_limiter.py的API）
        
        Args:
            key: 限制键
            max_attempts: 最大尝试次数
            
        Returns:
            int: 剩余尝试次数
        """
        return self.storage.get_remaining_count(key, max_attempts)
    
    def get_reset_time(self, key: str) -> Optional[int]:
        """获取限制重置时间（兼容原rate_limiter.py的API）
        
        Args:
            key: 限制键
            
        Returns:
            Optional[int]: 重置时间的Unix时间戳
        """
        return self.storage.get_reset_time(key)
    
    def limit(self, limit_string: str, key_func: Optional[Callable] = None):
        """频率限制装饰器（兼容原rate_limit.py的API）
        
        Args:
            limit_string: 限制字符串
            key_func: 自定义键生成函数
            
        Returns:
            装饰器函数
        """
        return self.limit_decorator(limit_string, key_func)