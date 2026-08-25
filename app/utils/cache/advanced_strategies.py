# -*- coding: utf-8 -*-
"""
高级缓存策略实现

提供多级缓存、智能失效、预热等高级缓存功能。
"""
from app.utils.logging import get_logger
import threading
import time
from typing import Any, Dict, List, Optional, Set, Callable
from dataclasses import dataclass
from enum import Enum
import json
import hashlib

from app.interfaces.cache import CacheStrategy
from app.utils.concurrency.locks import ReadWriteLock, ThreadSafeDict
from app.utils.concurrency.decorators import monitor_performance

logger = get_logger(__name__)


class CacheLevel(Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


@dataclass
class CacheMetrics:
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    errors: int = 0
    total_size: int = 0
    avg_access_time: float = 0.0
    last_access_time: float = 0.0


class MultiLevelCacheStrategy(CacheStrategy):
    
    def __init__(self, 
                 l1_max_size: int = 1000,
                 l2_max_size: int = 10000,
                 promotion_threshold: int = 3,
                 demotion_threshold: int = 100):
        self.l1_max_size = l1_max_size
        self.l2_max_size = l2_max_size
        self.promotion_threshold = promotion_threshold
        self.demotion_threshold = demotion_threshold
        
        self.access_count = ThreadSafeDict()
        self.access_time = ThreadSafeDict()
        self.cache_level = ThreadSafeDict()
        
        self.metrics = {
            CacheLevel.L1: CacheMetrics(),
            CacheLevel.L2: CacheMetrics(),
            CacheLevel.L3: CacheMetrics()
        }
        self.metrics_lock = threading.RLock()
        
        logger.info("多级缓存策略初始化完成")
    
    def should_cache(self, key: str, value: Any) -> bool:
        if value is None:
            return False
        
        data_size = self._estimate_size(value)
        if data_size > 1024 * 1024:
            logger.warning(f"数据过大，不缓存: {key}, 大小: {data_size}字节")
            return False
        
        return True
    
    def get_ttl(self, key: str, value: Any) -> Optional[int]:
        access_count = self.access_count.get(key, 0)
        
        if access_count > 10:
            return 3600
        elif access_count > 5:
            return 1800
        else:
            return 900
    
    def determine_cache_level(self, key: str, value: Any) -> CacheLevel:
        access_count = self.access_count.get(key, 0)
        current_level = self.cache_level.get(key, CacheLevel.L2)
        
        if access_count >= self.promotion_threshold:
            if current_level == CacheLevel.L2:
                return CacheLevel.L1
            elif current_level == CacheLevel.L3:
                return CacheLevel.L2
        
        last_access = self.access_time.get(key, time.time())
        if time.time() - last_access > self.demotion_threshold:
            if current_level == CacheLevel.L1:
                return CacheLevel.L2
            elif current_level == CacheLevel.L2:
                return CacheLevel.L3
        
        return current_level
    
    def on_hit(self, key: str, value: Any) -> None:
        current_time = time.time()
        
        self.access_count.set(key, self.access_count.get(key, 0) + 1)
        self.access_time.set(key, current_time)
        
        level = self.cache_level.get(key, CacheLevel.L2)
        with self.metrics_lock:
            self.metrics[level].hits += 1
            self.metrics[level].last_access_time = current_time
        
        logger.debug(f"多级缓存命中: {key}, 级别: {level.value}")
    
    def on_miss(self, key: str) -> None:
        with self.metrics_lock:
            self.metrics[CacheLevel.L2].misses += 1
        
        logger.debug(f"多级缓存未命中: {key}")
    
    def on_set(self, key: str, value: Any, ttl: int = None) -> None:
        current_time = time.time()
        
        level = self.determine_cache_level(key, value)
        self.cache_level.set(key, level)
        
        self.access_time.set(key, current_time)
        
        with self.metrics_lock:
            self.metrics[level].sets += 1
            self.metrics[level].total_size += self._estimate_size(value)
        
        logger.debug(f"多级缓存设置: {key}, 级别: {level.value}")
    
    def on_delete(self, key: str) -> None:
        level = self.cache_level.get(key, CacheLevel.L2)
        
        self.access_count.delete(key)
        self.access_time.delete(key)
        self.cache_level.delete(key)
        
        with self.metrics_lock:
            self.metrics[level].deletes += 1
        
        logger.debug(f"多级缓存删除: {key}, 级别: {level.value}")
    
    def _estimate_size(self, value: Any) -> int:
        try:
            if isinstance(value, str):
                return len(value.encode('utf-8'))
            elif isinstance(value, (dict, list)):
                return len(json.dumps(value, ensure_ascii=False).encode('utf-8'))
            else:
                return len(str(value).encode('utf-8'))
        except Exception:
            return 1024
    
    def get_metrics(self) -> Dict[str, CacheMetrics]:
        with self.metrics_lock:
            return {level.value: metrics for level, metrics in self.metrics.items()}
    
    def reset_metrics(self) -> None:
        with self.metrics_lock:
            for level in self.metrics:
                self.metrics[level] = CacheMetrics()

class SmartInvalidationStrategy(CacheStrategy):
    
    def __init__(self):
        self.dependency_graph = ThreadSafeDict()
        self.reverse_dependency = ThreadSafeDict()
        self.tag_to_keys = ThreadSafeDict()
        self.key_to_tags = ThreadSafeDict()
        
        self.lock = ReadWriteLock()
        
        logger.info("智能缓存失效策略初始化完成")
    
    def add_dependency(self, key: str, depends_on: List[str]) -> None:
        with self.lock.write_lock():
            self.reverse_dependency.set(key, depends_on)
            
            for dep_key in depends_on:
                current_deps = self.dependency_graph.get(dep_key, [])
                if key not in current_deps:
                    current_deps.append(key)
                    self.dependency_graph.set(dep_key, current_deps)
        
        logger.debug(f"添加缓存依赖: {key} -> {depends_on}")
    
    def add_tag(self, key: str, tags: List[str]) -> None:
        with self.lock.write_lock():
            self.key_to_tags.set(key, tags)
            
            for tag in tags:
                current_keys = self.tag_to_keys.get(tag, [])
                if key not in current_keys:
                    current_keys.append(key)
                    self.tag_to_keys.set(tag, current_keys)
        
        logger.debug(f"添加缓存标签: {key} -> {tags}")
    
    def get_invalidation_keys(self, key: str) -> Set[str]:
        invalidation_keys = set()
        
        with self.lock.read_lock():
            dependent_keys = self.dependency_graph.get(key, [])
            invalidation_keys.update(dependent_keys)
            
            for dep_key in dependent_keys:
                invalidation_keys.update(self._get_recursive_dependencies(dep_key, set()))
            
            key_tags = self.key_to_tags.get(key, [])
            for tag in key_tags:
                tagged_keys = self.tag_to_keys.get(tag, [])
                invalidation_keys.update(tagged_keys)
        
        return invalidation_keys
    
    def _get_recursive_dependencies(self, key: str, visited: Set[str]) -> Set[str]:
        if key in visited:
            return set()
        
        visited.add(key)
        result = set()
        
        dependent_keys = self.dependency_graph.get(key, [])
        result.update(dependent_keys)
        
        for dep_key in dependent_keys:
            result.update(self._get_recursive_dependencies(dep_key, visited))
        
        return result
    
    def should_cache(self, key: str, value: Any) -> bool:
        return value is not None
    
    def get_ttl(self, key: str, value: Any) -> Optional[int]:
        if self.reverse_dependency.has(key) or self.key_to_tags.has(key):
            return 1800
        else:
            return 3600
    
    def on_hit(self, key: str, value: Any) -> None:
        logger.debug(f"智能失效缓存命中: {key}")
    
    def on_miss(self, key: str) -> None:
        logger.debug(f"智能失效缓存未命中: {key}")
    
    def on_set(self, key: str, value: Any, ttl: int = None) -> None:
        logger.debug(f"智能失效设置缓存: {key}")
    
    def on_delete(self, key: str) -> None:
        invalidation_keys = self.get_invalidation_keys(key)
        
        if invalidation_keys:
            logger.info(f"智能失效触发: {key} -> {invalidation_keys}")
        
        with self.lock.write_lock():
            depends_on = self.reverse_dependency.get(key, [])
            for dep_key in depends_on:
                current_deps = self.dependency_graph.get(dep_key, [])
                if key in current_deps:
                    current_deps.remove(key)
                    if current_deps:
                        self.dependency_graph.set(dep_key, current_deps)
                    else:
                        self.dependency_graph.delete(dep_key)
            
            self.reverse_dependency.delete(key)
            
            key_tags = self.key_to_tags.get(key, [])
            for tag in key_tags:
                tagged_keys = self.tag_to_keys.get(tag, [])
                if key in tagged_keys:
                    tagged_keys.remove(key)
                    if tagged_keys:
                        self.tag_to_keys.set(tag, tagged_keys)
                    else:
                        self.tag_to_keys.delete(tag)
            
            self.key_to_tags.delete(key)


class CacheWarmupStrategy(CacheStrategy):
    
    def __init__(self):
        self.warmup_tasks = ThreadSafeDict()
        self.warmup_schedule = ThreadSafeDict()
        self.warmup_stats = ThreadSafeDict()
        
        self.lock = ReadWriteLock()
        
        logger.info("缓存预热策略初始化完成")
    
    def register_warmup_task(self, 
                           key_pattern: str, 
                           data_loader: Callable[[], Any],
                           priority: int = 1,
                           schedule: str = "startup") -> None:
        task_id = hashlib.md5(key_pattern.encode()).hexdigest()[:8]
        
        task = {
            'key_pattern': key_pattern,
            'data_loader': data_loader,
            'priority': priority,
            'schedule': schedule,
            'last_run': 0,
            'run_count': 0,
            'success_count': 0,
            'error_count': 0
        }
        
        with self.lock.write_lock():
            self.warmup_tasks.set(task_id, task)
            
            schedule_tasks = self.warmup_schedule.get(schedule, [])
            if task_id not in schedule_tasks:
                schedule_tasks.append(task_id)
                schedule_tasks.sort(key=lambda tid: self.warmup_tasks.get(tid, {}).get('priority', 0), reverse=True)
                self.warmup_schedule.set(schedule, schedule_tasks)
        
        logger.info(f"注册缓存预热任务: {key_pattern}, 优先级: {priority}, 调度: {schedule}")
    
    @monitor_performance(log_slow_calls=True, slow_threshold=5.0)
    def execute_warmup(self, schedule: str = "startup") -> Dict[str, Any]:
        results = {
            'total_tasks': 0,
            'successful_tasks': 0,
            'failed_tasks': 0,
            'execution_time': 0,
            'warmed_keys': []
        }
        
        start_time = time.time()
        
        with self.lock.read_lock():
            task_ids = self.warmup_schedule.get(schedule, [])
            results['total_tasks'] = len(task_ids)
        
        for task_id in task_ids:
            try:
                task = self.warmup_tasks.get(task_id)
                if not task:
                    continue
                
                data = task['data_loader']()
                
                cache_key = task['key_pattern'].replace('*', 'warmup')
                
                task['last_run'] = time.time()
                task['run_count'] += 1
                task['success_count'] += 1
                self.warmup_tasks.set(task_id, task)
                
                results['successful_tasks'] += 1
                results['warmed_keys'].append(cache_key)
                
                logger.debug(f"预热任务成功: {task['key_pattern']}")
                
            except Exception as e:
                task = self.warmup_tasks.get(task_id, {})
                task['error_count'] = task.get('error_count', 0) + 1
                self.warmup_tasks.set(task_id, task)
                
                results['failed_tasks'] += 1
                logger.error(f"预热任务失败: {task.get('key_pattern', task_id)}, 错误: {e}")
        
        results['execution_time'] = time.time() - start_time
        
        self.warmup_stats.set(f"{schedule}_last_run", {
            'timestamp': time.time(),
            'results': results
        })
        
        logger.info(f"缓存预热完成: {schedule}, 成功: {results['successful_tasks']}, 失败: {results['failed_tasks']}")
        
        return results
    
    def should_cache(self, key: str, value: Any) -> bool:
        return value is not None
    
    def get_ttl(self, key: str, value: Any) -> Optional[int]:
        return 7200
    
    def on_hit(self, key: str, value: Any) -> None:
        logger.debug(f"预热缓存命中: {key}")
    
    def on_miss(self, key: str) -> None:
        logger.debug(f"预热缓存未命中: {key}")
    
    def on_set(self, key: str, value: Any, ttl: int = None) -> None:
        logger.debug(f"预热设置缓存: {key}")
    
    def on_delete(self, key: str) -> None:
        logger.debug(f"预热删除缓存: {key}")
    
    def get_warmup_stats(self) -> Dict[str, Any]:
        with self.lock.read_lock():
            stats = {}
            
            for task_id, task in self.warmup_tasks.items():
                stats[task_id] = {
                    'key_pattern': task.get('key_pattern'),
                    'priority': task.get('priority'),
                    'schedule': task.get('schedule'),
                    'run_count': task.get('run_count', 0),
                    'success_count': task.get('success_count', 0),
                    'error_count': task.get('error_count', 0),
                    'last_run': task.get('last_run', 0)
                }
            
            for schedule, last_run_data in self.warmup_stats.items():
                stats[schedule] = last_run_data
            
            return stats


class HybridCacheStrategy(CacheStrategy):
    
    def __init__(self):
        self.multi_level = MultiLevelCacheStrategy()
        self.smart_invalidation = SmartInvalidationStrategy()
        self.warmup = CacheWarmupStrategy()
        
        self.strategy_rules = {
            'user': self.multi_level,
            'session': self.multi_level,
            'room': self.smart_invalidation,
            'cabinet': self.smart_invalidation,
            'device': self.smart_invalidation,
            'statistics': self.warmup,
            'dashboard': self.warmup
        }
        
        logger.info("混合缓存策略初始化完成")
    
    def _get_strategy_for_key(self, key: str) -> CacheStrategy:
        key_parts = key.split(':')
        if key_parts:
            data_type = key_parts[0]
            return self.strategy_rules.get(data_type, self.multi_level)
        return self.multi_level
    
    def should_cache(self, key: str, value: Any) -> bool:
        strategy = self._get_strategy_for_key(key)
        return strategy.should_cache(key, value)
    
    def get_ttl(self, key: str, value: Any) -> Optional[int]:
        strategy = self._get_strategy_for_key(key)
        return strategy.get_ttl(key, value)
    
    def on_hit(self, key: str, value: Any) -> None:
        strategy = self._get_strategy_for_key(key)
        strategy.on_hit(key, value)
    
    def on_miss(self, key: str) -> None:
        strategy = self._get_strategy_for_key(key)
        strategy.on_miss(key)
    
    def on_set(self, key: str, value: Any, ttl: int = None) -> None:
        strategy = self._get_strategy_for_key(key)
        strategy.on_set(key, value, ttl)
    
    def on_delete(self, key: str) -> None:
        strategy = self._get_strategy_for_key(key)
        strategy.on_delete(key)
    
    def add_dependency(self, key: str, depends_on: List[str]) -> None:
        self.smart_invalidation.add_dependency(key, depends_on)
    
    def add_tag(self, key: str, tags: List[str]) -> None:
        self.smart_invalidation.add_tag(key, tags)
    
    def register_warmup_task(self, key_pattern: str, data_loader: Callable[[], Any],
                           priority: int = 1, schedule: str = "startup") -> None:
        self.warmup.register_warmup_task(key_pattern, data_loader, priority, schedule)
    
    def execute_warmup(self, schedule: str = "startup") -> Dict[str, Any]:
        return self.warmup.execute_warmup(schedule)
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        return {
            'multi_level_metrics': self.multi_level.get_metrics(),
            'warmup_stats': self.warmup.get_warmup_stats(),
            'strategy_rules': {k: v.__class__.__name__ for k, v in self.strategy_rules.items()}
        }
