# -*- coding: utf-8 -*-
"""
服务层基类模块

提供通用的CRUD方法和查询构建器。
"""
from typing import Any, Dict, List, Optional, Tuple, Type

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query

from app.models.base import BaseModel
from app.exceptions.business import ServiceError
from app.utils.logging import get_logger

from extensions import db

logger = get_logger(__name__)

class BaseService:
    """服务层基类

    提供通用的CRUD方法、分页查询和查询构建器。
    所有具体的服务类都应该继承此基类。
    """

    def __init__(self, model_class: Type[BaseModel] = None):
        """初始化服务

        Args:
            model_class: 模型类
        """
        self.model_class = model_class
        self.session = db.session

    def get_by_id(self, id: int) -> Optional[BaseModel]:
        """根据ID获取单个对象

        Args:
            id: 对象ID

        Returns:
            Optional[BaseModel]: 模型对象，不存在则返回None

        Raises:
            QueryExecutionError: 查询失败时抛出
        """
        try:
            return self.session.query(self.model_class).filter_by(id=id).first()
        except SQLAlchemyError as e:
            logger.error("数据库查询失败", extra={
                'model_class': self.model_class.__name__,
                'operation': 'get_by_id',
                'object_id': id,
                'error_type': type(e).__name__,
                'error_message': str(e)
            })
            raise ServiceError(f"查询{self.model_class.__name__}失败") from e

    def get_all(
        self, filters: Dict[str, Any] = None, order_by: str = None, limit: int = None
    ) -> List[BaseModel]:
        """获取所有对象

        Args:
            filters: 过滤条件字典
            order_by: 排序字段
            limit: 限制返回数量

        Returns:
            List[BaseModel]: 模型对象列表

        Raises:
            QueryExecutionError: 查询失败时抛出
        """
        try:
            query = self.session.query(self.model_class)

            if filters:
                query = query.filter_by(**filters)

            if order_by:
                if order_by.startswith("-"):
                    field = order_by[1:]
                    query = query.order_by(getattr(self.model_class, field).desc())
                else:
                    query = query.order_by(getattr(self.model_class, order_by))

            if limit:
                query = query.limit(limit)

            return query.all()
        except SQLAlchemyError as e:
            logger.error("数据库查询失败", extra={
                'model_class': self.model_class.__name__,
                'operation': 'get_all',
                'filters': filters,
                'error_type': type(e).__name__,
                'error_message': str(e)
            })
            raise ServiceError(f"查询{self.model_class.__name__}列表失败") from e

    def create(self, data: Dict[str, Any]) -> BaseModel:
        """创建新对象

        Args:
            data: 对象数据字典

        Returns:
            BaseModel: 创建的模型对象

        Raises:
            DataAccessError: 创建失败时抛出
        """
        try:
            obj = self.model_class(**data)
            self.session.add(obj)
            self.session.flush()
            logger.info("对象创建成功", extra={
                'model_class': self.model_class.__name__,
                'object_id': obj.id,
                'operation': 'create'
            })
            return obj
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("对象创建失败", extra={
                'model_class': self.model_class.__name__,
                'operation': 'create',
                'error_type': type(e).__name__,
                'error_message': str(e)
            })
            raise ServiceError(f"创建{self.model_class.__name__}失败") from e

    def update(self, id: int, data: Dict[str, Any]) -> Optional[BaseModel]:
        """更新对象

        Args:
            id: 对象ID
            data: 更新数据字典

        Returns:
            Optional[BaseModel]: 更新后的模型对象，不存在则返回None

        Raises:
            DataAccessError: 更新失败时抛出
        """
        try:
            obj = self.get_by_id(id)
            if not obj:
                return None

            obj.update_from_dict(data)

            self.session.flush()
            logger.info("对象更新成功", extra={
                'model_class': self.model_class.__name__,
                'object_id': id,
                'operation': 'update',
                'updated_fields': list(data.keys())
            })
            return obj
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("对象更新失败", extra={
                'model_class': self.model_class.__name__,
                'object_id': id,
                'operation': 'update',
                'error_type': type(e).__name__,
                'error_message': str(e)
            })
            raise ServiceError(f"更新{self.model_class.__name__}失败") from e

    def delete(self, id: int) -> bool:
        """删除对象

        Args:
            id: 对象ID

        Returns:
            bool: 删除成功返回True，对象不存在返回False

        Raises:
            DataAccessError: 删除失败时抛出
        """
        try:
            obj = self.get_by_id(id)
            if not obj:
                return False

            self.session.delete(obj)
            self.session.flush()
            logger.info("对象删除成功", extra={
                'model_class': self.model_class.__name__,
                'object_id': id,
                'operation': 'delete'
            })
            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("对象删除失败", extra={
                'model_class': self.model_class.__name__,
                'object_id': id,
                'operation': 'delete',
                'error_type': type(e).__name__,
                'error_message': str(e)
            })
            raise ServiceError(f"删除{self.model_class.__name__}失败") from e

    def paginate(
        self,
        query: Query = None,
        page: int = 1,
        page_size: int = 20,
        filters: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """分页查询

        Args:
            query: 查询对象，如果为None则使用默认查询
            page: 页码（从1开始）
            page_size: 每页数量
            filters: 过滤条件字典

        Returns:
            Dict: 包含分页数据的字典
                - data: 数据列表
                - page: 当前页码
                - page_size: 每页数量
                - total_count: 总记录数
                - total_pages: 总页数

        Raises:
            QueryExecutionError: 查询失败时抛出
        """
        try:
            if query is None:
                query = self.session.query(self.model_class)

            if filters:
                query = query.filter_by(**filters)

            total_count = query.count()

            total_pages = (total_count + page_size - 1) // page_size

            if page < 1:
                page = 1
            elif page > total_pages and total_pages > 0:
                page = total_pages

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
            logger.error(f"分页查询失败: {e}", exc_info=True)
            raise ServiceError(f"分页查询{self.model_class.__name__}失败") from e

    def exists(self, filters: Dict[str, Any]) -> bool:
        """检查对象是否存在

        Args:
            filters: 过滤条件字典

        Returns:
            bool: 存在返回True，否则返回False

        Raises:
            QueryExecutionError: 查询失败时抛出
        """
        try:
            query = self.session.query(self.model_class).filter_by(**filters)
            return self.session.query(query.exists()).scalar()
        except SQLAlchemyError as e:
            logger.error(f"检查存在性失败: {e}", exc_info=True)
            raise ServiceError(f"检查{self.model_class.__name__}存在性失败") from e

    def count(self, filters: Dict[str, Any] = None) -> int:
        """统计对象数量

        Args:
            filters: 过滤条件字典

        Returns:
            int: 对象数量

        Raises:
            QueryExecutionError: 查询失败时抛出
        """
        try:
            query = self.session.query(self.model_class)

            if filters:
                query = query.filter_by(**filters)

            return query.count()
        except SQLAlchemyError as e:
            logger.error(f"统计数量失败: {e}", exc_info=True)
            raise ServiceError(f"统计{self.model_class.__name__}数量失败") from e

    def bulk_create(self, data_list: List[Dict[str, Any]]) -> List[BaseModel]:
        """批量创建对象

        Args:
            data_list: 对象数据字典列表

        Returns:
            List[BaseModel]: 创建的模型对象列表

        Raises:
            DataAccessError: 创建失败时抛出
        """
        try:
            objects = [self.model_class(**data) for data in data_list]
            self.session.bulk_save_objects(objects)
            self.session.flush()
            logger.info(f"批量创建{self.model_class.__name__}成功 (数量={len(objects)})")
            return objects
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"批量创建{self.model_class.__name__}失败: {e}", exc_info=True)
            raise ServiceError(f"批量创建{self.model_class.__name__}失败") from e

    def get_paginated(
        self, page: int = 1, per_page: int = 20, filters: Dict[str, Any] = None
    ) -> Tuple[List[BaseModel], int]:
        """获取分页数据（简化版本，返回元组）

        Args:
            page: 页码（从1开始）
            per_page: 每页数量
            filters: 过滤条件字典

        Returns:
            Tuple[List[BaseModel], int]: (数据列表, 总记录数)

        Raises:
            QueryExecutionError: 查询失败时抛出
        """
        try:
            query = self.session.query(self.model_class)

            if filters:
                query = query.filter_by(**filters)

            total = query.count()

            offset = (page - 1) * per_page

            data = query.limit(per_page).offset(offset).all()

            return data, total
        except SQLAlchemyError as e:
            logger.error(f"分页查询失败: {e}", exc_info=True)
            raise ServiceError(f"分页查询{self.model_class.__name__}失败") from e

    def get_by_name(self, name: str) -> Optional[BaseModel]:
        """根据名称获取对象（通用方法）

        Args:
            name: 名称

        Returns:
            Optional[BaseModel]: 模型对象，不存在则返回None

        Raises:
            QueryExecutionError: 查询失败时抛出
        """
        try:
            name_fields = ["name", "username", "customer_name", "device_name"]

            for field in name_fields:
                if hasattr(self.model_class, field):
                    return (
                        self.session.query(self.model_class)
                        .filter(getattr(self.model_class, field) == name)
                        .first()
                    )

            logger.warning(f"{self.model_class.__name__} 没有标准名称字段")
            return None
        except SQLAlchemyError as e:
            logger.error(f"根据名称查询失败: {e}", exc_info=True)
            raise ServiceError(f"查询{self.model_class.__name__}失败") from e


