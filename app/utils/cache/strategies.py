# -*- coding: utf-8 -*-
"""
缓存策略实现

定义不同的缓存策略（TTL、LRU等）。
"""
from app.utils.logging import get_logger
from typing import Any, Dict, Optional

from config import get_config

from app.interfaces.cache import CacheStrategy

logger = get_logger(__name__)
config = get_config()


class TTLCacheStrategy(CacheStrategy):
    """基于TTL的缓存策略
    
    根据数据类型和业务场景设置不同的过期时间。
    """
    
    TTL_CONFIG = {
        "room": getattr(config, 'CACHE_TTL_ROOM', 3600),  # 机房: 1小时
        "customer": getattr(config, 'CACHE_TTL_CUSTOMER', 3600),  # 客户: 1小时
        "user": getattr(config, 'CACHE_TTL_USER_SESSION', 86400),  # 用户: 24小时
        "cabinet": getattr(config, 'CACHE_TTL_CABINET', 1800),  # 机柜: 30分钟
        "device": getattr(config, 'CACHE_TTL_DEVICE', 900),  # 设备: 15分钟
        "session": getattr(config, 'CACHE_TTL_USER_SESSION', 86400),  # 用户会话: 24小时
        "token": 3600,  # JWT令牌: 1小时
        "token_revoked": 7200,  # 撤销令牌: 2小时
        "qr_login": 300,  # 二维码登录: 5分钟
        "statistics": 600,  # 统计数据: 10分钟
        "dashboard": 300,  # 仪表板数据: 5分钟
        "search": 180,  # 搜索结果: 3分钟
        "list": 300,  # 列表数据: 5分钟
        "relation": 900,  # 关系数据: 15分钟
        "layout": 600,  # 布局数据: 10分钟
        "port_detail": 1800,  # 端口详情: 30分钟
        "wechat": 3600,  # 微信缓存: 1小时
        "default": getattr(config, 'CACHE_DEFAULT_TIMEOUT', 3600)
    }
    
    NULL_CACHE_TTL = 60

    def __init__(self, custom_ttl: Dict[str, int] = None):
        """初始化TTL缓存策略

        Args:
            custom_ttl: 自定义TTL配置
        """
        self.ttl_config = self.TTL_CONFIG.copy()
        if custom_ttl:
            self.ttl_config.update(custom_ttl)

    def should_cache(self, key: str, value: Any) -> bool:
        """判断是否应该缓存

        允许缓存 None/空值以防止缓存穿透，但使用短 TTL。
        """
        return True

    def is_null_value(self, value: Any) -> bool:
        """判断是否为空值（None/空字符串/空列表/空字典）"""
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, (list, dict)) and not value:
            return True
        return False

    def get_ttl(self, key: str, value: Any) -> Optional[int]:
        """获取缓存过期时间

        空值使用短 TTL 防穿透，正常值按数据类型配置。
        """
        if self.is_null_value(value):
            return self.NULL_CACHE_TTL

        key_parts = key.split(":")
        if not key_parts:
            return self.ttl_config["default"]

        data_type = key_parts[0]

        if len(key_parts) >= 2 and key_parts[0] == "token" and key_parts[1] == "revoked":
            return self.ttl_config["token_revoked"]

        return self.ttl_config.get(data_type, self.ttl_config["default"])
    
    def on_hit(self, key: str, value: Any) -> None:
        """缓存命中时的回调"""
        logger.debug(f"缓存命中: {key}")
    
    def on_miss(self, key: str) -> None:
        """缓存未命中时的回调"""
        logger.debug(f"缓存未命中: {key}")
    
    def on_set(self, key: str, value: Any, ttl: int = None) -> None:
        """设置缓存时的回调"""
        actual_ttl = ttl or self.get_ttl(key, value)
        logger.debug(f"设置缓存: {key}, TTL: {actual_ttl}秒")
    
    def on_delete(self, key: str) -> None:
        """删除缓存时的回调"""
        logger.debug(f"删除缓存: {key}")


class LRUCacheStrategy(CacheStrategy):
    """LRU缓存策略
    
    最近最少使用的缓存淘汰策略。
    """
    
    def __init__(self, max_size: int = 1000):
        """初始化LRU缓存策略
        
        Args:
            max_size: 最大缓存条目数
        """
        self.max_size = max_size
        self.access_count = {}
        self.access_order = []
    
    def should_cache(self, key: str, value: Any) -> bool:
        """判断是否应该缓存"""
        if len(self.access_order) >= self.max_size:
            if self.access_order:
                oldest_key = self.access_order.pop(0)
                self.access_count.pop(oldest_key, None)
                logger.debug(f"LRU淘汰缓存键: {oldest_key}")
        
        return value is not None
    
    def get_ttl(self, key: str, value: Any) -> Optional[int]:
        """获取缓存过期时间"""
        return None
    
    def on_hit(self, key: str, value: Any) -> None:
        """缓存命中时的回调"""
        self.access_count[key] = self.access_count.get(key, 0) + 1
        
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)
        
        logger.debug(f"LRU缓存命中: {key}, 访问次数: {self.access_count[key]}")
    
    def on_miss(self, key: str) -> None:
        """缓存未命中时的回调"""
        logger.debug(f"LRU缓存未命中: {key}")
    
    def on_set(self, key: str, value: Any, ttl: int = None) -> None:
        """设置缓存时的回调"""
        self.access_count[key] = 1
        if key not in self.access_order:
            self.access_order.append(key)
        
        logger.debug(f"LRU设置缓存: {key}")
    
    def on_delete(self, key: str) -> None:
        """删除缓存时的回调"""
        self.access_count.pop(key, None)
        if key in self.access_order:
            self.access_order.remove(key)
        
        logger.debug(f"LRU删除缓存: {key}")


class AdaptiveCacheStrategy(CacheStrategy):
    """自适应缓存策略
    
    根据访问模式动态调整缓存策略。
    """
    
    def __init__(self):
        """初始化自适应缓存策略"""
        self.hit_count = {}
        self.miss_count = {}
        self.ttl_strategy = TTLCacheStrategy()
    
    def should_cache(self, key: str, value: Any) -> bool:
        """判断是否应该缓存"""
        hit_rate = self._get_hit_rate(key)
        
        if hit_rate > 0.7:
            return True
        elif hit_rate > 0.3:
            return value is not None
        else:
            return value is not None and self._is_valuable_data(value)
    
    def get_ttl(self, key: str, value: Any) -> Optional[int]:
        """获取缓存过期时间"""
        base_ttl = self.ttl_strategy.get_ttl(key, value)
        hit_rate = self._get_hit_rate(key)
        
        if hit_rate > 0.8:
            return int(base_ttl * 1.5)
        elif hit_rate < 0.2:
            return int(base_ttl * 0.5)
        else:
            return base_ttl
    
    def on_hit(self, key: str, value: Any) -> None:
        """缓存命中时的回调"""
        self.hit_count[key] = self.hit_count.get(key, 0) + 1
        logger.debug(f"自适应缓存命中: {key}, 命中率: {self._get_hit_rate(key):.2f}")
    
    def on_miss(self, key: str) -> None:
        """缓存未命中时的回调"""
        self.miss_count[key] = self.miss_count.get(key, 0) + 1
        logger.debug(f"自适应缓存未命中: {key}, 命中率: {self._get_hit_rate(key):.2f}")
    
    def on_set(self, key: str, value: Any, ttl: int = None) -> None:
        """设置缓存时的回调"""
        logger.debug(f"自适应设置缓存: {key}")
    
    def on_delete(self, key: str) -> None:
        """删除缓存时的回调"""
        logger.debug(f"自适应删除缓存: {key}")
    
    def _get_hit_rate(self, key: str) -> float:
        """获取键的命中率"""
        hits = self.hit_count.get(key, 0)
        misses = self.miss_count.get(key, 0)
        total = hits + misses
        
        if total == 0:
            return 0.0
        
        return hits / total
    
    def _is_valuable_data(self, value: Any) -> bool:
        """判断数据是否有价值"""
        if value is None:
            return False
        
        if isinstance(value, (list, dict, str)) and not value:
            return False
        
        if isinstance(value, str) and len(value) > 10000:
            return False
        
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取策略统计信息"""
        total_hits = sum(self.hit_count.values())
        total_misses = sum(self.miss_count.values())
        total_requests = total_hits + total_misses
        
        overall_hit_rate = 0.0
        if total_requests > 0:
            overall_hit_rate = total_hits / total_requests
        
        return {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "total_requests": total_requests,
            "overall_hit_rate": round(overall_hit_rate, 4),
            "tracked_keys": len(set(list(self.hit_count.keys()) + list(self.miss_count.keys())))
        }