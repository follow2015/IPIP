# -*- coding: utf-8 -*-
"""
缓存接口定义

定义缓存管理的统一接口，支持多种缓存后端和策略。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union


class CacheStorage(ABC):
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        pass
    
    @abstractmethod
    def get_ttl(self, key: str) -> int:
        pass
    
    @abstractmethod
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        pass
    
    @abstractmethod
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def set_many(self, mapping: Dict[str, Any], ttl: int = None) -> bool:
        pass
    
    @abstractmethod
    def delete_pattern(self, pattern: str) -> int:
        pass
    
    @abstractmethod
    def clear_all(self) -> bool:
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        pass


class CacheKeyGenerator(ABC):
    
    @abstractmethod
    def user_key(self, user_id: int) -> str:
        pass
    
    @abstractmethod
    def user_session_key(self, user_id: int) -> str:
        pass
    
    @abstractmethod
    def token_key(self, token: str) -> str:
        pass
    
    @abstractmethod
    def rate_limit_key(self, identifier: str, endpoint: str) -> str:
        pass
    
    @abstractmethod
    def entity_key(self, entity_type: str, entity_id: int) -> str:
        pass
    
    @abstractmethod
    def list_key(self, entity_type: str, filters: Dict[str, Any] = None) -> str:
        pass
    
    @abstractmethod
    def custom_key(self, namespace: str, *args, **kwargs) -> str:
        pass


class CacheManager(ABC):
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = None, 
            level: str = None) -> bool:
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        pass
    
    @abstractmethod
    def invalidate_pattern(self, pattern: str) -> int:
        pass
    
    @abstractmethod
    def get_or_set(self, key: str, callback, ttl: int = None) -> Any:
        pass
    
    @abstractmethod
    def remember(self, key: str, ttl: int = None):
        pass
    
    @abstractmethod
    def forget(self, key: str) -> bool:
        pass
    
    @abstractmethod
    def flush(self, namespace: str = None) -> bool:
        pass
    
    @abstractmethod
    def get_storage(self, level: str = None) -> CacheStorage:
        pass
    
    @abstractmethod
    def get_key_generator(self) -> CacheKeyGenerator:
        pass


class CacheStrategy(ABC):
    
    @abstractmethod
    def should_cache(self, key: str, value: Any) -> bool:
        pass
    
    @abstractmethod
    def get_ttl(self, key: str, value: Any) -> Optional[int]:
        pass
    
    @abstractmethod
    def on_hit(self, key: str, value: Any) -> None:
        pass
    
    @abstractmethod
    def on_miss(self, key: str) -> None:
        pass
    
    @abstractmethod
    def on_set(self, key: str, value: Any, ttl: int = None) -> None:
        pass
    
    @abstractmethod
    def on_delete(self, key: str) -> None:
        pass
