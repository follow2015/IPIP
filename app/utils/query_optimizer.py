# -*- coding: utf-8 -*-
"""
数据库查询优化工具

提供查询性能监控、N+1查询检测和优化建议。
"""
from app.utils.logging import get_logger
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict
import threading

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Query, Session

logger = get_logger(__name__)


class QueryMonitor:
    
    def __init__(self):
        self.queries: List[Dict[str, Any]] = []
        self.query_counts = defaultdict(int)
        self.slow_queries: List[Dict[str, Any]] = []
        self.n_plus_1_patterns: Set[str] = set()
        self._lock = threading.Lock()
        self.enabled = True
        self.slow_query_threshold = 0.1
        
    def record_query(self, statement: str, parameters: Any, duration: float, 
                    context: Optional[str] = None):
        if not self.enabled:
            return
            
        with self._lock:
            query_info = {
                'statement': statement,
                'parameters': parameters,
                'duration': duration,
                'context': context,
                'timestamp': time.time()
            }
            
            self.queries.append(query_info)
            
            normalized_query = self._normalize_query(statement)
            self.query_counts[normalized_query] += 1
            
            if duration > self.slow_query_threshold:
                self.slow_queries.append(query_info)
                logger.warning(f"慢查询检测: {duration:.3f}s - {statement[:100]}...")
            
            self._detect_n_plus_1(normalized_query)
    
    def _normalize_query(self, statement: str) -> str:
        import re
        normalized = re.sub(r'\b\d+\b', '?', statement)
        normalized = re.sub(r"'[^']*'", '?', normalized)
        normalized = re.sub(r'"[^"]*"', '?', normalized)
        return normalized.strip()
    
    def _detect_n_plus_1(self, normalized_query: str):
        if self.query_counts[normalized_query] > 5:
            if normalized_query not in self.n_plus_1_patterns:
                self.n_plus_1_patterns.add(normalized_query)
                logger.warning(f"可能的N+1查询: {normalized_query}")
    
    def get_statistics(self) -> Dict[str, Any]:
        with self._lock:
            total_queries = len(self.queries)
            total_time = sum(q['duration'] for q in self.queries)
            avg_time = total_time / total_queries if total_queries > 0 else 0
            
            frequent_queries = sorted(
                self.query_counts.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10]
            
            return {
                'total_queries': total_queries,
                'total_time': total_time,
                'average_time': avg_time,
                'slow_queries_count': len(self.slow_queries),
                'n_plus_1_patterns_count': len(self.n_plus_1_patterns),
                'frequent_queries': frequent_queries,
                'slow_queries': self.slow_queries[-10:],
                'n_plus_1_patterns': list(self.n_plus_1_patterns)
            }
    
    def reset(self):
        with self._lock:
            self.queries.clear()
            self.query_counts.clear()
            self.slow_queries.clear()
            self.n_plus_1_patterns.clear()
    
    def enable(self):
        self.enabled = True
    
    def disable(self):
        self.enabled = False


query_monitor = QueryMonitor()


class QueryOptimizer:
    
    @staticmethod
    def optimize_pagination_query(query: Query, page: int, page_size: int) -> Tuple[List[Any], int]:
        offset = (page - 1) * page_size
        
        count_query = query.statement.with_only_columns([query.statement.c.id]).alias()
        total_count = query.session.execute(
            query.session.query(count_query).count()
        ).scalar()
        
        data = query.offset(offset).limit(page_size).all()
        
        return data, total_count
    
    @staticmethod
    def add_eager_loading(query: Query, relationships: List[str]) -> Query:
        from sqlalchemy.orm import joinedload, selectinload
        
        for relationship in relationships:
            if '.' in relationship:
                query = query.options(selectinload(relationship))
            else:
                query = query.options(joinedload(relationship))
        
        return query
    
    @staticmethod
    def optimize_exists_query(session: Session, model_class: Any, filters: Dict[str, Any]) -> bool:
        query = session.query(model_class)
        
        for key, value in filters.items():
            if hasattr(model_class, key):
                query = query.filter(getattr(model_class, key) == value)
        
        return session.query(query.exists()).scalar()
    
    @staticmethod
    def batch_load_relationships(session: Session, entities: List[Any], 
                                relationship_name: str) -> Dict[Any, List[Any]]:
        if not entities:
            return {}
        
        entity_ids = [entity.id for entity in entities]
        
        relationship_attr = getattr(entities[0].__class__, relationship_name)
        related_model = relationship_attr.property.mapper.class_
        
        foreign_key = relationship_attr.property.local_columns[0].name
        related_entities = session.query(related_model).filter(
            getattr(related_model, foreign_key).in_(entity_ids)
        ).all()
        
        result = defaultdict(list)
        for related_entity in related_entities:
            fk_value = getattr(related_entity, foreign_key)
            result[fk_value].append(related_entity)
        
        return dict(result)


def monitor_query_performance(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            query_monitor.record_query(
                statement=f"{func.__module__}.{func.__name__}",
                parameters=None,
                duration=duration,
                context=f"Function: {func.__name__}"
            )
            
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"查询执行失败 {func.__name__}: {e}, 耗时: {duration:.3f}s")
            raise
    
    return wrapper


@contextmanager
def query_performance_context(context_name: str):
    start_time = time.time()
    
    try:
        yield
    finally:
        duration = time.time() - start_time
        query_monitor.record_query(
            statement=context_name,
            parameters=None,
            duration=duration,
            context=context_name
        )


def setup_sqlalchemy_monitoring(engine: Engine):
    @event.listens_for(engine, "before_cursor_execute")
    def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        context._query_start_time = time.time()
    
    @event.listens_for(engine, "after_cursor_execute")
    def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        duration = time.time() - context._query_start_time
        
        query_monitor.record_query(
            statement=statement,
            parameters=parameters,
            duration=duration,
            context="SQLAlchemy"
        )


class QueryAnalyzer:
    
    @staticmethod
    def analyze_n_plus_1_risk(model_class: Any, relationships: List[str]) -> Dict[str, Any]:
        risks = []
        recommendations = []
        
        for relationship in relationships:
            if hasattr(model_class, relationship):
                rel_attr = getattr(model_class, relationship)
                
                if hasattr(rel_attr.property, 'lazy'):
                    lazy_strategy = rel_attr.property.lazy
                    
                    if lazy_strategy == 'select':
                        risks.append(f"关系 '{relationship}' 使用lazy='select'，可能导致N+1查询")
                        recommendations.append(f"考虑为 '{relationship}' 使用 joinedload 或 selectinload")
                    elif lazy_strategy == 'dynamic':
                        risks.append(f"关系 '{relationship}' 使用lazy='dynamic'，需要显式加载")
                        recommendations.append(f"在查询时为 '{relationship}' 添加适当的加载选项")
        
        return {
            'model': model_class.__name__,
            'risks': risks,
            'recommendations': recommendations,
            'risk_level': 'high' if len(risks) > 2 else 'medium' if len(risks) > 0 else 'low'
        }
    
    @staticmethod
    def suggest_indexes(model_class: Any, frequent_filters: List[str]) -> List[str]:
        suggestions = []
        
        for field in frequent_filters:
            if hasattr(model_class, field):
                column = getattr(model_class, field)
                
                if hasattr(column.property, 'columns'):
                    col = column.property.columns[0]
                    if not col.index and not col.primary_key:
                        suggestions.append(f"为字段 '{field}' 添加索引")
        
        return suggestions


query_optimizer = QueryOptimizer()
query_analyzer = QueryAnalyzer()
