# -*- coding: utf-8 -*-
"""
并发安全工具模块

提供线程安全的工具和装饰器，确保系统在多线程环境下的数据一致性。
"""

from app.utils.concurrency.locks import (
    thread_safe,
    singleton,
    ThreadSafeSingleton,
    ReadWriteLock,
    TimeoutLock
)
from app.utils.concurrency.managers import (
    ConcurrencyManager,
    ResourcePool,
    ThreadLocalStorage
)
from app.utils.concurrency.decorators import (
    synchronized,
    retry_on_conflict,
    atomic_operation,
    rate_limited
)

__all__ = [
    'thread_safe',
    'singleton',
    'ThreadSafeSingleton',
    'ReadWriteLock',
    'TimeoutLock',
    
    'ConcurrencyManager',
    'ResourcePool',
    'ThreadLocalStorage',
    
    'synchronized',
    'retry_on_conflict',
    'atomic_operation',
    'rate_limited'
]
