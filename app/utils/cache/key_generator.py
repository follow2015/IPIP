# -*- coding: utf-8 -*-
"""
缓存键生成器实现

提供统一的缓存键生成规范。
"""
import hashlib
from typing import Any, Dict

from app.interfaces.cache import CacheKeyGenerator


class StandardCacheKeyGenerator(CacheKeyGenerator):
    """标准缓存键生成器
    
    实现统一的缓存键命名规范。
    """
    
    PREFIXES = {
        "user": "user",
        "session": "session", 
        "token": "token",
        "rate_limit": "rate_limit",
        "room": "room",
        "cabinet": "cabinet",
        "device": "device",
        "customer": "customer",
        "statistics": "stats",
        "search": "search",
        "qr_login": "qr_login",
        "wechat": "wechat"
    }
    
    def user_key(self, user_id: int) -> str:
        """生成用户缓存键"""
        return f"{self.PREFIXES['user']}:{user_id}"
    
    def user_session_key(self, user_id: int) -> str:
        """生成用户会话缓存键"""
        return f"{self.PREFIXES['user']}:{user_id}:{self.PREFIXES['session']}"
    
    def token_key(self, token: str) -> str:
        """生成令牌缓存键"""
        if len(token) > 50:
            token_hash = hashlib.md5(token.encode()).hexdigest()
            return f"{self.PREFIXES['token']}:{token_hash}"
        return f"{self.PREFIXES['token']}:{token}"
    
    def token_revoked_key(self, token: str) -> str:
        """生成撤销令牌缓存键"""
        token_key = self.token_key(token).replace(f"{self.PREFIXES['token']}:", "")
        return f"{self.PREFIXES['token']}:revoked:{token_key}"
    
    def rate_limit_key(self, identifier: str, endpoint: str) -> str:
        """生成频率限制缓存键"""
        return f"{self.PREFIXES['rate_limit']}:{identifier}:{endpoint}"
    
    def entity_key(self, entity_type: str, entity_id: int) -> str:
        """生成实体缓存键"""
        prefix = self.PREFIXES.get(entity_type, entity_type)
        return f"{prefix}:{entity_id}"
    
    def list_key(self, entity_type: str, filters: Dict[str, Any] = None) -> str:
        """生成列表缓存键"""
        prefix = self.PREFIXES.get(entity_type, entity_type)
        key_parts = [prefix, "list"]
        
        if filters:
            sorted_filters = sorted(filters.items())
            filter_parts = [f"{k}={v}" for k, v in sorted_filters]
            key_parts.extend(filter_parts)
        
        return ":".join(key_parts)
    
    def custom_key(self, namespace: str, *args, **kwargs) -> str:
        """生成自定义缓存键"""
        key_parts = [namespace]
        
        key_parts.extend(str(arg) for arg in args)
        
        if kwargs:
            sorted_kwargs = sorted(kwargs.items())
            key_parts.extend(f"{k}={v}" for k, v in sorted_kwargs)
        
        return ":".join(key_parts)
    
    
    def qr_login_key(self, scene_id: str) -> str:
        """生成二维码登录缓存键"""
        return f"{self.PREFIXES['qr_login']}:{scene_id}"
    
    def room_key(self, room_id: int) -> str:
        """生成机房缓存键"""
        return self.entity_key("room", room_id)
    
    def room_list_key(self, page: int = 1, page_size: int = 20, **filters) -> str:
        """生成机房列表缓存键"""
        filters.update({"page": page, "page_size": page_size})
        return self.list_key("room", filters)
    
    def cabinet_key(self, cabinet_id: int) -> str:
        """生成机柜缓存键"""
        return self.entity_key("cabinet", cabinet_id)
    
    def cabinet_layout_key(self, cabinet_id: int) -> str:
        """生成机柜布局缓存键"""
        return f"{self.PREFIXES['cabinet']}:layout:{cabinet_id}"
    
    def device_key(self, device_id: int) -> str:
        """生成设备缓存键"""
        return self.entity_key("device", device_id)
    
    def device_statistics_key(self) -> str:
        """生成设备统计缓存键"""
        return f"{self.PREFIXES['device']}:{self.PREFIXES['statistics']}"
    
    def customer_key(self, customer_id: int) -> str:
        """生成客户缓存键"""
        return self.entity_key("customer", customer_id)
    
    def customer_resources_key(self, customer_id: int) -> str:
        """生成客户资源缓存键"""
        return f"{self.PREFIXES['customer']}:resources:{customer_id}"
    
    def search_key(self, entity_type: str, keyword: str, **params) -> str:
        """生成搜索结果缓存键"""
        keyword_hash = hashlib.md5(keyword.encode()).hexdigest()[:8]
        key_parts = [self.PREFIXES['search'], entity_type, keyword_hash]
        
        if params:
            sorted_params = sorted(params.items())
            key_parts.extend(f"{k}={v}" for k, v in sorted_params)
        
        return ":".join(key_parts)
    
    def port_detail_key(self, switch_id: int, port_number: int) -> str:
        """生成端口详情缓存键"""
        return f"port_detail:{switch_id}:{port_number}"
    
    def wechat_cache_key(self, cache_type: str, identifier: str = None) -> str:
        """生成微信相关缓存键"""
        if identifier:
            return f"{self.PREFIXES['wechat']}:{cache_type}:{identifier}"
        return f"{self.PREFIXES['wechat']}:{cache_type}"
    
    
    def get_invalidation_pattern(self, entity_type: str, entity_id: int = None) -> str:
        """生成缓存失效模式
        
        Args:
            entity_type: 实体类型
            entity_id: 实体ID，为None时失效该类型的所有缓存
            
        Returns:
            str: 失效模式（支持通配符*）
        """
        prefix = self.PREFIXES.get(entity_type, entity_type)
        if entity_id is not None:
            return f"{prefix}:{entity_id}:*"
        return f"{prefix}:*"
    
    def get_user_invalidation_pattern(self, user_id: int = None) -> str:
        """生成用户相关缓存失效模式"""
        if user_id is not None:
            return f"{self.PREFIXES['user']}:{user_id}:*"
        return f"{self.PREFIXES['user']}:*"
    
    def get_token_invalidation_pattern(self, token_prefix: str = None) -> str:
        """生成令牌相关缓存失效模式"""
        if token_prefix:
            return f"{self.PREFIXES['token']}:{token_prefix}*"
        return f"{self.PREFIXES['token']}:*"