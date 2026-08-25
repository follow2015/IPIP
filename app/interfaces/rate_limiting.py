# -*- coding: utf-8 -*-
"""
频率限制接口定义

定义频率限制功能的统一接口，支持多种存储后端和限制策略。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Callable


class RateLimitStorage(ABC):
    
    @abstractmethod
    def check_limit(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        pass
    
    @abstractmethod
    def reset_limit(self, key: str) -> bool:
        pass
    
    @abstractmethod
    def get_current_count(self, key: str) -> int:
        pass
    
    @abstractmethod
    def get_remaining_count(self, key: str, limit: int) -> int:
        pass
    
    @abstractmethod
    def get_reset_time(self, key: str) -> Optional[int]:
        pass
    
    @abstractmethod
    def cleanup_expired(self) -> int:
        pass


class RateLimiter(ABC):
    
    @abstractmethod
    def is_allowed(self, key: str, limit: int, window: int) -> Tuple[bool, Dict[str, Any]]:
        pass
    
    @abstractmethod
    def reset(self, key: str) -> bool:
        pass
    
    @abstractmethod
    def get_limit_info(self, key: str, limit: int, window: int) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def parse_limit_string(self, limit_string: str) -> Tuple[int, int]:
        pass
    
    @abstractmethod
    def get_client_identifier(self, request_context: Any = None) -> str:
        pass
    
    @abstractmethod
    def limit_decorator(self, limit_string: str, 
                       key_func: Optional[Callable] = None,
                       error_handler: Optional[Callable] = None):
        pass


class RateLimitStrategy(ABC):
    
    @abstractmethod
    def check_limit(self, storage: RateLimitStorage, key: str, 
                   limit: int, window: int) -> Tuple[bool, int]:
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        pass
    
    @abstractmethod
    def get_strategy_config(self) -> Dict[str, Any]:
        pass


class RateLimitRule(ABC):
    
    @abstractmethod
    def get_limit_for_endpoint(self, endpoint: str, user_role: str = None) -> Optional[Tuple[int, int]]:
        pass
    
    @abstractmethod
    def get_limit_for_user(self, user_id: int, endpoint: str = None) -> Optional[Tuple[int, int]]:
        pass
    
    @abstractmethod
    def is_endpoint_limited(self, endpoint: str) -> bool:
        pass
    
    @abstractmethod
    def is_user_exempt(self, user_id: int) -> bool:
        pass
    
    @abstractmethod
    def add_rule(self, rule_config: Dict[str, Any]) -> bool:
        pass
    
    @abstractmethod
    def remove_rule(self, rule_id: str) -> bool:
        pass
    
    @abstractmethod
    def get_all_rules(self) -> List[Dict[str, Any]]:
        pass


class RateLimitMonitor(ABC):
    
    @abstractmethod
    def record_request(self, key: str, endpoint: str, allowed: bool, 
                      limit_info: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    def get_statistics(self, time_range: Tuple[int, int] = None) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_client_statistics(self, client_key: str, 
                            time_range: Tuple[int, int] = None) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_endpoint_statistics(self, endpoint: str, 
                              time_range: Tuple[int, int] = None) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_alerts(self) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def cleanup_old_records(self, days: int = 30) -> int:
        pass
