# -*- coding: utf-8 -*-
"""
查询性能分析工具

提供查询性能分析、N+1查询检测和优化建议。
"""
from app.utils.logging import get_logger
import time
from typing import Any, Dict, List
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.utils.query_optimizer import query_monitor

logger = get_logger(__name__)


@dataclass
class QueryAnalysisResult:
    query_pattern: str
    execution_count: int
    total_time: float
    average_time: float
    max_time: float
    min_time: float
    is_slow: bool
    is_n_plus_1: bool
    optimization_suggestions: List[str]


@dataclass
class N1QueryPattern:
    pattern: str
    count: int
    related_queries: List[str]
    suggested_fix: str


class QueryPerformanceAnalyzer:
    
    def __init__(self, session: Session):
        self.session = session
        self.slow_query_threshold = 0.1
        self.n_plus_1_threshold = 5
        self.query_counts = query_monitor.query_counts
    
    def analyze_query_patterns(self, time_window_minutes: int = 60) -> List[QueryAnalysisResult]:
        stats = query_monitor.get_statistics()
        
        pattern_stats = defaultdict(list)
        
        cutoff_time = time.time() - (time_window_minutes * 60)
        
        for query_info in stats.get('queries', []):
            if query_info.get('timestamp', 0) < cutoff_time:
                continue
                
            pattern = self._normalize_query_pattern(query_info.get('statement', ''))
            pattern_stats[pattern].append(query_info)
        
        results = []
        for pattern, queries in pattern_stats.items():
            if not queries:
                continue
                
            execution_count = len(queries)
            durations = [q.get('duration', 0) for q in queries]
            total_time = sum(durations)
            average_time = total_time / execution_count
            max_time = max(durations)
            min_time = min(durations)
            
            is_slow = average_time > self.slow_query_threshold
            is_n_plus_1 = execution_count > self.n_plus_1_threshold
            
            suggestions = self._generate_optimization_suggestions(
                pattern, execution_count, average_time, is_slow, is_n_plus_1
            )
            
            result = QueryAnalysisResult(
                query_pattern=pattern,
                execution_count=execution_count,
                total_time=total_time,
                average_time=average_time,
                max_time=max_time,
                min_time=min_time,
                is_slow=is_slow,
                is_n_plus_1=is_n_plus_1,
                optimization_suggestions=suggestions
            )
            results.append(result)
        
        results.sort(key=lambda x: x.total_time, reverse=True)
        return results
    
    def detect_n_plus_1_patterns(self) -> List[N1QueryPattern]:
        stats = query_monitor.get_statistics()
        patterns = []

        runtime_patterns = stats.get('n_plus_1_patterns', [])
        for pattern in runtime_patterns:
            count = self.query_counts.get(pattern, 0)
            related_queries = self._find_related_queries(pattern)
            suggested_fix = self._suggest_n_plus_1_fix(pattern)

            n1_pattern = N1QueryPattern(
                pattern=pattern,
                count=count,
                related_queries=related_queries,
                suggested_fix=suggested_fix
            )
            patterns.append(n1_pattern)

        for pattern, count in stats.get('frequent_queries', []):
            if count > self.n_plus_1_threshold and pattern not in runtime_patterns:
                related_queries = self._find_related_queries(pattern)
                suggested_fix = self._suggest_n_plus_1_fix(pattern)

                n1_pattern = N1QueryPattern(
                    pattern=pattern,
                    count=count,
                    related_queries=related_queries,
                    suggested_fix=suggested_fix
                )
                patterns.append(n1_pattern)

        return patterns
    
    def analyze_slow_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        stats = query_monitor.get_statistics()
        slow_queries = stats.get('slow_queries', [])
        
        slow_queries.sort(key=lambda x: x.get('duration', 0), reverse=True)
        
        results = []
        for query_info in slow_queries[:limit]:
            analysis = {
                'statement': query_info.get('statement', ''),
                'duration': query_info.get('duration', 0),
                'context': query_info.get('context', ''),
                'timestamp': query_info.get('timestamp', 0),
                'optimization_suggestions': self._analyze_slow_query(query_info)
            }
            results.append(analysis)
        
        return results
    
    def generate_performance_report(self) -> Dict[str, Any]:
        stats = query_monitor.get_statistics()
        query_patterns = self.analyze_query_patterns()
        n_plus_1_patterns = self.detect_n_plus_1_patterns()
        slow_queries = self.analyze_slow_queries()
        
        total_queries = stats.get('total_queries', 0)
        total_time = stats.get('total_time', 0)
        avg_time = stats.get('average_time', 0)
        slow_query_count = stats.get('slow_queries_count', 0)
        
        performance_score = self._calculate_performance_score(
            avg_time, slow_query_count, total_queries, len(n_plus_1_patterns)
        )
        
        return {
            'summary': {
                'total_queries': total_queries,
                'total_time': round(total_time, 3),
                'average_time': round(avg_time, 3),
                'slow_query_count': slow_query_count,
                'n_plus_1_patterns_count': len(n_plus_1_patterns),
                'performance_score': performance_score
            },
            'query_patterns': [
                {
                    'pattern': p.query_pattern,
                    'execution_count': p.execution_count,
                    'total_time': round(p.total_time, 3),
                    'average_time': round(p.average_time, 3),
                    'is_slow': p.is_slow,
                    'is_n_plus_1': p.is_n_plus_1,
                    'suggestions': p.optimization_suggestions
                }
                for p in query_patterns[:10]
            ],
            'n_plus_1_patterns': [
                {
                    'pattern': p.pattern,
                    'count': p.count,
                    'suggested_fix': p.suggested_fix
                }
                for p in n_plus_1_patterns
            ],
            'slow_queries': slow_queries[:5],
            'recommendations': self._generate_general_recommendations(
                query_patterns, n_plus_1_patterns, slow_queries
            )
        }
    
    def _normalize_query_pattern(self, statement: str) -> str:
        import re
        
        normalized = re.sub(r'\b\d+\b', '?', statement)
        normalized = re.sub(r"'[^']*'", '?', normalized)
        normalized = re.sub(r'"[^"]*"', '?', normalized)
        
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized.strip()
    
    def _generate_optimization_suggestions(self, pattern: str, count: int, 
                                         avg_time: float, is_slow: bool, 
                                         is_n_plus_1: bool) -> List[str]:
        suggestions = []
        
        if is_n_plus_1:
            suggestions.append("检测到N+1查询模式，建议使用JOIN或预加载（eager loading）")
            suggestions.append("考虑使用批量查询替代循环查询")
        
        if is_slow:
            suggestions.append("查询执行时间较长，建议检查索引是否合适")
            suggestions.append("考虑优化WHERE条件或使用更高效的查询方式")
        
        if 'SELECT COUNT' in pattern.upper():
            suggestions.append("COUNT查询可能较慢，考虑使用EXISTS或缓存结果")
        
        if 'ORDER BY' in pattern.upper() and 'LIMIT' not in pattern.upper():
            suggestions.append("排序查询建议添加LIMIT限制结果数量")
        
        if count > 100:
            suggestions.append("查询执行频率很高，建议考虑缓存结果")
        
        return suggestions
    
    def _find_related_queries(self, pattern: str) -> List[str]:
        stats = query_monitor.get_statistics()
        related = []
        
        tables = self._extract_table_names(pattern)
        for other_pattern, _ in stats.get('frequent_queries', []):
            if other_pattern != pattern:
                other_tables = self._extract_table_names(other_pattern)
                if tables & other_tables:
                    related.append(other_pattern)
        
        return related[:3]
    
    def _extract_table_names(self, query: str) -> set:
        import re
        
        tables = set()
        
        from_matches = re.findall(r'FROM\s+(\w+)', query, re.IGNORECASE)
        join_matches = re.findall(r'JOIN\s+(\w+)', query, re.IGNORECASE)
        
        tables.update(from_matches)
        tables.update(join_matches)
        
        return tables
    
    def _suggest_n_plus_1_fix(self, pattern: str) -> str:
        if 'SELECT' in pattern.upper() and 'WHERE' in pattern.upper():
            return "使用JOIN查询或SQLAlchemy的joinedload/selectinload预加载关联数据"
        elif 'COUNT' in pattern.upper():
            return "使用聚合查询或EXISTS子查询替代多次COUNT查询"
        else:
            return "考虑批量查询或使用IN子句替代循环查询"
    
    def _analyze_slow_query(self, query_info: Dict[str, Any]) -> List[str]:
        suggestions = []
        statement = query_info.get('statement', '').upper()
        duration = query_info.get('duration', 0)
        
        if duration > 1.0:
            suggestions.append("查询执行时间超过1秒，需要紧急优化")
        
        if 'SELECT *' in statement:
            suggestions.append("避免使用SELECT *，只查询需要的字段")
        
        if 'ORDER BY' in statement and 'LIMIT' not in statement:
            suggestions.append("排序查询建议添加LIMIT限制")
        
        if statement.count('JOIN') > 3:
            suggestions.append("JOIN表过多，考虑分解查询或优化表结构")
        
        if 'LIKE %' in statement:
            suggestions.append("前缀模糊查询无法使用索引，考虑全文搜索")
        
        return suggestions
    
    def _calculate_performance_score(self, avg_time: float, slow_count: int, 
                                   total_queries: int, n_plus_1_count: int) -> int:
        score = 100
        
        if avg_time > 0.5:
            score -= 30
        elif avg_time > 0.1:
            score -= 15
        elif avg_time > 0.05:
            score -= 5
        
        if total_queries > 0:
            slow_ratio = slow_count / total_queries
            if slow_ratio > 0.1:
                score -= 25
            elif slow_ratio > 0.05:
                score -= 15
            elif slow_ratio > 0.01:
                score -= 5
        
        if n_plus_1_count > 5:
            score -= 20
        elif n_plus_1_count > 2:
            score -= 10
        elif n_plus_1_count > 0:
            score -= 5
        
        return max(0, score)
    
    def _generate_general_recommendations(self, query_patterns: List[QueryAnalysisResult],
                                        n_plus_1_patterns: List[N1QueryPattern],
                                        slow_queries: List[Dict[str, Any]]) -> List[str]:
        recommendations = []
        
        if n_plus_1_patterns:
            recommendations.append("发现N+1查询问题，建议在Repository层使用预加载策略")
        
        if slow_queries:
            recommendations.append("存在慢查询，建议检查数据库索引和查询优化")
        
        count_patterns = [p for p in query_patterns if 'COUNT' in p.query_pattern.upper()]
        if count_patterns:
            recommendations.append("频繁的COUNT查询可能影响性能，考虑使用缓存或EXISTS查询")
        
        pagination_patterns = [p for p in query_patterns if 'LIMIT' in p.query_pattern.upper()]
        if len(pagination_patterns) > 5:
            recommendations.append("大量分页查询，建议优化分页算法或使用游标分页")
        
        if not recommendations:
            recommendations.append("查询性能良好，继续保持当前的优化策略")
        
        return recommendations


def create_performance_report(session: Session) -> Dict[str, Any]:
    analyzer = QueryPerformanceAnalyzer(session)
    return analyzer.generate_performance_report()


def analyze_repository_performance(repository_class: Any) -> Dict[str, Any]:
    from app.utils.query_optimizer import query_analyzer
    
    relationships = getattr(repository_class, 'default_eager_load', [])
    model_class = getattr(repository_class, 'model_class', None)
    
    if model_class:
        n_plus_1_analysis = query_analyzer.analyze_n_plus_1_risk(model_class, relationships)
        index_suggestions = query_analyzer.suggest_indexes(model_class, [])
        
        return {
            'repository': repository_class.__name__,
            'model': model_class.__name__,
            'n_plus_1_analysis': n_plus_1_analysis,
            'index_suggestions': index_suggestions,
            'default_eager_load': relationships
        }
    
    return {'error': 'Unable to analyze repository'}
