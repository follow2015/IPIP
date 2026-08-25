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
    """查询监控器
    
    监控SQL查询的执行情况，检测N+1查询问题。
    """
    
    def __init__(self):
        self.queries: List[Dict[str, Any]] = []
        self.query_counts = defaultdict(int)
        self.slow_queries: List[Dict[str, Any]] = []
        self.n_plus_1_patterns: Set[str] = set()
        self._lock = threading.Lock()
        self.enabled = True
        self.slow_query_threshold = 0.1  # 100ms
        
    def record_query(self, statement: str, parameters: Any, duration: float, 
                    context: Optional[str] = None):
        """记录查询执行信息
        
        Args:
            statement: SQL语句
            parameters: 查询参数
            duration: 执行时间（秒）
            context: 执行上下文
        """
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
        """标准化查询语句，移除参数值"""
        import re
        normalized = re.sub(r'\b\d+\b', '?', statement)
        normalized = re.sub(r"'[^']*'", '?', normalized)
        normalized = re.sub(r'"[^"]*"', '?', normalized)
        return normalized.strip()
    
    def _detect_n_plus_1(self, normalized_query: str):
        """检测N+1查询模式"""
        if self.query_counts[normalized_query] > 5:
            if normalized_query not in self.n_plus_1_patterns:
                self.n_plus_1_patterns.add(normalized_query)
                logger.warning(f"可能的N+1查询: {normalized_query}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取查询统计信息"""
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
                'slow_queries': self.slow_queries[-10:],  # 最近10个慢查询
                'n_plus_1_patterns': list(self.n_plus_1_patterns)
            }
    
    def reset(self):
        """重置监控数据"""
        with self._lock:
            self.queries.clear()
            self.query_counts.clear()
            self.slow_queries.clear()
            self.n_plus_1_patterns.clear()
    
    def enable(self):
        """启用监控"""
        self.enabled = True
    
    def disable(self):
        """禁用监控"""
        self.enabled = False


query_monitor = QueryMonitor()


class QueryOptimizer:
    """查询优化器
    
    提供查询优化建议和自动优化功能。
    """
    
    @staticmethod
    def optimize_pagination_query(query: Query, page: int, page_size: int) -> Tuple[List[Any], int]:
        """优化分页查询
        
        使用窗口函数或子查询优化分页性能。
        
        Args:
            query: SQLAlchemy查询对象
            page: 页码
            page_size: 每页大小
            
        Returns:
            Tuple[List[Any], int]: (数据列表, 总数)
        """
        offset = (page - 1) * page_size
        
        count_query = query.statement.with_only_columns([query.statement.c.id]).alias()
        total_count = query.session.execute(
            query.session.query(count_query).count()
        ).scalar()
        
        data = query.offset(offset).limit(page_size).all()
        
        return data, total_count
    
    @staticmethod
    def add_eager_loading(query: Query, relationships: List[str]) -> Query:
        """为查询添加预加载关系
        
        Args:
            query: SQLAlchemy查询对象
            relationships: 要预加载的关系列表
            
        Returns:
            Query: 优化后的查询对象
        """
        from sqlalchemy.orm import joinedload, selectinload
        
        for relationship in relationships:
            if '.' in relationship:
                query = query.options(selectinload(relationship))
            else:
                query = query.options(joinedload(relationship))
        
        return query
    
    @staticmethod
    def optimize_exists_query(session: Session, model_class: Any, filters: Dict[str, Any]) -> bool:
        """优化存在性查询
        
        使用EXISTS而不是COUNT来检查记录是否存在。
        
        Args:
            session: 数据库会话
            model_class: 模型类
            filters: 过滤条件
            
        Returns:
            bool: 记录是否存在
        """
        query = session.query(model_class)
        
        for key, value in filters.items():
            if hasattr(model_class, key):
                query = query.filter(getattr(model_class, key) == value)
        
        return session.query(query.exists()).scalar()
    
    @staticmethod
    def batch_load_relationships(session: Session, entities: List[Any], 
                                relationship_name: str) -> Dict[Any, List[Any]]:
        """批量加载关系数据，避免N+1查询
        
        Args:
            session: 数据库会话
            entities: 实体列表
            relationship_name: 关系名称
            
        Returns:
            Dict: 实体ID到关系数据的映射
        """
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
    """查询性能监控装饰器"""
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
    """查询性能监控上下文管理器"""
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
    """设置SQLAlchemy查询监控
    
    Args:
        engine: SQLAlchemy引擎
    """
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
    """查询分析器
    
    分析查询模式并提供优化建议。
    """
    
    @staticmethod
    def analyze_n_plus_1_risk(model_class: Any, relationships: List[str]) -> Dict[str, Any]:
        """分析N+1查询风险
        
        Args:
            model_class: 模型类
            relationships: 关系列表
            
        Returns:
            Dict: 分析结果
        """
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
        """建议索引
        
        Args:
            model_class: 模型类
            frequent_filters: 常用过滤字段
            
        Returns:
            List[str]: 索引建议
        """
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