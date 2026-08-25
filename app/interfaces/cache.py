# -*- coding: utf-8 -*-
"""
缓存接口定义

定义缓存管理的统一接口，支持多种缓存后端和策略。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union


class CacheStorage(ABC):
    """缓存存储接口
    
    定义缓存存储的基本操作，支持不同的存储后端（Redis、内存等）。
    """
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值
        
        Args:
            key: 缓存键
            default: 默认值
            
        Returns:
            Any: 缓存值，不存在则返回default
        """
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
            
        Returns:
            bool: 设置成功返回True
        """
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 删除成功返回True
        """
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """检查缓存是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 存在返回True
        """
        pass
    
    @abstractmethod
    def get_ttl(self, key: str) -> int:
        """获取缓存剩余过期时间
        
        Args:
            key: 缓存键
            
        Returns:
            int: 剩余秒数，-1表示永不过期，-2表示不存在
        """
        pass
    
    @abstractmethod
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """增加计数器
        
        Args:
            key: 缓存键
            amount: 增加量
            
        Returns:
            Optional[int]: 增加后的值
        """
        pass
    
    @abstractmethod
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """批量获取缓存
        
        Args:
            keys: 缓存键列表
            
        Returns:
            Dict[str, Any]: 键值对字典
        """
        pass
    
    @abstractmethod
    def set_many(self, mapping: Dict[str, Any], ttl: int = None) -> bool:
        """批量设置缓存
        
        Args:
            mapping: 键值对字典
            ttl: 过期时间（秒）
            
        Returns:
            bool: 设置成功返回True
        """
        pass
    
    @abstractmethod
    def delete_pattern(self, pattern: str) -> int:
        """根据模式删除缓存
        
        Args:
            pattern: 键名模式（支持通配符*）
            
        Returns:
            int: 删除的键数量
        """
        pass
    
    @abstractmethod
    def clear_all(self) -> bool:
        """清空所有缓存
        
        Returns:
            bool: 清空成功返回True
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        pass


class CacheKeyGenerator(ABC):
    """缓存键生成器接口
    
    提供统一的缓存键生成规范。
    """
    
    @abstractmethod
    def user_key(self, user_id: int) -> str:
        """生成用户缓存键
        
        Args:
            user_id: 用户ID
            
        Returns:
            str: 缓存键
        """
        pass
    
    @abstractmethod
    def user_session_key(self, user_id: int) -> str:
        """生成用户会话缓存键
        
        Args:
            user_id: 用户ID
            
        Returns:
            str: 缓存键
        """
        pass
    
    @abstractmethod
    def token_key(self, token: str) -> str:
        """生成令牌缓存键
        
        Args:
            token: 令牌
            
        Returns:
            str: 缓存键
        """
        pass
    
    @abstractmethod
    def rate_limit_key(self, identifier: str, endpoint: str) -> str:
        """生成频率限制缓存键
        
        Args:
            identifier: 标识符（IP或用户ID）
            endpoint: 端点名称
            
        Returns:
            str: 缓存键
        """
        pass
    
    @abstractmethod
    def entity_key(self, entity_type: str, entity_id: int) -> str:
        """生成实体缓存键
        
        Args:
            entity_type: 实体类型
            entity_id: 实体ID
            
        Returns:
            str: 缓存键
        """
        pass
    
    @abstractmethod
    def list_key(self, entity_type: str, filters: Dict[str, Any] = None) -> str:
        """生成列表缓存键
        
        Args:
            entity_type: 实体类型
            filters: 过滤条件
            
        Returns:
            str: 缓存键
        """
        pass
    
    @abstractmethod
    def custom_key(self, namespace: str, *args, **kwargs) -> str:
        """生成自定义缓存键
        
        Args:
            namespace: 命名空间
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            str: 缓存键
        """
        pass


class CacheManager(ABC):
    """缓存管理器接口
    
    提供高级缓存管理功能，包括多级缓存、缓存策略等。
    """
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值（支持多级缓存）
        
        Args:
            key: 缓存键
            default: 默认值
            
        Returns:
            Any: 缓存值
        """
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = None, 
            level: str = None) -> bool:
        """设置缓存值（支持多级缓存）
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
            level: 缓存级别（L1, L2, L3等）
            
        Returns:
            bool: 设置成功返回True
        """
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除缓存（所有级别）
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 删除成功返回True
        """
        pass
    
    @abstractmethod
    def invalidate_pattern(self, pattern: str) -> int:
        """根据模式失效缓存
        
        Args:
            pattern: 键名模式
            
        Returns:
            int: 失效的键数量
        """
        pass
    
    @abstractmethod
    def get_or_set(self, key: str, callback, ttl: int = None) -> Any:
        """获取缓存值，不存在则通过回调函数设置
        
        Args:
            key: 缓存键
            callback: 回调函数，用于生成缓存值
            ttl: 过期时间（秒）
            
        Returns:
            Any: 缓存值
        """
        pass
    
    @abstractmethod
    def remember(self, key: str, ttl: int = None):
        """缓存装饰器
        
        Args:
            key: 缓存键模式
            ttl: 过期时间（秒）
            
        Returns:
            装饰器函数
        """
        pass
    
    @abstractmethod
    def forget(self, key: str) -> bool:
        """忘记缓存（别名：delete）
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 删除成功返回True
        """
        pass
    
    @abstractmethod
    def flush(self, namespace: str = None) -> bool:
        """清空缓存
        
        Args:
            namespace: 命名空间，为None则清空所有
            
        Returns:
            bool: 清空成功返回True
        """
        pass
    
    @abstractmethod
    def get_storage(self, level: str = None) -> CacheStorage:
        """获取指定级别的缓存存储
        
        Args:
            level: 缓存级别
            
        Returns:
            CacheStorage: 缓存存储实例
        """
        pass
    
    @abstractmethod
    def get_key_generator(self) -> CacheKeyGenerator:
        """获取缓存键生成器
        
        Returns:
            CacheKeyGenerator: 键生成器实例
        """
        pass


class CacheStrategy(ABC):
    """缓存策略接口
    
    定义不同的缓存策略（LRU、LFU、TTL等）。
    """
    
    @abstractmethod
    def should_cache(self, key: str, value: Any) -> bool:
        """判断是否应该缓存
        
        Args:
            key: 缓存键
            value: 缓存值
            
        Returns:
            bool: 应该缓存返回True
        """
        pass
    
    @abstractmethod
    def get_ttl(self, key: str, value: Any) -> Optional[int]:
        """获取缓存过期时间
        
        Args:
            key: 缓存键
            value: 缓存值
            
        Returns:
            Optional[int]: 过期时间（秒），None表示使用默认值
        """
        pass
    
    @abstractmethod
    def on_hit(self, key: str, value: Any) -> None:
        """缓存命中时的回调
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        pass
    
    @abstractmethod
    def on_miss(self, key: str) -> None:
        """缓存未命中时的回调
        
        Args:
            key: 缓存键
        """
        pass
    
    @abstractmethod
    def on_set(self, key: str, value: Any, ttl: int = None) -> None:
        """设置缓存时的回调
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间
        """
        pass
    
    @abstractmethod
    def on_delete(self, key: str) -> None:
        """删除缓存时的回调
        
        Args:
            key: 缓存键
        """
        pass