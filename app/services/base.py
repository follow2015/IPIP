# -*- coding: utf-8 -*-
"""兼容 shim：BaseService 已迁至 app/persistence/base_service（B-44 收官批）。

保留本文件以免破坏既有 ``from app.services.base import BaseService`` 引用面
（app/services/__init__.py / ai_conversation_repository），并维持门禁的
services 文件数下界。本文件**不含任何查询**。
"""
from app.persistence.base_service import BaseService  # noqa: F401

__all__ = ["BaseService"]
