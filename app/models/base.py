# -*- coding: utf-8 -*-
"""
基础模型模块

定义所有模型的基类，提供通用字段和方法。
软删除支持：子类设置 __soft_delete__ = True 并定义 deleted_at 列即可启用。
"""
from datetime import datetime, timezone
from typing import Any, Dict

from extensions import db
from sqlalchemy.sql import func


class BaseModel(db.Model):

    __abstract__ = True

    __soft_delete__ = False

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    @property
    def is_deleted(self) -> bool:
        return getattr(self, 'deleted_at', None) is not None

    def soft_delete(self) -> None:
        if hasattr(self, 'deleted_at'):
            self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        if hasattr(self, 'deleted_at'):
            self.deleted_at = None

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        return value.isoformat() if isinstance(value, datetime) else value

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> Dict[str, Any]:
        exclude = exclude or []
        result = {}
        for column in self.__table__.columns:
            if column.name in exclude:
                continue
            value = getattr(self, column.name)
            result[column.name] = self._serialize_value(value)
        return result

    _IMMUTABLE_FIELDS = frozenset([
        "id", "created_at", "updated_at", "deleted_at",
    ])

    _PROTECTED_FIELDS = frozenset([
        "id", "created_at", "updated_at", "deleted_at",
    ])

    def update_from_dict(self, data: Dict[str, Any], exclude: list = None, allowed: list = None) -> None:
        if allowed is not None:
            for key in allowed:
                if key in data and key not in self._IMMUTABLE_FIELDS and hasattr(self, key):
                    setattr(self, key, data[key])
        else:
            exclude = set(exclude or []) | self._PROTECTED_FIELDS
            for key, value in data.items():
                if key not in exclude and hasattr(self, key):
                    setattr(self, key, value)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"
