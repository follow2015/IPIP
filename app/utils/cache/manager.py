# -*- coding: utf-8 -*-
"""
统一缓存管理器实现

提供多级缓存、缓存策略等高级功能。
"""
from app.utils.logging import get_logger
import threading
import time
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable, Dict, Optional, List
from dataclasses import asdict

from app.interfaces.cache import CacheManager, CacheStorage, CacheKeyGenerator, CacheStrategy
from app.utils.cache.storages import RedisCacheStorage, MemoryCacheStorage
from app.utils.cache.key_generator import StandardCacheKeyGenerator
from app.utils.cache.strategies import TTLCacheStrategy
from app.utils.cache.advanced_strategies import HybridCacheStrategy
from app.utils.cache.monitoring import CacheMonitor, CacheEvent
from app.utils.concurrency.locks import ReadWriteLock

logger = get_logger(__name__)

_CACHE_MISS = object()

_MAX_KEY_LOCKS = 4096


class UnifiedCacheManager(CacheManager):
    
    def __init__(self, 
                 primary_storage: CacheStorage = None,
                 secondary_storage: CacheStorage = None,
                 key_generator: CacheKeyGenerator = None,
                 strategy: CacheStrategy = None,
                 enable_monitoring: bool = True,
                 enable_advanced_strategies: bool = True):
        self.primary_storage = primary_storage or RedisCacheStorage()
        self.secondary_storage = secondary_storage or MemoryCacheStorage()
        self.key_generator = key_generator or StandardCacheKeyGenerator()
        
        if enable_advanced_strategies:
            self.strategy = strategy or HybridCacheStrategy()
        else:
            self.strategy = strategy or TTLCacheStrategy()
        
        self.cache_levels = {
            "L1": self.secondary_storage,
            "L2": self.primary_storage,
        }
        
        self._lock = ReadWriteLock()
        self._stats_lock = threading.RLock()

        self._key_locks: "OrderedDict[str, threading.Lock]" = OrderedDict()
        self._key_locks_lock = threading.RLock()
        
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'errors': 0
        }
        
        self.monitoring_enabled = enable_monitoring
        if enable_monitoring:
            self.monitor = CacheMonitor()
            logger.info("缓存监控系统已启用")
        else:
            self.monitor = None
        
        if enable_advanced_strategies and isinstance(self.strategy, HybridCacheStrategy):
            self.multi_level_strategy = self.strategy.multi_level
            self.smart_invalidation = self.strategy.smart_invalidation
            self.warmup_strategy = self.strategy.warmup
        else:
            self.multi_level_strategy = None
            self.smart_invalidation = None
            self.warmup_strategy = None
        
        logger.info("统一缓存管理器初始化完成")
    
    def get(self, key: str, default: Any = None) -> Any:
        start_time = time.time()

        try:
            value = self.secondary_storage.get(key, _CACHE_MISS)
            if value is not _CACHE_MISS:
                execution_time = time.time() - start_time
                self.strategy.on_hit(key, value)
                self._record_event('hit', key, 'L1', execution_time, value)
                logger.debug(f"L1缓存命中: {key}")
                return value

            value = self.primary_storage.get(key, _CACHE_MISS)
            if value is not _CACHE_MISS:
                ttl = self.primary_storage.get_ttl(key)
                if ttl > 0:
                    self.secondary_storage.set(key, value, min(ttl, 300))

                execution_time = time.time() - start_time
                self.strategy.on_hit(key, value)
                self._record_event('hit', key, 'L2', execution_time, value)
                logger.debug(f"L2缓存命中: {key}")
                return value

            execution_time = time.time() - start_time
            self.strategy.on_miss(key)
            self._record_event('miss', key, 'unknown', execution_time)
            return default
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"获取缓存失败: {key}, 错误: {e}")
            self._record_event('error', key, 'unknown', execution_time, error_message=str(e))
            return default
    
    def set(self, key: str, value: Any, ttl: int = None, level: str = None) -> bool:
        start_time = time.time()
        
        try:
            if not self.strategy.should_cache(key, value):
                logger.debug(f"策略决定不缓存: {key}")
                return False
            
            actual_ttl = ttl or self.strategy.get_ttl(key, value)
            
            success = True
            
            if level is None or level == "L2":
                if not self.primary_storage.set(key, value, actual_ttl):
                    success = False
                    logger.warning(f"L2缓存设置失败: {key}")
            
            if level is None or level == "L1":
                l1_ttl = min(actual_ttl or 300, 300) if actual_ttl else 300
                if not self.secondary_storage.set(key, value, l1_ttl):
                    logger.warning(f"L1缓存设置失败: {key}")
            
            if success:
                execution_time = time.time() - start_time
                self.strategy.on_set(key, value, actual_ttl)
                self._record_event('set', key, level or 'L1+L2', execution_time, value)
            
            return success
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"设置缓存失败: {key}, 错误: {e}")
            self._record_event('error', key, level or 'unknown', execution_time, error_message=str(e))
            return False
    
    def delete(self, key: str) -> bool:
        start_time = time.time()
        
        try:
            success_l1 = self.secondary_storage.delete(key)
            success_l2 = self.primary_storage.delete(key)
            
            if success_l1 or success_l2:
                execution_time = time.time() - start_time
                self.strategy.on_delete(key)
                self._record_event('delete', key, 'L1+L2', execution_time)
                
                if self.smart_invalidation:
                    invalidation_keys = self.smart_invalidation.get_invalidation_keys(key)
                    for inv_key in invalidation_keys:
                        try:
                            self.delete(inv_key)
                        except Exception as e:
                            logger.warning(f"智能失效删除相关缓存失败: {inv_key}, 错误: {e}")
                
                return True
            
            return False
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"删除缓存失败: {key}, 错误: {e}")
            self._record_event('error', key, 'unknown', execution_time, error_message=str(e))
            return False
    
    def invalidate_pattern(self, pattern: str) -> int:
        count_l1 = self.secondary_storage.delete_pattern(pattern)
        count_l2 = self.primary_storage.delete_pattern(pattern)
        
        total_count = count_l1 + count_l2
        if total_count > 0:
            logger.info(f"模式失效缓存: {pattern}, 删除数量: L1={count_l1}, L2={count_l2}")
        
        return total_count

    def _get_key_lock(self, key: str) -> threading.Lock:
        with self._key_locks_lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._key_locks[key] = lock
            self._key_locks.move_to_end(key)
            while len(self._key_locks) > _MAX_KEY_LOCKS:
                self._key_locks.popitem(last=False)
            return lock

    def get_or_set(self, key: str, callback: Callable, ttl: int = None) -> Any:
        value = self.get(key, _CACHE_MISS)
        if value is not _CACHE_MISS:
            return value

        key_lock = self._get_key_lock(key)
        with key_lock:
            value = self.get(key, _CACHE_MISS)
            if value is not _CACHE_MISS:
                return value

            try:
                value = callback()
                self.set(key, value, ttl)
                return value
            except Exception as e:
                logger.error(f"回调函数执行失败 (key={key}): {e}", exc_info=True)
                return None
    
    def remember(self, key: str, ttl: int = None):
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                cache_key = key
                if "{" in key and "}" in key:
                    import inspect
                    sig = inspect.signature(func)
                    bound_args = sig.bind(*args, **kwargs)
                    bound_args.apply_defaults()
                    cache_key = key.format(**bound_args.arguments)
                
                return self.get_or_set(cache_key, lambda: func(*args, **kwargs), ttl)
            
            return wrapper
        return decorator
    
    def forget(self, key: str) -> bool:
        return self.delete(key)
    
    def flush(self, namespace: str = None) -> bool:
        if namespace:
            pattern = f"{namespace}:*"
            return self.invalidate_pattern(pattern) > 0
        else:
            success_l1 = self.secondary_storage.clear_all()
            success_l2 = self.primary_storage.clear_all()
            return success_l1 or success_l2
    
    def get_storage(self, level: str = None) -> CacheStorage:
        if level is None:
            return self.primary_storage
        
        return self.cache_levels.get(level, self.primary_storage)
    
    def get_key_generator(self) -> CacheKeyGenerator:
        return self.key_generator
    
    def exists(self, key: str) -> bool:
        return (self.secondary_storage.exists(key) or 
                self.primary_storage.exists(key))
    
    def get_ttl(self, key: str) -> int:
        ttl = self.primary_storage.get_ttl(key)
        if ttl > -2:
            return ttl
        
        return self.secondary_storage.get_ttl(key)
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        result = self.primary_storage.increment(key, amount)
        
        if result is not None:
            self.secondary_storage.set(key, result, 300)
        
        return result
    
    def get_many(self, keys: list) -> Dict[str, Any]:
        result = {}
        missing_keys = []
        
        l1_result = self.secondary_storage.get_many(keys)
        result.update(l1_result)
        
        for key in keys:
            if key not in l1_result:
                missing_keys.append(key)
        
        if missing_keys:
            l2_result = self.primary_storage.get_many(missing_keys)
            result.update(l2_result)
            
            if l2_result:
                self.secondary_storage.set_many(l2_result, 300)
        
        return result
    
    def set_many(self, mapping: Dict[str, Any], ttl: int = None) -> bool:
        filtered_mapping = {}
        for key, value in mapping.items():
            if self.strategy.should_cache(key, value):
                filtered_mapping[key] = value
        
        if not filtered_mapping:
            return True
        
        actual_ttl = ttl or self.strategy.get_ttl(list(filtered_mapping.keys())[0], None)
        
        success_l2 = self.primary_storage.set_many(filtered_mapping, actual_ttl)
        
        l1_ttl = min(actual_ttl or 300, 300)
        success_l1 = self.secondary_storage.set_many(filtered_mapping, l1_ttl)
        
        return success_l2 or success_l1
    
    def _record_event(self, event_type: str, key: str, cache_level: str = 'unknown', 
                     execution_time: float = 0.0, value: Any = None, error_message: str = "") -> None:
        if not self.monitoring_enabled or not self.monitor:
            return
        
        try:
            data_size = 0
            if value is not None:
                data_size = self._estimate_data_size(value)
            
            event = CacheEvent(
                timestamp=time.time(),
                event_type=event_type,
                key=key,
                cache_level=cache_level,
                execution_time=execution_time,
                data_size=data_size,
                error_message=error_message
            )
            
            self.monitor.record_event(event)
            
        except Exception as e:
            logger.warning(f"记录缓存事件失败: {e}")
    
    def _estimate_data_size(self, value: Any) -> int:
        try:
            import sys
            return sys.getsizeof(value)
        except Exception:
            return 0
    
    
    def add_cache_dependency(self, key: str, depends_on: List[str]) -> None:
        if self.smart_invalidation:
            self.smart_invalidation.add_dependency(key, depends_on)
            logger.debug(f"添加缓存依赖: {key} -> {depends_on}")
    
    def add_cache_tags(self, key: str, tags: List[str]) -> None:
        if self.smart_invalidation:
            self.smart_invalidation.add_tag(key, tags)
            logger.debug(f"添加缓存标签: {key} -> {tags}")
    
    def register_warmup_task(self, key_pattern: str, data_loader: Callable[[], Any],
                           priority: int = 1, schedule: str = "startup") -> None:
        if self.warmup_strategy:
            self.warmup_strategy.register_warmup_task(key_pattern, data_loader, priority, schedule)
            logger.info(f"注册缓存预热任务: {key_pattern}")
    
    def execute_warmup(self, schedule: str = "startup") -> Dict[str, Any]:
        if self.warmup_strategy:
            return self.warmup_strategy.execute_warmup(schedule)
        return {'error': '预热策略未启用'}
    
    def invalidate_by_tags(self, tags: List[str]) -> int:
        if not self.smart_invalidation:
            return 0
        
        total_invalidated = 0
        for tag in tags:
            tagged_keys = self.smart_invalidation.tag_to_keys.get(tag, [])
            for key in tagged_keys:
                if self.delete(key):
                    total_invalidated += 1
        
        logger.info(f"根据标签失效缓存: {tags}, 失效数量: {total_invalidated}")
        return total_invalidated
    
    def get_stats(self) -> Dict[str, Any]:
        l1_stats = self.secondary_storage.get_stats()
        l2_stats = self.primary_storage.get_stats()
        
        stats = {
            "L1_cache": l1_stats,
            "L2_cache": l2_stats,
            "strategy": self.strategy.__class__.__name__
        }
        
        if hasattr(self.strategy, 'get_statistics'):
            stats["strategy_stats"] = self.strategy.get_statistics()
        
        return stats

    def get_cache_metrics(self) -> Dict[str, Any]:
        metrics = {}
        
        metrics['basic_stats'] = self.get_stats()
        
        metrics['storage_stats'] = {
            'L1': self.secondary_storage.get_stats(),
            'L2': self.primary_storage.get_stats()
        }
        
        if hasattr(self.strategy, 'get_comprehensive_stats'):
            metrics['strategy_stats'] = self.strategy.get_comprehensive_stats()
        
        if self.monitoring_enabled and self.monitor:
            metrics['monitoring_stats'] = self.monitor.get_current_metrics()
        
        return metrics
    
    def get_monitoring_report(self, hours: int = 1) -> Dict[str, Any]:
        if not self.monitoring_enabled or not self.monitor:
            return {'error': '监控系统未启用'}
        
        end_time = time.time()
        start_time = end_time - (hours * 3600)
        
        return self.monitor.generate_report(start_time, end_time)
    
    def get_cache_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.monitoring_enabled or not self.monitor:
            return []
        
        alerts = self.monitor.get_alerts(limit=limit)
        return [asdict(alert) for alert in alerts]
    
    
    def cache_user(self, user_id: int, user_data: Dict[str, Any], ttl: int = None) -> bool:
        key = self.key_generator.user_key(user_id)
        return self.set(key, user_data, ttl)
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        key = self.key_generator.user_key(user_id)
        return self.get(key)
    
    def invalidate_user(self, user_id: int) -> int:
        total = self.invalidate_pattern(self.key_generator.user_key(user_id))
        total += self.invalidate_pattern(
            self.key_generator.get_user_invalidation_pattern(user_id)
        )
        return total
    
    def cache_token(self, token: str, token_data: Dict[str, Any], ttl: int = None) -> bool:
        key = self.key_generator.token_key(token)
        return self.set(key, token_data, ttl)
    
    def revoke_token(self, token: str, ttl: int = None) -> bool:
        key = self.key_generator.token_revoked_key(token)
        return self.set(key, True, ttl)
    
    def is_token_revoked(self, token: str) -> bool:
        key = self.key_generator.token_revoked_key(token)
        return self.exists(key)
    
    def cache_qr_login(self, scene_id: str, qr_data: Dict[str, Any], ttl: int = None) -> bool:
        key = self.key_generator.qr_login_key(scene_id)
        return self.set(key, qr_data, ttl)
    
    def get_qr_login(self, scene_id: str) -> Optional[Dict[str, Any]]:
        key = self.key_generator.qr_login_key(scene_id)
        return self.get(key)
    
    def delete_qr_login(self, scene_id: str) -> bool:
        key = self.key_generator.qr_login_key(scene_id)
        return self.delete(key)


from app.utils.concurrency.locks import singleton

@singleton
class GlobalCacheManager(UnifiedCacheManager):
    pass


def get_cache_manager() -> UnifiedCacheManager:
    return GlobalCacheManager()


cache_manager = get_cache_manager()


def cached(key_pattern: str = None, ttl: int = None):
    return cache_manager.remember(key_pattern or "cached_func", ttl)
