# -*- coding: utf-8 -*-
"""
基础模型模块

定义所有模型的基类，提供通用字段和方法。
软删除支持：子类设置 __soft_delete__ = True 并定义 deleted_at 列即可启用。
"""
from datetime import datetime, timezone
from typing import Any, Dict

from extensions import db
from sqlalchemy import Integer, SmallInteger, Text
from sqlalchemy.dialects.mysql import (
    BIGINT as _MYSQL_BIGINT,
    MEDIUMTEXT as _MYSQL_MEDIUMTEXT,
    LONGTEXT as _MYSQL_LONGTEXT,
    TINYINT as _MYSQL_TINYINT,
)
from sqlalchemy.sql import func

MEDIUMTEXT = Text().with_variant(_MYSQL_MEDIUMTEXT(), "mysql")
LONGTEXT = Text().with_variant(_MYSQL_LONGTEXT(), "mysql")


def BIGINT_UNSIGNED():
    """MySQL BIGINT UNSIGNED 自增主键（跨方言安全）。

    - MySQL：渲染 BIGINT UNSIGNED（对齐 5 张监控表的库侧真实类型）。
    - sqlite：退化为 Integer——sqlite 仅在列类型恰为 INTEGER 时才把
      主键作为 rowid 别名实现自增，BIGINT 主键会导致插入 NULL。
    """
    return _MYSQL_BIGINT(unsigned=True).with_variant(Integer(), "sqlite")


def TINYINT(unsigned: bool = False):
    """MySQL TINYINT 列类型（跨方言安全）。

    - MySQL：渲染为 TINYINT [UNSIGNED]，与生产库真实 DDL 对齐
      （docs/2026-09-04-Schema差异评估与修改计划.md §1.3）。
    - sqlite（测试内存库 create_all）：退化为 SmallInteger，
      因 sqlite 方言编译器不识别 mysql.TINYINT。
    """
    return _MYSQL_TINYINT(unsigned=unsigned).with_variant(SmallInteger(), "sqlite")


class BaseModel(db.Model):
    """模型基类

    提供所有模型通用的字段和方法：
    - 主键ID
    - 创建时间和更新时间
    - to_dict / update_from_dict 工具方法

    软删除支持：
    - 子类设置 __soft_delete__ = True
    - 子类定义 deleted_at = db.Column(db.DateTime, nullable=True, comment="软删除时间")
    - 即可使用 is_deleted / soft_delete() / restore() 方法
    """

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
        """是否已被软删除（仅 __soft_delete__=True 的子类可用）"""
        return getattr(self, 'deleted_at', None) is not None

    def soft_delete(self) -> None:
        """执行软删除（设置 deleted_at 为当前时间）"""
        if hasattr(self, 'deleted_at'):
            self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """恢复软删除"""
        if hasattr(self, 'deleted_at'):
            self.deleted_at = None

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        """序列化单个值：datetime → ISO 字符串，其余原样返回。

        子类 to_dict() 中手动构建字段时，可调用此方法避免重复
        isinstance(value, datetime) 判断。
        """
        return value.isoformat() if isinstance(value, datetime) else value

    def to_dict(self, exclude: list = None, include_relations: bool = False) -> Dict[str, Any]:
        """将模型转换为字典

        Args:
            exclude: 要排除的字段列表
            include_relations: 是否包含关联对象

        Returns:
            Dict: 模型数据字典
        """
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
        """从字典更新模型属性

        Args:
            data: 包含更新数据的字典
            exclude: 要排除的字段列表（默认保护主键、时间戳和敏感字段）
            allowed: 允许更新的字段白名单。如果提供，仅更新白名单中的字段（优先级最高，可覆盖 _PROTECTED_FIELDS 但不可覆盖 _IMMUTABLE_FIELDS）
        """
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
