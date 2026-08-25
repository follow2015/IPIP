# -*- coding: utf-8 -*-
"""
统一异常体系模块

提供应用程序的统一异常处理机制。
"""

from .base import BaseAppException
from .business import (
    BusinessLogicError,
    DuplicateUserError,
    InsufficientPermissionError,
    InvalidOperationError,
    ResourceConflictError,
    BusinessRuleViolationError,
    DeviceNotSupported,
    IPAlreadyBannedException,
    IPNotBannedException,
    NoCoreSwitch,
    BanCommandFailed,
    ServiceError,
    UserNotFoundError,
)
from .data_access import (
    DataAccessError,
    DatabaseConnectionError,
    QueryExecutionError,
    RecordNotFoundError,
    TransactionError,
    DataIntegrityError,
    DuplicateRecordError,
)
from .system import (
    CacheError,
    ConfigurationError,
    ExternalServiceError,
    FileSystemError,
    NetworkError,
    SSHConnectionError,
    ResourceExhaustionError,
    SwitchConfigError,
    SystemError,
)
from .validation import (
    ValidationError,
    SchemaValidationError,
    RequiredFieldError,
    InvalidFormatError,
    ValueRangeError,
)
from .handlers import register_error_handlers

__all__ = [
    "BaseAppException",

    "ValidationError",
    "SchemaValidationError",
    "RequiredFieldError",
    "InvalidFormatError",
    "ValueRangeError",

    "BusinessLogicError",
    "UserNotFoundError",
    "DuplicateUserError",
    "InsufficientPermissionError",
    "InvalidOperationError",
    "ResourceConflictError",
    "BusinessRuleViolationError",
    "DeviceNotSupported",
    "IPAlreadyBannedException",
    "IPNotBannedException",
    "NoCoreSwitch",
    "BanCommandFailed",
    "ServiceError",

    "DataAccessError",
    "DatabaseConnectionError",
    "QueryExecutionError",
    "RecordNotFoundError",
    "TransactionError",
    "DataIntegrityError",
    "DuplicateRecordError",

    "SystemError",
    "CacheError",
    "ConfigurationError",
    "ExternalServiceError",
    "FileSystemError",
    "NetworkError",
    "SSHConnectionError",
    "ResourceExhaustionError",
    "SwitchConfigError",

    "register_error_handlers",
]
