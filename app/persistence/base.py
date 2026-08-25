# -*- coding: utf-8 -*-
"""
Repository基础实现

提供Repository模式的基础实现，统一数据访问方式。
"""
import inspect

from app.utils.logging import get_logger
from typing import Any, Callable, Dict, List, Optional, Tuple, Type
from contextlib import contextmanager

from sqlalchemy import or_, desc, asc, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, Query, joinedload, selectinload

from app.models.base import BaseModel
from app.exceptions.data_access import (
    DataAccessError,
    QueryExecutionError,
    TransactionError
)
from app.utils.query_optimizer import query_monitor, monitor_query_performance
from extensions import db

logger = get_logger(__name__)


class BaseRepository:
    """Repository基础抽象类
    
    实现BaseRepository接口，提供通用的数据访问方法。
    所有具体的Repository都应该继承此类。
    """

    _REGISTRY: Dict[Type["BaseRepository"], Callable[[Optional[Session]], "BaseRepository"]] = {}

    def __init_subclass__(cls, abstract: bool = False, **kwargs):
        """子类钩子：自动将具体仓储登记到 ``_REGISTRY``。

        Args:
            abstract: 中间基类（如 SQLAlchemyRepository/OptimizedRepository）
                置 True 以避免被当作可创建的叶仓储注册。
        """
        super().__init_subclass__(**kwargs)
        if abstract:
            cls._is_abstract = True
            return
        sig = inspect.signature(cls.__init__)
        if "session" in sig.parameters:
            cls._REGISTRY[cls] = lambda s=None: cls(s or db.session)
        else:
            cls._REGISTRY[cls] = lambda s=None: cls()

    def __init__(self, model_class: Type[BaseModel], session: Session = None):
        """初始化Repository
        
        Args:
            model_class: 模型类
            session: 数据库会话，默认使用全局会话
        """
        self.model_class = model_class
        self.session = session or db.session
        self.logger = get_logger(f"{self.__class__.__module__}.{self.__class__.__name__}")
    
    def find_by_id(self, entity_id: int) -> Optional[BaseModel]:
        """根据ID查找实体
        
        Args:
            entity_id: 实体ID
            
        Returns:
            Optional[BaseModel]: 实体对象，不存在则返回None
            
        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            query = self._base_query().filter_by(id=entity_id)
            return query.first()
        except SQLAlchemyError as e:
            self.logger.error(f"根据ID查找{self.model_class.__name__}失败 (ID={entity_id}): {e}")
            raise QueryExecutionError(f"查找{self.model_class.__name__}失败", original_error=e)

    def find_by_ids(self, ids: List[int]) -> List[BaseModel]:
        """根据ID列表批量查找实体（避免 N+1 查询）

        Args:
            ids: ID列表

        Returns:
            List[BaseModel]: 实体列表
        """
        if not ids:
            return []
        try:
            query = self._base_query().filter(
                self.model_class.id.in_(ids)
            )
            return query.all()
        except SQLAlchemyError as e:
            self.logger.error(f"批量查找{self.model_class.__name__}失败: {e}")
            raise QueryExecutionError(f"批量查找{self.model_class.__name__}失败", original_error=e)

    def _base_query(self) -> Query:
        """构建基础查询，自动过滤软删除记录。

        所有查询方法应通过此方法构建基础 Query，确保软删除过滤逻辑
        只在一处维护，避免散落多处导致遗漏或被意外覆盖。
        """
        query = self.session.query(self.model_class)
        if getattr(self.model_class, '__soft_delete__', False):
            query = query.filter(self.model_class.deleted_at.is_(None))
        return query

    def find_all(self, filters: Dict[str, Any] = None, 
                 order_by: str = None, limit: int = None,
                 offset: int = None) -> List[BaseModel]:
        """查找所有符合条件的实体
        
        Args:
            filters: 过滤条件字典
            order_by: 排序字段，支持"-field"表示降序
            limit: 限制返回数量
            offset: 跳过前N条记录（分页用）
            
        Returns:
            List[BaseModel]: 实体列表
            
        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            query = self._base_query()

            if filters:
                query = self._apply_filters(query, filters)

            if order_by:
                query = self._apply_ordering(query, order_by)

            if offset is not None:
                query = query.offset(offset)
            if limit is not None:
                query = query.limit(limit)

            return query.all()
        except SQLAlchemyError as e:
            self.logger.error(f"查找{self.model_class.__name__}列表失败: {e}")
            raise QueryExecutionError(f"查找{self.model_class.__name__}列表失败", original_error=e)

    def count(self, filters: Dict[str, Any] = None) -> int:
        """统计符合条件的实体数量（分页用）

        Args:
            filters: 过滤条件字典

        Returns:
            int: 符合条件的记录数
        """
        try:
            query = self._base_query()
            if filters:
                query = self._apply_filters(query, filters)
            return query.count()
        except SQLAlchemyError as e:
            self.logger.error(f"统计{self.model_class.__name__}数量失败: {e}")
            raise QueryExecutionError(f"统计{self.model_class.__name__}数量失败", original_error=e)

    def find_one(self, filters: Dict[str, Any]) -> Optional[BaseModel]:
        """查找单个符合条件的实体
        
        Args:
            filters: 过滤条件字典
            
        Returns:
            Optional[BaseModel]: 实体对象，不存在则返回None
            
        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            query = self._base_query()
            query = self._apply_filters(query, filters)
            return query.first()
        except SQLAlchemyError as e:
            self.logger.error(f"查找单个{self.model_class.__name__}失败: {e}")
            raise QueryExecutionError(f"查找{self.model_class.__name__}失败", original_error=e)
    
    def save(self, entity: BaseModel) -> BaseModel:
        """保存实体（创建或更新）
        
        Args:
            entity: 实体对象
            
        Returns:
            BaseModel: 保存后的实体对象
            
        Raises:
            DataAccessError: 保存失败
        """
        try:
            if entity.id is None:
                self.session.add(entity)
            else:
                entity = self.session.merge(entity)
            
            self.session.flush()
            self.logger.info(f"保存{self.model_class.__name__}成功 (ID={entity.id})")
            return entity
        except SQLAlchemyError as e:
            self.logger.error(f"保存{self.model_class.__name__}失败: {e}")
            raise DataAccessError(f"保存{self.model_class.__name__}失败", original_error=e)
    
    def create(self, data: Dict[str, Any]) -> BaseModel:
        """创建新实体
        
        Args:
            data: 实体数据字典
            
        Returns:
            BaseModel: 创建的实体对象
            
        Raises:
            DataAccessError: 创建失败
        """
        try:
            entity = self.model_class(**data)
            self.session.add(entity)
            self.session.flush()
            self.logger.info(f"创建{self.model_class.__name__}成功 (ID={entity.id})")
            return entity
        except SQLAlchemyError as e:
            self.logger.error(f"创建{self.model_class.__name__}失败: {e}")
            raise DataAccessError(f"创建{self.model_class.__name__}失败", original_error=e)
    
    def update(self, entity_id: int, data: Dict[str, Any], allowed: list = None) -> Optional[BaseModel]:
        """更新实体
        
        Args:
            entity_id: 实体ID
            data: 更新数据字典
            
        Returns:
            Optional[BaseModel]: 更新后的实体对象，不存在则返回None
            
        Raises:
            DataAccessError: 更新失败
        """
        try:
            entity = self.find_by_id(entity_id)
            if not entity:
                return None
            
            if hasattr(entity, 'update_from_dict'):
                entity.update_from_dict(data, allowed=allowed)
            else:
                if allowed is not None:
                    for key in allowed:
                        if key in data and hasattr(entity, key):
                            setattr(entity, key, data[key])
                else:
                    for key, value in data.items():
                        if hasattr(entity, key):
                            setattr(entity, key, value)
            
            from sqlalchemy.orm.attributes import flag_modified
            from sqlalchemy import JSON
            if hasattr(entity, '__table__'):
                for column in entity.__table__.columns:
                    if isinstance(column.type, JSON) and column.name in data:
                        flag_modified(entity, column.name)
            
            self.session.flush()
            self.logger.info(f"更新{self.model_class.__name__}成功 (ID={entity_id})")
            return entity
        except SQLAlchemyError as e:
            self.logger.error(f"更新{self.model_class.__name__}失败 (ID={entity_id}): {e}")
            raise DataAccessError(f"更新{self.model_class.__name__}失败", original_error=e)
    
    def delete(self, entity_id: int) -> bool:
        """删除实体（支持软删除）

        如果模型启用了 __soft_delete__，则执行软删除（设置 deleted_at），
        否则执行物理删除。

        Args:
            entity_id: 实体ID

        Returns:
            bool: 删除成功返回True

        Raises:
            DataAccessError: 删除失败
        """
        try:
            entity = self.find_by_id(entity_id)
            if not entity:
                return False

            if getattr(self.model_class, '__soft_delete__', False):
                entity.soft_delete()
            else:
                self.session.delete(entity)
            self.session.flush()
            self.logger.info(f"删除{self.model_class.__name__}成功 (ID={entity_id})")
            return True
        except SQLAlchemyError as e:
            self.logger.error(f"删除{self.model_class.__name__}失败 (ID={entity_id}): {e}")
            raise DataAccessError(f"删除{self.model_class.__name__}失败", original_error=e)
    
    def exists(self, filters: Dict[str, Any]) -> bool:
        """检查实体是否存在
        
        Args:
            filters: 过滤条件字典
            
        Returns:
            bool: 存在返回True
            
        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            query = self._base_query()
            query = self._apply_filters(query, filters)
            return self.session.query(query.exists()).scalar()
        except SQLAlchemyError as e:
            self.logger.error(f"检查{self.model_class.__name__}存在性失败: {e}")
            raise QueryExecutionError(f"检查{self.model_class.__name__}存在性失败", original_error=e)
    
    def paginate(self, page: int = 1, page_size: int = 20, 
                 filters: Dict[str, Any] = None, 
                 order_by: str = None) -> Dict[str, Any]:
        """分页查询
        
        Args:
            page: 页码（从1开始）
            page_size: 每页数量
            filters: 过滤条件字典
            order_by: 排序字段
                
        Raises:
            QueryExecutionError: 查询执行失败
        """
        try:
            query = self._base_query()
            
            if filters:
                query = self._apply_filters(query, filters)
            
            total_count = query.count()
            
            total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
            
            page = 1 if total_pages == 0 else max(1, min(page, total_pages))
            
            if order_by:
                query = self._apply_ordering(query, order_by)
            
            offset = (page - 1) * page_size
            data = query.limit(page_size).offset(offset).all()
            
            return {
                "data": data,
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
            }
        except SQLAlchemyError as e:
            self.logger.error(f"分页查询{self.model_class.__name__}失败: {e}")
            raise QueryExecutionError(f"分页查询{self.model_class.__name__}失败", original_error=e)
    
    def bulk_create(self, data_list: List[Dict[str, Any]]) -> List[BaseModel]:
        """批量创建实体
        
        Args:
            data_list: 实体数据字典列表
            
        Returns:
            List[BaseModel]: 创建的实体对象列表
            
        Raises:
            DataAccessError: 创建失败
        """
        try:
            entities = [self.model_class(**data) for data in data_list]
            self.session.add_all(entities)
            self.session.flush()
            self.logger.info(f"批量创建{self.model_class.__name__}成功 (数量={len(entities)})")
            return entities
        except SQLAlchemyError as e:
            self.logger.error(f"批量创建{self.model_class.__name__}失败: {e}")
            raise DataAccessError(f"批量创建{self.model_class.__name__}失败", original_error=e)
    
    def bulk_update(self, updates: List[Tuple[int, Dict[str, Any]]]) -> int:
        """批量更新实体
        
        Args:
            updates: 更新数据列表，每个元素为(entity_id, update_data)
            
        Returns:
            int: 更新的实体数量
            
        Raises:
            DataAccessError: 更新失败
        """
        try:
            entity_ids = [entity_id for entity_id, _ in updates]
            entities = self._base_query().filter(
                self.model_class.id.in_(entity_ids)
            ).all()
            entity_map = {e.id: e for e in entities}

            updated_count = 0
            for entity_id, update_data in updates:
                entity = entity_map.get(entity_id)
                if entity:
                    if hasattr(entity, 'update_from_dict'):
                        entity.update_from_dict(update_data)
                    else:
                        for key, value in update_data.items():
                            if hasattr(entity, key):
                                setattr(entity, key, value)
                    updated_count += 1
            
            self.session.flush()
            self.logger.info(f"批量更新{self.model_class.__name__}成功 (数量={updated_count})")
            return updated_count
        except SQLAlchemyError as e:
            self.logger.error(f"批量更新{self.model_class.__name__}失败: {e}")
            raise DataAccessError(f"批量更新{self.model_class.__name__}失败", original_error=e)
    
    def bulk_delete(self, entity_ids: List[int]) -> int:
        """批量删除实体
        
        Args:
            entity_ids: 实体ID列表
            
        Returns:
            int: 删除的实体数量
            
        Raises:
            DataAccessError: 删除失败
        """
        try:
            if getattr(self.model_class, '__soft_delete__', False):
                from datetime import datetime, timezone
                entities = self._base_query().filter(
                    self.model_class.id.in_(entity_ids)
                ).all()
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                for entity in entities:
                    entity.deleted_at = now
                deleted_count = len(entities)
            else:
                deleted_count = self.session.query(self.model_class).filter(
                    self.model_class.id.in_(entity_ids)
                ).delete(synchronize_session=False)
            
            self.session.flush()
            self.logger.info(f"批量删除{self.model_class.__name__}成功 (数量={deleted_count})")
            return deleted_count
        except SQLAlchemyError as e:
            self.logger.error(f"批量删除{self.model_class.__name__}失败: {e}")
            raise DataAccessError(f"批量删除{self.model_class.__name__}失败", original_error=e)
    
    
    def _apply_filters(self, query: Query, filters: Dict[str, Any]) -> Query:
        """应用过滤条件
        
        Args:
            query: 查询对象
            filters: 过滤条件字典
            
        Returns:
            Query: 应用过滤条件后的查询对象
        """
        for key, value in filters.items():
            if hasattr(self.model_class, key):
                column = getattr(self.model_class, key)
                
                if isinstance(value, dict):
                    for operator, operand in value.items():
                        if operator == 'eq':
                            query = query.filter(column == operand)
                        elif operator == 'ne':
                            query = query.filter(column != operand)
                        elif operator == 'gt':
                            query = query.filter(column > operand)
                        elif operator == 'gte':
                            query = query.filter(column >= operand)
                        elif operator == 'lt':
                            query = query.filter(column < operand)
                        elif operator == 'lte':
                            query = query.filter(column <= operand)
                        elif operator == 'like':
                            query = query.filter(column.like(f"%{operand}%"))
                        elif operator == 'ilike':
                            query = query.filter(column.ilike(f"%{operand}%"))
                        elif operator == 'in':
                            query = query.filter(column.in_(operand))
                        elif operator == 'not_in':
                            query = query.filter(~column.in_(operand))
                        elif operator == 'is_null':
                            if operand:
                                query = query.filter(column.is_(None))
                            else:
                                query = query.filter(column.isnot(None))
                elif isinstance(value, list):
                    query = query.filter(column.in_(value))
                else:
                    query = query.filter(column == value)
        
        return query
    
    def _apply_ordering(self, query: Query, order_by: str) -> Query:
        """应用排序
        
        Args:
            query: 查询对象
            order_by: 排序字段，支持"-field"表示降序
            
        Returns:
            Query: 应用排序后的查询对象
        """
        if order_by.startswith('-'):
            field = order_by[1:]
            if hasattr(self.model_class, field):
                column = getattr(self.model_class, field)
                query = query.order_by(desc(column))
        else:
            if hasattr(self.model_class, order_by):
                column = getattr(self.model_class, order_by)
                query = query.order_by(asc(column))
        
        return query
    
    @contextmanager
    def transaction(self):
        """事务上下文管理器
        
        使用方法:
            with repository.transaction():
                pass
        """
        try:
            yield self.session
            self.session.flush()
        except SQLAlchemyError as e:
            self.session.rollback()
            self.logger.error(f"事务执行失败(数据库错误): {e}")
            raise TransactionError("事务执行失败", original_error=e)
        except Exception as e:
            self.session.rollback()
            self.logger.error(f"事务执行失败(非数据库错误): {e}")
            raise


class SQLAlchemyRepository(BaseRepository, abstract=True):
    """SQLAlchemy Repository实现
    
    基于SQLAlchemy的Repository实现，提供ORM优先的数据访问方式。
    这是推荐的Repository实现，优先使用ORM进行数据访问。
    """
    
    def __init__(self, model_class: Type[BaseModel], session: Session = None):
        """初始化SQLAlchemy Repository
        
        Args:
            model_class: 模型类
            session: 数据库会话，默认使用全局会话
        """
        super().__init__(model_class, session)
        self.logger.debug(f"初始化{self.model_class.__name__} SQLAlchemy Repository")
    
    def find_with_relations(self, entity_id: int, relations: List[str] = None) -> Optional[BaseModel]:
        """查找实体并预加载关联对象
        
        Args:
            entity_id: 实体ID
            relations: 要预加载的关联对象列表
            
        Returns:
            Optional[BaseModel]: 实体对象，不存在则返回None
        """
        try:
            query = self._base_query()
            
            if relations:
                for relation in relations:
                    if hasattr(self.model_class, relation):
                        rel_prop = getattr(self.model_class, relation).property
                        if rel_prop.uselist:
                            query = query.options(selectinload(getattr(self.model_class, relation)))
                        else:
                            query = query.options(joinedload(getattr(self.model_class, relation)))
            
            return query.filter_by(id=entity_id).first()
        except SQLAlchemyError as e:
            self.logger.error(f"查找{self.model_class.__name__}及关联对象失败 (ID={entity_id}): {e}")
            raise QueryExecutionError(f"查找{self.model_class.__name__}失败", original_error=e)
    
    def search(self, search_fields: List[str], keyword: str,
               filters: Dict[str, Any] = None,
               exclude_filters: Optional[Dict[str, Any]] = None,
               page: int = 1, page_size: int = 20,
               joins: Optional[List[Dict[str, Any]]] = None,
               join_search_fields: Optional[List[Dict[str, Any]]] = None,
               distinct: bool = False) -> Dict[str, Any]:
        """搜索实体
        
        Args:
            search_fields: 本模型搜索字段列表
            keyword: 搜索关键词
            filters: 精确匹配过滤条件（仅支持本模型字段，不支持跨表字段）
            exclude_filters: 排除过滤条件，key=字段名 value=要排除的值（使用 != 运算符）
            page: 页码
            page_size: 每页数量
            joins: 跨表 join 配置列表，每项为 {"model": ModelClass, "on": join_condition, "type": "outerjoin"|"join"}
            join_search_fields: 跨表搜索字段列表，每项为 {"model": ModelClass, "field": "field_name", "cast": "Text"|"Integer"|None}
            distinct: 是否使用 COUNT(DISTINCT) 去重（outerjoin 场景需要）
            
        Returns:
            Dict[str, Any]: 搜索结果
        """
        try:
            query = self._base_query()

            for join_cfg in (joins or []):
                join_model = join_cfg["model"]
                join_on = join_cfg.get("on")
                join_type = join_cfg.get("type", "outerjoin")
                if join_type == "outerjoin":
                    query = query.outerjoin(join_model, join_on) if join_on else query.outerjoin(join_model)
                else:
                    query = query.join(join_model, join_on) if join_on else query.join(join_model)

            if keyword and search_fields:
                search_conditions = []
                for field in search_fields:
                    if hasattr(self.model_class, field):
                        column = getattr(self.model_class, field)
                        search_conditions.append(column.ilike(f"%{keyword}%"))

                for jsf in (join_search_fields or []):
                    join_model = jsf["model"]
                    field_name = jsf["field"]
                    if hasattr(join_model, field_name):
                        column = getattr(join_model, field_name)
                        cast_type = jsf.get("cast")
                        if cast_type:
                            from sqlalchemy import String, Text as SAText, Integer
                            cast_map = {"Text": SAText, "String": String, "Integer": Integer}
                            sa_type = cast_map.get(cast_type)
                            if sa_type:
                                column = column.cast(sa_type)
                        search_conditions.append(column.ilike(f"%{keyword}%"))

                if search_conditions:
                    query = query.filter(or_(*search_conditions))
            
            if filters:
                query = self._apply_filters(query, filters)
            
            if exclude_filters:
                for key, value in exclude_filters.items():
                    if hasattr(self.model_class, key):
                        query = query.filter(getattr(self.model_class, key) != value)
            
            if distinct:
                from sqlalchemy import distinct as sa_distinct
                pk_col = getattr(self.model_class, 'id')
                total_count = query.with_entities(func.count(sa_distinct(pk_col))).scalar() or 0
                total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
                page = 1 if total_pages == 0 else max(1, min(page, total_pages))
                offset = (page - 1) * page_size
                id_rows = (
                    query.with_entities(sa_distinct(pk_col))
                    .order_by(pk_col)
                    .limit(page_size)
                    .offset(offset)
                    .all()
                )
                ids = [r[0] for r in id_rows]
                data = (
                    self._base_query()
                    .filter(pk_col.in_(ids))
                    .all() if ids else []
                )
            else:
                total_count = query.count()
                total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
                page = 1 if total_pages == 0 else max(1, min(page, total_pages))
                offset = (page - 1) * page_size
                data = query.limit(page_size).offset(offset).all()
            
            return {
                "data": data,
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
            }
        except SQLAlchemyError as e:
            self.logger.error(f"搜索{self.model_class.__name__}失败: {e}")
            raise QueryExecutionError(f"搜索{self.model_class.__name__}失败", original_error=e)


class OptimizedRepository(BaseRepository, abstract=True):
    """优化的Repository基类
    
    提供查询优化功能，包括：
    - 自动N+1查询检测和预防
    - 分页查询优化
    - 批量操作优化
    - 查询性能监控
    """
    
    def __init__(self, model_class: Any, session: Session):
        """初始化优化Repository
        
        Args:
            model_class: 模型类
            session: 数据库会话
        """
        super().__init__(model_class, session)
        self.default_eager_load = []
        self.query_cache = {}
    
    def set_default_eager_load(self, relationships: List[str]):
        """设置默认预加载关系
        
        Args:
            relationships: 关系名称列表
        """
        self.default_eager_load = relationships
    
    @monitor_query_performance
    def find_by_id_optimized(self, entity_id: int, 
                           eager_load: Optional[List[str]] = None) -> Optional[Any]:
        """优化的按ID查找方法
        
        Args:
            entity_id: 实体ID
            eager_load: 要预加载的关系列表
            
        Returns:
            Optional[Any]: 实体对象
        """
        try:
            query = self._base_query()
            
            relationships = eager_load or self.default_eager_load
            if relationships:
                query = self._apply_eager_loading(query, relationships)
            
            return query.filter_by(id=entity_id).first()
        except Exception as e:
            logger.error(f"优化查询失败: {e}")
            raise QueryExecutionError(f"按ID查找失败", original_error=e)
    
    @monitor_query_performance
    def find_all_optimized(self, filters: Optional[Dict[str, Any]] = None,
                          eager_load: Optional[List[str]] = None,
                          order_by: Optional[str] = None) -> List[Any]:
        """优化的查找所有方法
        
        Args:
            filters: 过滤条件
            eager_load: 要预加载的关系列表
            order_by: 排序字段
            
        Returns:
            List[Any]: 实体列表
        """
        try:
            query = self._base_query()
            
            if filters:
                query = self._apply_filters(query, filters)
            
            relationships = eager_load or self.default_eager_load
            if relationships:
                query = self._apply_eager_loading(query, relationships)
            
            if order_by:
                if hasattr(self.model_class, order_by):
                    query = query.order_by(getattr(self.model_class, order_by))
            
            return query.all()
        except Exception as e:
            logger.error(f"优化查询失败: {e}")
            raise QueryExecutionError(f"查找所有记录失败", original_error=e)
    
    @monitor_query_performance
    def paginate_optimized(self, page: int = 1, page_size: int = 20,
                          filters: Optional[Dict[str, Any]] = None,
                          eager_load: Optional[List[str]] = None,
                          order_by: Optional[str] = None) -> Dict[str, Any]:
        """优化的分页查询
        
        使用窗口函数和子查询优化分页性能。
        
        Args:
            page: 页码
            page_size: 每页大小
            filters: 过滤条件
            eager_load: 要预加载的关系列表
            order_by: 排序字段
            
        Returns:
            Dict[str, Any]: 分页结果
        """
        try:
            query = self._base_query()
            
            if filters:
                query = self._apply_filters(query, filters)
            
            if order_by and hasattr(self.model_class, order_by):
                query = query.order_by(getattr(self.model_class, order_by))
            
            count_query = query.statement.with_only_columns(func.count()).order_by(None)
            total_count = self.session.execute(count_query).scalar()
            
            total_pages = (total_count + page_size - 1) // page_size
            offset = (page - 1) * page_size
            
            relationships = eager_load or self.default_eager_load
            if relationships:
                query = self._apply_eager_loading(query, relationships)
            
            data = query.offset(offset).limit(page_size).all()
            
            return {
                "data": data,
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        except Exception as e:
            logger.error(f"分页查询失败: {e}")
            raise QueryExecutionError(f"分页查询失败", original_error=e)
    
    @monitor_query_performance
    def exists_optimized(self, filters: Dict[str, Any]) -> bool:
        """优化的存在性检查
        
        使用EXISTS而不是COUNT提高性能。
        
        Args:
            filters: 过滤条件
            
        Returns:
            bool: 是否存在
        """
        try:
            query = self._base_query()
            query = self._apply_filters(query, filters)
            
            return self.session.query(query.exists()).scalar()
        except Exception as e:
            logger.error(f"存在性检查失败: {e}")
            raise QueryExecutionError(f"存在性检查失败", original_error=e)
    
    @monitor_query_performance
    def batch_load_by_ids(self, entity_ids: List[int],
                         eager_load: Optional[List[str]] = None) -> Dict[int, Any]:
        """批量按ID加载实体
        
        避免N+1查询问题。
        
        Args:
            entity_ids: 实体ID列表
            eager_load: 要预加载的关系列表
            
        Returns:
            Dict[int, Any]: ID到实体的映射
        """
        if not entity_ids:
            return {}
        
        try:
            query = self._base_query().filter(
                self.model_class.id.in_(entity_ids)
            )
            
            relationships = eager_load or self.default_eager_load
            if relationships:
                query = self._apply_eager_loading(query, relationships)
            
            entities = query.all()
            
            return {entity.id: entity for entity in entities}
        except Exception as e:
            logger.error(f"批量加载失败: {e}")
            raise QueryExecutionError(f"批量加载失败", original_error=e)
    
    def batch_create(self, data_list: List[Dict[str, Any]]) -> List[Any]:
        """批量创建实体
        
        Args:
            data_list: 数据字典列表
            
        Returns:
            List[Any]: 创建的实体列表
        """
        if not data_list:
            return []
        
        try:
            entities = []
            for data in data_list:
                entity = self.model_class(**data)
                entities.append(entity)
                self.session.add(entity)
            
            self.session.flush()
            return entities
        except Exception as e:
            logger.error(f"批量创建失败: {e}")
            raise QueryExecutionError(f"批量创建失败", original_error=e)
    
    def batch_update(self, updates: List[Tuple[int, Dict[str, Any]]]) -> int:
        """批量更新实体（先批量 IN 预加载，再 setattr，消除 N+1 写）
        
        Args:
            updates: (ID, 更新数据) 元组列表
            
        Returns:
            int: 更新的记录数
        """
        if not updates:
            return 0
        
        try:
            entity_ids = [eid for eid, _ in updates]
            entities = self._base_query().filter(
                self.model_class.id.in_(entity_ids)
            ).all()
            entity_map = {e.id: e for e in entities}

            updated_count = 0
            for entity_id, update_data in updates:
                entity = entity_map.get(entity_id)
                if entity:
                    for k, v in update_data.items():
                        if hasattr(entity, k):
                            setattr(entity, k, v)
                    from sqlalchemy.orm.attributes import flag_modified as _flag_modified
                    from sqlalchemy import JSON as _JSON
                    if hasattr(entity, '__table__'):
                        for column in entity.__table__.columns:
                            if isinstance(column.type, _JSON) and column.name in update_data:
                                _flag_modified(entity, column.name)
                    updated_count += 1

            self.session.flush()
            return updated_count
        except Exception as e:
            logger.error(f"批量更新失败: {e}")
            raise QueryExecutionError(f"批量更新失败", original_error=e)
    
    def _apply_eager_loading(self, query: Query, relationships: List[str]) -> Query:
        """应用预加载策略
        
        Args:
            query: 查询对象
            relationships: 关系列表
            
        Returns:
            Query: 应用预加载后的查询对象
        """
        for relationship in relationships:
            if not hasattr(self.model_class, relationship):
                logger.warning(f"关系 '{relationship}' 在模型 {self.model_class.__name__} 中不存在")
                continue
            
            rel_attr = getattr(self.model_class, relationship)
            
            if hasattr(rel_attr.property, 'uselist') and rel_attr.property.uselist:
                query = query.options(selectinload(rel_attr))
            else:
                query = query.options(joinedload(rel_attr))
        
        return query
    
    def _apply_filters(self, query: Query, filters: Dict[str, Any]) -> Query:
        """应用过滤条件（委托给基类实现，避免重复维护两份过滤逻辑）"""
        return super()._apply_filters(query, filters)
    
    def get_query_statistics(self) -> Dict[str, Any]:
        """获取查询统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        return query_monitor.get_statistics()
    
    def analyze_performance(self) -> Dict[str, Any]:
        """分析查询性能
        
        Returns:
            Dict[str, Any]: 性能分析结果
        """
        from app.utils.query_optimizer import query_analyzer
        
        n_plus_1_analysis = query_analyzer.analyze_n_plus_1_risk(
            self.model_class, 
            self.default_eager_load
        )
        
        query_stats = self.get_query_statistics()
        
        return {
            'model': self.model_class.__name__,
            'n_plus_1_analysis': n_plus_1_analysis,
            'query_statistics': query_stats,
            'default_eager_load': self.default_eager_load
        }


class QueryOptimizationMixin:
    """查询优化混入类
    
    为现有Repository类提供优化功能。
    """
    
    def enable_query_monitoring(self):
        """启用查询监控"""
        query_monitor.enable()
    
    def disable_query_monitoring(self):
        """禁用查询监控"""
        query_monitor.disable()
    
    def reset_query_statistics(self):
        """重置查询统计"""
        query_monitor.reset()
    
    def get_slow_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取慢查询列表
        
        Args:
            limit: 返回数量限制
            
        Returns:
            List[Dict[str, Any]]: 慢查询列表
        """
        stats = query_monitor.get_statistics()
        return stats.get('slow_queries', [])[-limit:]
    
    def get_n_plus_1_patterns(self) -> List[str]:
        """获取N+1查询模式
        
        Returns:
            List[str]: N+1查询模式列表
        """
        stats = query_monitor.get_statistics()
        return stats.get('n_plus_1_patterns', [])
