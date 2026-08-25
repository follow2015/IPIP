# -*- coding: utf-8 -*-
"""
频率限制接口定义

定义频率限制功能的统一接口，支持多种存储后端和限制策略。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Callable


class RateLimitStorage(ABC):
    """频率限制存储接口
    
    定义频率限制数据存储的基本操作，支持不同的存储后端。
    """
    
    @abstractmethod
    def check_limit(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        """检查是否超过限制
        
        Args:
            key: 限制键
            limit: 允许的请求数量
            window: 时间窗口（秒）
            
        Returns:
            Tuple[bool, int]: (是否允许请求, 剩余请求数)
        """
        pass
    
    @abstractmethod
    def reset_limit(self, key: str) -> bool:
        """重置限制计数
        
        Args:
            key: 限制键
            
        Returns:
            bool: 重置成功返回True
        """
        pass
    
    @abstractmethod
    def get_current_count(self, key: str) -> int:
        """获取当前计数
        
        Args:
            key: 限制键
            
        Returns:
            int: 当前计数
        """
        pass
    
    @abstractmethod
    def get_remaining_count(self, key: str, limit: int) -> int:
        """获取剩余请求数
        
        Args:
            key: 限制键
            limit: 允许的请求数量
            
        Returns:
            int: 剩余请求数
        """
        pass
    
    @abstractmethod
    def get_reset_time(self, key: str) -> Optional[int]:
        """获取重置时间
        
        Args:
            key: 限制键
            
        Returns:
            Optional[int]: 重置时间的Unix时间戳，不存在返回None
        """
        pass
    
    @abstractmethod
    def cleanup_expired(self) -> int:
        """清理过期的限制记录
        
        Returns:
            int: 清理的记录数量
        """
        pass


class RateLimiter(ABC):
    """频率限制器接口
    
    提供请求频率限制的核心功能。
    """
    
    @abstractmethod
    def is_allowed(self, key: str, limit: int, window: int) -> Tuple[bool, Dict[str, Any]]:
        """检查请求是否被允许
        
        Args:
            key: 限制键（通常是IP地址或用户标识）
            limit: 时间窗口内允许的最大请求数
            window: 时间窗口大小（秒）
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (是否允许, 限制信息)
                限制信息包含：
                - allowed: 是否允许
                - limit: 限制数量
                - remaining: 剩余请求数
                - reset_time: 重置时间
                - retry_after: 重试等待时间（秒）
        """
        pass
    
    @abstractmethod
    def reset(self, key: str) -> bool:
        """重置指定键的限制
        
        Args:
            key: 限制键
            
        Returns:
            bool: 重置成功返回True
        """
        pass
    
    @abstractmethod
    def get_limit_info(self, key: str, limit: int, window: int) -> Dict[str, Any]:
        """获取限制信息
        
        Args:
            key: 限制键
            limit: 限制数量
            window: 时间窗口
            
        Returns:
            Dict[str, Any]: 限制信息
        """
        pass
    
    @abstractmethod
    def parse_limit_string(self, limit_string: str) -> Tuple[int, int]:
        """解析限制字符串
        
        Args:
            limit_string: 限制字符串，如 "100 per minute"
            
        Returns:
            Tuple[int, int]: (请求数量, 时间窗口秒数)
        """
        pass
    
    @abstractmethod
    def get_client_identifier(self, request_context: Any = None) -> str:
        """获取客户端标识符
        
        Args:
            request_context: 请求上下文
            
        Returns:
            str: 客户端标识符
        """
        pass
    
    @abstractmethod
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
        pass


class RateLimitStrategy(ABC):
    """频率限制策略接口
    
    定义不同的频率限制算法（滑动窗口、令牌桶、漏桶等）。
    """
    
    @abstractmethod
    def check_limit(self, storage: RateLimitStorage, key: str, 
                   limit: int, window: int) -> Tuple[bool, int]:
        """检查限制
        
        Args:
            storage: 存储后端
            key: 限制键
            limit: 限制数量
            window: 时间窗口
            
        Returns:
            Tuple[bool, int]: (是否允许, 剩余数量)
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """获取策略名称
        
        Returns:
            str: 策略名称
        """
        pass
    
    @abstractmethod
    def get_strategy_config(self) -> Dict[str, Any]:
        """获取策略配置
        
        Returns:
            Dict[str, Any]: 策略配置
        """
        pass


class RateLimitRule(ABC):
    """频率限制规则接口
    
    定义频率限制规则的管理。
    """
    
    @abstractmethod
    def get_limit_for_endpoint(self, endpoint: str, user_role: str = None) -> Optional[Tuple[int, int]]:
        """获取端点的限制配置
        
        Args:
            endpoint: 端点名称
            user_role: 用户角色
            
        Returns:
            Optional[Tuple[int, int]]: (限制数量, 时间窗口)，无限制返回None
        """
        pass
    
    @abstractmethod
    def get_limit_for_user(self, user_id: int, endpoint: str = None) -> Optional[Tuple[int, int]]:
        """获取用户的限制配置
        
        Args:
            user_id: 用户ID
            endpoint: 端点名称
            
        Returns:
            Optional[Tuple[int, int]]: (限制数量, 时间窗口)，无限制返回None
        """
        pass
    
    @abstractmethod
    def is_endpoint_limited(self, endpoint: str) -> bool:
        """检查端点是否有限制
        
        Args:
            endpoint: 端点名称
            
        Returns:
            bool: 有限制返回True
        """
        pass
    
    @abstractmethod
    def is_user_exempt(self, user_id: int) -> bool:
        """检查用户是否免于限制
        
        Args:
            user_id: 用户ID
            
        Returns:
            bool: 免于限制返回True
        """
        pass
    
    @abstractmethod
    def add_rule(self, rule_config: Dict[str, Any]) -> bool:
        """添加限制规则
        
        Args:
            rule_config: 规则配置
                - endpoint: 端点名称
                - limit: 限制数量
                - window: 时间窗口
                - user_role: 用户角色（可选）
                - priority: 优先级（可选）
                
        Returns:
            bool: 添加成功返回True
        """
        pass
    
    @abstractmethod
    def remove_rule(self, rule_id: str) -> bool:
        """移除限制规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            bool: 移除成功返回True
        """
        pass
    
    @abstractmethod
    def get_all_rules(self) -> List[Dict[str, Any]]:
        """获取所有限制规则
        
        Returns:
            List[Dict[str, Any]]: 规则列表
        """
        pass


class RateLimitMonitor(ABC):
    """频率限制监控接口
    
    提供频率限制的监控和统计功能。
    """
    
    @abstractmethod
    def record_request(self, key: str, endpoint: str, allowed: bool, 
                      limit_info: Dict[str, Any]) -> None:
        """记录请求
        
        Args:
            key: 限制键
            endpoint: 端点名称
            allowed: 是否被允许
            limit_info: 限制信息
        """
        pass
    
    @abstractmethod
    def get_statistics(self, time_range: Tuple[int, int] = None) -> Dict[str, Any]:
        """获取统计信息
        
        Args:
            time_range: 时间范围（开始时间戳, 结束时间戳）
            
        Returns:
            Dict[str, Any]: 统计信息
                - total_requests: 总请求数
                - blocked_requests: 被阻止的请求数
                - top_clients: 请求最多的客户端
                - top_endpoints: 请求最多的端点
        """
        pass
    
    @abstractmethod
    def get_client_statistics(self, client_key: str, 
                            time_range: Tuple[int, int] = None) -> Dict[str, Any]:
        """获取客户端统计信息
        
        Args:
            client_key: 客户端键
            time_range: 时间范围
            
        Returns:
            Dict[str, Any]: 客户端统计信息
        """
        pass
    
    @abstractmethod
    def get_endpoint_statistics(self, endpoint: str, 
                              time_range: Tuple[int, int] = None) -> Dict[str, Any]:
        """获取端点统计信息
        
        Args:
            endpoint: 端点名称
            time_range: 时间范围
            
        Returns:
            Dict[str, Any]: 端点统计信息
        """
        pass
    
    @abstractmethod
    def get_alerts(self) -> List[Dict[str, Any]]:
        """获取告警信息
        
        Returns:
            List[Dict[str, Any]]: 告警列表
        """
        pass
    
    @abstractmethod
    def cleanup_old_records(self, days: int = 30) -> int:
        """清理旧记录
        
        Args:
            days: 保留天数
            
        Returns:
            int: 清理的记录数量
        """
        pass