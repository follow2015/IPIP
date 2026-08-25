# -*- coding: utf-8 -*-
"""
缓存监控系统

提供缓存性能监控、告警和分析功能。
"""
from app.utils.logging import get_logger
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, asdict

from app.utils.concurrency.locks import ThreadSafeDict, ReadWriteLock
from app.utils.concurrency.decorators import monitor_performance

logger = get_logger(__name__)


@dataclass
class CacheEvent:
    timestamp: float
    event_type: str
    key: str
    cache_level: str = "unknown"
    execution_time: float = 0.0
    data_size: int = 0
    error_message: str = ""


@dataclass
class CacheAlert:
    timestamp: float
    alert_type: str
    severity: str
    message: str
    metrics: Dict[str, Any]
    resolved: bool = False


class CacheMonitor:
    
    def __init__(self, 
                 max_events: int = 10000,
                 alert_thresholds: Dict[str, Any] = None):
        self.max_events = max_events
        self.alert_thresholds = alert_thresholds or self._get_default_thresholds()
        
        self.events = deque(maxlen=max_events)
        self.events_lock = threading.RLock()

        self.alerts = deque(maxlen=1000)
        self.alerts_lock = threading.RLock()
        
        self.metrics = ThreadSafeDict()
        self.metrics_lock = ReadWriteLock()
        
        self.alert_callbacks = []

        self._alert_cooldown_seconds: float = 60.0
        self._alert_last_fired: Dict[str, float] = {}

        self._initialize_metrics()
        
        logger.info("缓存监控器初始化完成")
    
    def _get_default_thresholds(self) -> Dict[str, Any]:
        return {
            'hit_rate_low': 0.7,
            'response_time_high': 0.1,
            'error_rate_high': 0.05,
            'memory_usage_high': 0.8,
            'eviction_rate_high': 0.1,
            'connection_failure_count': 5
        }
    
    def _initialize_metrics(self) -> None:
        initial_metrics = {
            'total_requests': 0,
            'total_hits': 0,
            'total_misses': 0,
            'total_sets': 0,
            'total_deletes': 0,
            'total_errors': 0,
            'total_response_time': 0.0,
            'max_response_time': 0.0,
            'min_response_time': None,
            'cache_size': 0,
            'memory_usage': 0,
            'connection_failures': 0,
            'last_update': time.time()
        }
        
        for key, value in initial_metrics.items():
            self.metrics.set(key, value)
    
    def record_event(self, event: CacheEvent) -> None:
        with self.events_lock:
            self.events.append(event)

        self._update_metrics(event)
        
        self._check_alerts(event)
    
    def _update_metrics(self, event: CacheEvent) -> None:
        with self.metrics_lock.write_lock():
            if event.event_type == 'hit':
                self.metrics.set('total_hits', self.metrics.get('total_hits', 0) + 1)
                self.metrics.set('total_requests', self.metrics.get('total_requests', 0) + 1)
            elif event.event_type == 'miss':
                self.metrics.set('total_misses', self.metrics.get('total_misses', 0) + 1)
                self.metrics.set('total_requests', self.metrics.get('total_requests', 0) + 1)
            elif event.event_type == 'set':
                self.metrics.set('total_sets', self.metrics.get('total_sets', 0) + 1)
                self.metrics.set('cache_size', self.metrics.get('cache_size', 0) + event.data_size)
            elif event.event_type == 'delete':
                self.metrics.set('total_deletes', self.metrics.get('total_deletes', 0) + 1)
                self.metrics.set('cache_size', max(0, self.metrics.get('cache_size', 0) - event.data_size))
            elif event.event_type == 'error':
                self.metrics.set('total_errors', self.metrics.get('total_errors', 0) + 1)
                if 'connection' in event.error_message.lower():
                    self.metrics.set('connection_failures', self.metrics.get('connection_failures', 0) + 1)
            
            if event.execution_time > 0:
                total_time = self.metrics.get('total_response_time', 0.0) + event.execution_time
                self.metrics.set('total_response_time', total_time)
                
                max_time = max(self.metrics.get('max_response_time', 0.0), event.execution_time)
                self.metrics.set('max_response_time', max_time)
                
                min_time = min(self.metrics.get('min_response_time') or float('inf'), event.execution_time)
                self.metrics.set('min_response_time', min_time)
            
            self.metrics.set('last_update', time.time())
    
    def _check_alerts(self, event: CacheEvent) -> None:
        now = time.time()
        current_metrics = self.get_current_metrics()
        alerts_to_create = []

        if current_metrics['hit_rate'] < self.alert_thresholds['hit_rate_low']:
            alerts_to_create.append(CacheAlert(
                timestamp=now,
                alert_type='performance',
                severity='medium',
                message=f"缓存命中率过低: {current_metrics['hit_rate']:.2%}",
                metrics={'hit_rate': current_metrics['hit_rate']}
            ))

        if event.execution_time > self.alert_thresholds['response_time_high']:
            alerts_to_create.append(CacheAlert(
                timestamp=now,
                alert_type='performance',
                severity='high',
                message=f"缓存响应时间过长: {event.execution_time:.3f}s",
                metrics={'response_time': event.execution_time, 'key': event.key}
            ))

        if current_metrics['error_rate'] > self.alert_thresholds['error_rate_high']:
            alerts_to_create.append(CacheAlert(
                timestamp=now,
                alert_type='error',
                severity='high',
                message=f"缓存错误率过高: {current_metrics['error_rate']:.2%}",
                metrics={'error_rate': current_metrics['error_rate']}
            ))

        connection_failures = self.metrics.get('connection_failures', 0)
        if connection_failures >= self.alert_thresholds['connection_failure_count']:
            alerts_to_create.append(CacheAlert(
                timestamp=now,
                alert_type='error',
                severity='critical',
                message=f"缓存连接失败次数过多: {connection_failures}",
                metrics={'connection_failures': connection_failures}
            ))

        for alert in alerts_to_create:
            cooldown_key = f"{alert.alert_type}:{alert.severity}"
            last_fired = self._alert_last_fired.get(cooldown_key, 0.0)
            if now - last_fired < self._alert_cooldown_seconds:
                continue
            self._alert_last_fired[cooldown_key] = now
            self._create_alert(alert)
    
    def _create_alert(self, alert: CacheAlert) -> None:
        with self.alerts_lock:
            self.alerts.append(alert)

        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error("告警回调执行失败: %s", e)

        logger.warning("缓存告警: %s - %s", alert.alert_type, alert.message)
    
    def add_alert_callback(self, callback: Callable[[CacheAlert], None]) -> None:
        self.alert_callbacks.append(callback)
    
    def get_current_metrics(self) -> Dict[str, Any]:
        with self.metrics_lock.read_lock():
            total_requests = self.metrics.get('total_requests', 0)
            total_hits = self.metrics.get('total_hits', 0)
            total_errors = self.metrics.get('total_errors', 0)
            total_response_time = self.metrics.get('total_response_time', 0.0)
            
            hit_rate = total_hits / total_requests if total_requests > 0 else 0.0
            error_rate = total_errors / total_requests if total_requests > 0 else 0.0
            avg_response_time = total_response_time / total_requests if total_requests > 0 else 0.0
            
            return {
                'total_requests': total_requests,
                'total_hits': total_hits,
                'total_misses': self.metrics.get('total_misses', 0),
                'total_sets': self.metrics.get('total_sets', 0),
                'total_deletes': self.metrics.get('total_deletes', 0),
                'total_errors': total_errors,
                'hit_rate': hit_rate,
                'error_rate': error_rate,
                'avg_response_time': avg_response_time,
                'max_response_time': self.metrics.get('max_response_time', 0.0),
                'min_response_time': self.metrics.get('min_response_time') or 0.0,
                'cache_size': self.metrics.get('cache_size', 0),
                'memory_usage': self.metrics.get('memory_usage', 0),
                'connection_failures': self.metrics.get('connection_failures', 0),
                'last_update': self.metrics.get('last_update', 0)
            }
    
    def get_events(self, 
                   event_type: Optional[str] = None,
                   start_time: Optional[float] = None,
                   end_time: Optional[float] = None,
                   limit: int = 100) -> List[CacheEvent]:
        with self.events_lock:
            filtered_events = []
            
            for event in reversed(self.events):
                if start_time and event.timestamp < start_time:
                    continue
                if end_time and event.timestamp > end_time:
                    continue
                
                if event_type and event.event_type != event_type:
                    continue
                
                filtered_events.append(event)
                
                if len(filtered_events) >= limit:
                    break
            
            return filtered_events
    
    def get_alerts(self, 
                   alert_type: Optional[str] = None,
                   severity: Optional[str] = None,
                   resolved: Optional[bool] = None,
                   limit: int = 50) -> List[CacheAlert]:
        with self.alerts_lock:
            filtered_alerts = []
            
            for alert in reversed(self.alerts):
                if alert_type and alert.alert_type != alert_type:
                    continue
                
                if severity and alert.severity != severity:
                    continue
                
                if resolved is not None and alert.resolved != resolved:
                    continue
                
                filtered_alerts.append(alert)
                
                if len(filtered_alerts) >= limit:
                    break
            
            return filtered_alerts
    
    def resolve_alert(self, alert_index: int) -> bool:
        with self.alerts_lock:
            if 0 <= alert_index < len(self.alerts):
                self.alerts[alert_index].resolved = True
                return True
            return False
    
    @monitor_performance(log_slow_calls=True, slow_threshold=1.0)
    def generate_report(self, 
                       start_time: Optional[float] = None,
                       end_time: Optional[float] = None) -> Dict[str, Any]:
        if not start_time:
            start_time = time.time() - 3600
        if not end_time:
            end_time = time.time()
        
        events = self.get_events(start_time=start_time, end_time=end_time, limit=10000)
        
        event_stats = {}
        response_times = []
        error_events = []
        
        for event in events:
            event_type = event.event_type
            event_stats[event_type] = event_stats.get(event_type, 0) + 1
            
            if event.execution_time > 0:
                response_times.append(event.execution_time)
            
            if event.event_type == 'error':
                error_events.append(event)
        
        total_events = len(events)
        hit_count = event_stats.get('hit', 0)
        miss_count = event_stats.get('miss', 0)
        total_requests = hit_count + miss_count
        
        hit_rate = hit_count / total_requests if total_requests > 0 else 0.0
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0
        max_response_time = max(response_times) if response_times else 0.0
        min_response_time = min(response_times) if response_times else 0.0
        
        alerts = self.get_alerts(limit=100)
        unresolved_alerts = [a for a in alerts if not a.resolved]
        
        report = {
            'report_period': {
                'start_time': start_time,
                'end_time': end_time,
                'duration_hours': (end_time - start_time) / 3600
            },
            'summary': {
                'total_events': total_events,
                'total_requests': total_requests,
                'hit_rate': hit_rate,
                'avg_response_time': avg_response_time,
                'max_response_time': max_response_time,
                'min_response_time': min_response_time,
                'error_count': len(error_events),
                'alert_count': len(alerts),
                'unresolved_alert_count': len(unresolved_alerts)
            },
            'event_breakdown': event_stats,
            'performance_metrics': {
                'response_time_distribution': self._calculate_percentiles(response_times),
                'slow_operations': [
                    asdict(event) for event in events 
                    if event.execution_time > self.alert_thresholds['response_time_high']
                ][:10]
            },
            'error_analysis': {
                'error_types': self._analyze_errors(error_events),
                'recent_errors': [asdict(event) for event in error_events[:5]]
            },
            'alerts': {
                'recent_alerts': [asdict(alert) for alert in alerts[:10]],
                'unresolved_alerts': [asdict(alert) for alert in unresolved_alerts]
            },
            'current_metrics': self.get_current_metrics()
        }
        
        return report
    
    def _calculate_percentiles(self, values: List[float]) -> Dict[str, float]:
        if not values:
            return {}
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        
        return {
            'p50': sorted_values[int(n * 0.5)] if n > 0 else 0.0,
            'p90': sorted_values[int(n * 0.9)] if n > 0 else 0.0,
            'p95': sorted_values[int(n * 0.95)] if n > 0 else 0.0,
            'p99': sorted_values[int(n * 0.99)] if n > 0 else 0.0
        }
    
    def _analyze_errors(self, error_events: List[CacheEvent]) -> Dict[str, int]:
        error_types = {}
        
        for event in error_events:
            error_msg = event.error_message.lower()
            
            if 'connection' in error_msg:
                error_type = 'connection_error'
            elif 'timeout' in error_msg:
                error_type = 'timeout_error'
            elif 'memory' in error_msg:
                error_type = 'memory_error'
            elif 'serialization' in error_msg:
                error_type = 'serialization_error'
            else:
                error_type = 'unknown_error'
            
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        return error_types
    
    def reset_metrics(self) -> None:
        with self.events_lock:
            self.events.clear()
        
        with self.alerts_lock:
            self.alerts.clear()
        
        self._initialize_metrics()
        
        logger.info("缓存监控指标已重置")


_cache_monitor_instance = None


def __getattr__(name: str):
    if name == "cache_monitor":
        global _cache_monitor_instance
        if _cache_monitor_instance is None:
            _cache_monitor_instance = CacheMonitor()
        return _cache_monitor_instance
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_cache_monitor() -> "CacheMonitor":
    return __getattr__("cache_monitor")


def reset_cache_monitor_for_test() -> None:
    global _cache_monitor_instance
    _cache_monitor_instance = None
