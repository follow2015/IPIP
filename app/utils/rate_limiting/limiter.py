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
    
    def __init__(self, storage: Optional[RateLimitStorage] = None,
                 strategy: Optional[RateLimitStrategy] = None,
                 fail_close: bool = True):
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
        try:
            redis_storage = RedisRateLimitStorage()
            redis_storage.redis_client.ping()
            logger.info("统一频率限制器: 使用Redis存储")
            return redis_storage
        except Exception as e:
            logger.warning(f"统一频率限制器: Redis不可用，降级到内存存储: {str(e)}")
            return MemoryRateLimitStorage()
    
    def is_allowed(self, key: str, limit: int, window: int) -> Tuple[bool, Dict[str, Any]]:
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
        try:
            return self.storage.reset_limit(key)
        except Exception as e:
            logger.error(f"频率限制重置失败: key={key}, error={str(e)}", exc_info=True)
            return False
    
    def get_limit_info(self, key: str, limit: int, window: int) -> Dict[str, Any]:
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
        patterns = [
            r'(\d+)\s+per\s+(second|minute|hour|day)',
            r'(\d+)/(\d+)s',
            r'(\d+)/(\d+)m',
            r'(\d+)/(\d+)h',
            r'(\d+)/(\d+)d',
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
        allowed, limit_info = self.is_allowed(key, max_attempts, window_seconds)
        
        if allowed:
            return False, None
        else:
            return True, limit_info.get('retry_after', window_seconds)
    
    def reset_limit(self, key: str) -> bool:
        return self.reset(key)
    
    def get_remaining_attempts(self, key: str, max_attempts: int = 5) -> int:
        return self.storage.get_remaining_count(key, max_attempts)
    
    def get_reset_time(self, key: str) -> Optional[int]:
        return self.storage.get_reset_time(key)
    
    def limit(self, limit_string: str, key_func: Optional[Callable] = None):
        return self.limit_decorator(limit_string, key_func)
